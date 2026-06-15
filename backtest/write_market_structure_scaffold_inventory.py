from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from market_structure import write_scaffold_inventory


def main() -> None:
    path = write_scaffold_inventory()
    print(f"Market structure scaffold inventory written to {path}")


if __name__ == "__main__":
    main()
