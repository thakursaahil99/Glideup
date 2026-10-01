"""Write the OpenAPI schema to a file so the frontend can generate its typed client.

uv run python -m app.scripts.export_openapi ../frontend/openapi.json
"""

import json
import sys
from pathlib import Path

from app.main import app


def main() -> None:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
    schema = app.openapi()
    # Always LF, so the file is byte-identical on Windows and in Linux CI (drift check).
    content = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    target.write_text(content, encoding="utf-8", newline="\n")
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
