from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_impl() -> ModuleType:
    repo_root = Path(__file__).resolve().parents[1]
    impl_path = repo_root / "src" / "ralph" / "cli.py"
    spec = importlib.util.spec_from_file_location("_ralph_src_cli", impl_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load Ralph CLI implementation from {impl_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_IMPL = _load_impl()
main = _IMPL.main


if __name__ == "__main__":
    raise SystemExit(main())
