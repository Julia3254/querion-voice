from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.internet_ingest_service import ingest_sources


def main() -> None:
    report = ingest_sources()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()