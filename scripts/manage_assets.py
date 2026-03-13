#!/usr/bin/env python3
"""Validate and synchronize Ralph asset manifests."""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def get_project_dir() -> Path:
    env = os.environ.get("RALPH_PROJECT_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


PROJECT_DIR = get_project_dir()
MANIFEST_FILE = PROJECT_DIR / "assets_manifest.json"
DEFAULT_INBOX_DIR = PROJECT_DIR / ".ralph" / "assets" / "inbox"


class ManifestError(RuntimeError):
    """Manifest validation error."""


@dataclass
class AssetStatus:
    asset_id: str
    state: str
    target_exists: bool
    source_exists: bool
    copied: bool = False
    moved: bool = False
    optional: bool = False


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_rel_path(raw: str, field: str) -> str:
    path = Path(raw)
    if path.is_absolute():
        raise ManifestError(f"{field} must be repo-relative: {raw}")
    normalized = path.as_posix()
    if normalized in {"", "."}:
        raise ManifestError(f"{field} must not be empty")
    if normalized.startswith("../") or "/../" in f"/{normalized}":
        raise ManifestError(f"{field} must stay inside the repo: {raw}")
    return normalized


def load_manifest(path: Path = MANIFEST_FILE) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)

    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"invalid JSON: {exc}") from exc

    if not isinstance(manifest, dict):
        raise ManifestError("manifest root must be an object")

    version = manifest.get("version")
    if version != 1:
        raise ManifestError("version must be 1")

    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ManifestError("assets must be a non-empty list")

    seen_ids: set[str] = set()
    for index, asset in enumerate(assets, start=1):
        if not isinstance(asset, dict):
            raise ManifestError(f"asset #{index} must be an object")

        asset_id = asset.get("id")
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise ManifestError(f"asset #{index} missing id")
        if asset_id in seen_ids:
            raise ManifestError(f"duplicate asset id: {asset_id}")
        seen_ids.add(asset_id)

        kind = asset.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            raise ManifestError(f"asset {asset_id} missing kind")

        request = asset.get("request")
        if not isinstance(request, str) or not request.strip():
            raise ManifestError(f"asset {asset_id} missing request")

        target_path = asset.get("target_path")
        if not isinstance(target_path, str):
            raise ManifestError(f"asset {asset_id} missing target_path")
        asset["target_path"] = normalize_rel_path(target_path, f"{asset_id}.target_path")

        source_path = asset.get("source_path")
        if source_path is None:
            source_path = f".ralph/assets/inbox/{asset_id}"
        if not isinstance(source_path, str) or not source_path.strip():
            raise ManifestError(f"asset {asset_id} missing source_path")
        asset["source_path"] = normalize_rel_path(source_path, f"{asset_id}.source_path")

        if "optional" in asset and not isinstance(asset["optional"], bool):
            raise ManifestError(f"asset {asset_id} optional must be boolean")

        notes = asset.get("notes")
        if notes is not None and not isinstance(notes, str):
            raise ManifestError(f"asset {asset_id} notes must be string")

    return manifest


def write_manifest(manifest: dict, path: Path = MANIFEST_FILE) -> None:
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def resolve_repo_path(relative_path: str) -> Path:
    return (PROJECT_DIR / relative_path).resolve()


def is_managed_inbox_path(relative_path: str) -> bool:
    try:
        resolve_repo_path(relative_path).relative_to(DEFAULT_INBOX_DIR.resolve())
    except ValueError:
        return False
    return True


def sync_manifest(path: Path = MANIFEST_FILE) -> dict:
    manifest = load_manifest(path)
    manifest["last_synced_at"] = now_iso()
    manifest.setdefault("generated_by", "unknown")

    statuses: list[AssetStatus] = []
    copied = 0
    moved = 0
    waiting = 0
    optional_waiting = 0

    for asset in manifest["assets"]:
        asset_id = asset["id"]
        target_path = resolve_repo_path(asset["target_path"])
        source_path = resolve_repo_path(asset["source_path"])
        optional = bool(asset.get("optional", False))

        target_exists = target_path.exists()
        source_exists = source_path.exists()
        asset_copied = False
        asset_moved = False

        if not target_exists and source_exists:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if is_managed_inbox_path(asset["source_path"]) and source_path != target_path:
                shutil.move(str(source_path), str(target_path))
                asset_moved = True
                moved += 1
            else:
                shutil.copy2(source_path, target_path)
                asset_copied = True
                copied += 1
            target_exists = target_path.exists()
            source_exists = source_path.exists()

        if target_exists:
            state = "ready"
            asset["resolved_at"] = now_iso()
            asset.pop("waiting_since", None)
        elif optional:
            state = "optional_missing"
            optional_waiting += 1
            asset.setdefault("waiting_since", now_iso())
        else:
            state = "waiting_for_source"
            waiting += 1
            asset.setdefault("waiting_since", now_iso())

        asset["state"] = state
        statuses.append(
            AssetStatus(
                asset_id=asset_id,
                state=state,
                target_exists=target_exists,
                source_exists=source_exists,
                copied=asset_copied,
                moved=asset_moved,
                optional=optional,
            )
        )

    manifest["summary"] = {
        "total": len(statuses),
        "ready": sum(1 for item in statuses if item.state == "ready"),
        "waiting": waiting,
        "optional_waiting": optional_waiting,
        "copied": copied,
        "moved": moved,
    }
    write_manifest(manifest, path)

    return {
        "manifest_found": True,
        "summary": manifest["summary"],
        "assets": [status.__dict__ for status in statuses],
    }


def print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def command_validate() -> int:
    try:
        manifest = load_manifest()
    except FileNotFoundError:
        print_json({"manifest_found": False})
        return 0
    except ManifestError as exc:
        print_json({"manifest_found": True, "valid": False, "error": str(exc)})
        return 1

    print_json(
        {
            "manifest_found": True,
            "valid": True,
            "version": manifest["version"],
            "assets_total": len(manifest["assets"]),
        }
    )
    return 0


def command_sync() -> int:
    try:
        payload = sync_manifest()
    except FileNotFoundError:
        print_json({"manifest_found": False})
        return 0
    except ManifestError as exc:
        print_json({"manifest_found": True, "valid": False, "error": str(exc)})
        return 1

    print_json(payload)
    if payload["summary"]["waiting"] > 0:
        return 2
    return 0


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"validate", "sync"}:
        print("Usage: manage_assets.py {validate|sync}", file=sys.stderr)
        return 1

    if sys.argv[1] == "validate":
        return command_validate()
    return command_sync()


if __name__ == "__main__":
    sys.exit(main())
