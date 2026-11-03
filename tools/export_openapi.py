"""Export the FastAPI OpenAPI document for frontend type generation."""

import json
from pathlib import Path

from yottaflex_debt_collection.api import create_app


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    output = ROOT / "ui" / "openapi.json"
    output.write_text(
        json.dumps(create_app().openapi(), indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"OpenAPI schema written to {output}")


if __name__ == "__main__":
    main()
