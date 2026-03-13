from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "manage_assets.py"


def run_manage_assets(project_dir: Path, command: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RALPH_PROJECT_DIR"] = str(project_dir)
    return subprocess.run(
        ["python3", str(SCRIPT), command],
        cwd=project_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_validate_accepts_standard_assets_manifest(tmp_path: Path) -> None:
    manifest = {
        "version": 1,
        "generated_by": "coder",
        "assets": [
            {
                "id": "hero-image",
                "kind": "image",
                "request": "Generate a hero image",
                "source_path": ".ralph/assets/inbox/hero-image.png",
                "target_path": "src/assets/hero-image.png",
            }
        ],
    }
    (tmp_path / "assets_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = run_manage_assets(tmp_path, "validate")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["manifest_found"] is True
    assert payload["valid"] is True
    assert payload["assets_total"] == 1


def test_sync_moves_assets_into_target_paths(tmp_path: Path) -> None:
    manifest = {
        "version": 1,
        "generated_by": "coder",
        "assets": [
            {
                "id": "logo-svg",
                "kind": "image",
                "request": "Create a vector logo",
                "source_path": ".ralph/assets/inbox/logo.svg",
                "target_path": "src/assets/logo.svg",
            }
        ],
    }
    (tmp_path / "assets_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    inbox_asset = tmp_path / ".ralph" / "assets" / "inbox" / "logo.svg"
    inbox_asset.parent.mkdir(parents=True, exist_ok=True)
    inbox_asset.write_text("<svg>logo</svg>", encoding="utf-8")

    result = run_manage_assets(tmp_path, "sync")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["summary"]["ready"] == 1
    assert payload["summary"]["moved"] == 1
    assert not inbox_asset.exists()
    assert (tmp_path / "src" / "assets" / "logo.svg").read_text(encoding="utf-8") == "<svg>logo</svg>"

    persisted = json.loads((tmp_path / "assets_manifest.json").read_text(encoding="utf-8"))
    assert persisted["assets"][0]["state"] == "ready"
    assert "resolved_at" in persisted["assets"][0]
