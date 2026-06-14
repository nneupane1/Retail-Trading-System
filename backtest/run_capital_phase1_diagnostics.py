from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import AppConfig
from capital.phase1_diagnostics import write_phase1_diagnostics


def main() -> None:
    config = AppConfig.load()
    paths = write_phase1_diagnostics(config)
    print("Capital Phase 1 diagnostics written:")
    for key, path in paths.items():
        print(f"  {key}: {path}")


if __name__ == "__main__":
    main()
