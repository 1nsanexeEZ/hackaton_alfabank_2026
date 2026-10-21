"""Write the OpenAPI schema of the backend to docs/api/openapi.json.

The schema is built from create_app() without starting the server: no
database, broker or storage is needed. Run from backend/ after changing the
API and commit the result:

    uv run python -m scripts.export_openapi
    uv run python -m scripts.export_openapi --check   # exit 1 if the file is stale
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from src.core.config import Settings

DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.json"


def build_schema() -> dict[str, Any]:
    from src.main import create_app  # registers the routers of every module

    # No .env: the schema must not depend on the local configuration.
    return create_app(Settings(_env_file=None)).openapi()


def render(schema: dict[str, Any]) -> str:
    return json.dumps(schema, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check", action="store_true", help="compare with the file instead of writing it"
    )
    args = parser.parse_args(argv)

    content = render(build_schema())
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else None
        if current != content:
            print(f"{args.output} is stale, run: uv run python -m scripts.export_openapi")
            return 1
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8", newline="\n")
    print(f"OpenAPI written to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
