"""Lệnh quản trị.

- `uv run python -m app.cli create-system-admin --username admin`
- `uv run python -m app.cli export-openapi ../packages/api-client/openapi.json`
"""

import argparse
import asyncio
import getpass
import json
from pathlib import Path

from app.core.db import SessionFactory
from app.modules.identity import service as identity_service


async def _create_system_admin(username: str, password: str, full_name: str) -> None:
    async with SessionFactory() as session:
        user = await identity_service.create_user(
            session,
            username=username,
            password=password,
            full_name=full_name,
            is_system_admin=True,
        )
        await session.commit()
        print(f"Đã tạo admin hệ thống '{user.username}' ({user.id})")


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-system-admin", help="Tạo tài khoản admin hệ thống")
    create.add_argument("--username", required=True)
    create.add_argument("--full-name", default="System Administrator")
    create.add_argument("--password", help="Bỏ trống để nhập ẩn")
    export = sub.add_parser("export-openapi", help="Ghi OpenAPI schema ra file JSON")
    export.add_argument("output", type=Path)
    args = parser.parse_args()

    if args.command == "create-system-admin":
        password = args.password or getpass.getpass("Mật khẩu: ")
        asyncio.run(_create_system_admin(args.username, password, args.full_name))
    elif args.command == "export-openapi":
        from app.main import app

        args.output.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n")
        print(f"Đã ghi OpenAPI schema vào {args.output}")


if __name__ == "__main__":
    main()
