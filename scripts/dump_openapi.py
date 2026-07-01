"""Dump the FastAPI OpenAPI schema to a JSON file for local frontend type generation.

Builds the schema statically via ``app.openapi()`` — it does not start uvicorn,
run the lifespan, or touch the database, so it is safe to run offline and in CI.

Usage:
    PYTHONPATH=src uv run python scripts/dump_openapi.py [output_path]

``output_path`` defaults to ``frontend/.openapi/openapi.json`` (relative to repo root).
The output is a personal, gitignored artifact used as a type oracle; it is not committed.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "frontend" / ".openapi" / "openapi.json"


def main(argv: list[str]) -> int:
    out_arg = argv[1] if len(argv) > 1 else None
    output = Path(out_arg).resolve() if out_arg else DEFAULT_OUTPUT

    # Imported lazily so an import-time failure surfaces with a clear message.
    from fleetent.server import app

    schema = app.openapi()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    paths = schema.get("paths", {})
    route_count = sum(len(methods) for methods in paths.values())
    print(f"wrote {output} ({len(paths)} paths, {route_count} operations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
