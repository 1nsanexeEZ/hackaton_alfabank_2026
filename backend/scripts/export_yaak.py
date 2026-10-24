"""Write the Yaak collection of the API to docs/api/yaak/ and docs/api/yaak.json.

The collection is built from docs/api/openapi.json and the scenarios in
scripts/yaak/scenarios.py: a reference folder with every operation and the
folders S-1…S-10 whose steps take ids from the answers before them. Yaak opens
docs/api/yaak/ with Open Folder and keeps it in sync, docs/api/yaak.json is the
same for Import. Run from backend/ after changing the API or a scenario and
commit the result:

    uv run python -m scripts.export_yaak
    uv run python -m scripts.export_yaak --check   # exit 1 if the files are stale
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.yaak.accounts import ACCOUNTS, login_body, login_request_id, token_variables
from scripts.yaak.collection import NO_AUTH, Collection, var
from scripts.yaak.reference import add_reference
from scripts.yaak.scenarios import add_scenarios

DOCS_API = Path(__file__).resolve().parents[2] / "docs" / "api"
DEFAULT_OPENAPI = DOCS_API / "openapi.json"
DEFAULT_FOLDER = DOCS_API / "yaak"
DEFAULT_EXPORT = DOCS_API / "yaak.json"

ENVIRONMENTS = {
    "local": ("http://localhost:8080/api", "#22c55e"),
    "stand": ("https://alfa-hack.ru/api", "#ef4444"),
}


def build(openapi: dict[str, Any]) -> Collection:
    collection = Collection(
        "credit-cabinet",
        "Кредитный кабинет МСБ — API",
        "Справочник по всем ручкам API и сценарии проверки S-1…S-10. Выберите окружение "
        "`local` или `stand`, токены ролей берутся сами. Собрано "
        "`backend/scripts/export_yaak.py` из `docs/api/openapi.json`.",
    )
    base_id = collection.environment(
        "base",
        "Общие",
        {
            "demo_password": "Demo-2026!",
            "admin_login": "admin@example.com",
            "admin_password": "Admin-2026!",
            **token_variables(),
        },
    )
    for name, (base_url, color) in ENVIRONMENTS.items():
        collection.environment(
            f"env/{name}",
            name,
            {"base_url": base_url},
            parent_model="environment",
            parent_id=base_id,
            color=color,
        )
    _add_logins(collection)
    add_scenarios(collection)
    add_reference(collection, openapi)
    return collection


def _add_logins(collection: Collection) -> None:
    folder = collection.folder(
        "logins",
        "Токены ролей",
        parent=None,
        description=(
            "Вход под каждой демо-учёткой. Отправлять руками не нужно: переменные `token_*` "
            "окружения берут токен из последнего ответа и сами входят заново раз в 25 минут. "
            "После смены окружения отправьте вход нужных ролей — иначе до 25 минут будут уходить "
            "токены прошлого стенда. На `stand` всю папку разом не отправляйте: nginx там пускает "
            "на вход 10 запросов в минуту, не больше шести подряд."
        ),
    )
    for who, (_, person) in ACCOUNTS.items():
        collection.request(
            login_request_id(who),
            person[0].upper() + person[1:],
            "POST",
            var("base_url") + "/auth/login",
            folder=folder,
            auth=NO_AUTH,
            description=f"200 и `access_token` на 30 минут: переменная `token_{who}`.",
            body=login_body(who),
        )


def render(collection: Collection) -> tuple[dict[str, str], str]:
    return collection.files(), collection.export()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--openapi", type=Path, default=DEFAULT_OPENAPI)
    parser.add_argument("--folder", type=Path, default=DEFAULT_FOLDER)
    parser.add_argument("--export", type=Path, default=DEFAULT_EXPORT)
    parser.add_argument(
        "--check", action="store_true", help="compare with the files instead of writing them"
    )
    args = parser.parse_args(argv)

    openapi = json.loads(args.openapi.read_text(encoding="utf-8"))
    files, export = render(build(openapi))
    if args.check:
        current = {p.name: p.read_text(encoding="utf-8") for p in args.folder.glob("yaak.*.yaml")}
        exported = args.export.read_text(encoding="utf-8") if args.export.exists() else None
        if current != files or exported != export:
            print("The Yaak collection is stale, run: uv run python -m scripts.export_yaak")
            return 1
        return 0
    args.folder.mkdir(parents=True, exist_ok=True)
    for stale in args.folder.glob("yaak.*.yaml"):
        if stale.name not in files:
            stale.unlink()
    for name, content in files.items():
        (args.folder / name).write_text(content, encoding="utf-8", newline="\n")
    args.export.write_text(export, encoding="utf-8", newline="\n")
    print(f"Yaak collection written to {args.folder} ({len(files)} files) and {args.export}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
