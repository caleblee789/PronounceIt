from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pronounceit.qa import audit_pronunciations


def main() -> int:
    audit = audit_pronunciations()
    print(json.dumps(audit.as_dict(), indent=2, sort_keys=True))
    return 0 if audit.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
