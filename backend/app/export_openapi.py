"""Write the OpenAPI contract: python -m app.export_openapi ../contracts/openapi.json"""
import json
import sys
from pathlib import Path

from app.main import create_app


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(create_app().openapi(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
