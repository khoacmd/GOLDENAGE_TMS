"""Lệnh quản trị.

- `uv run python -m app.cli create-system-admin --username admin`
- `uv run python -m app.cli export-openapi ../packages/api-client/openapi.json`
- `uv run python -m app.cli export-import-docs ../docs/IMPORT_TEMPLATES.md`
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
    docs = sub.add_parser("export-import-docs", help="Sinh tài liệu template import (Markdown)")
    docs.add_argument("output", type=Path)
    args = parser.parse_args()

    if args.command == "create-system-admin":
        password = args.password or getpass.getpass("Mật khẩu: ")
        asyncio.run(_create_system_admin(args.username, password, args.full_name))
    elif args.command == "export-openapi":
        from app.main import app

        args.output.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n")
        print(f"Đã ghi OpenAPI schema vào {args.output}")
    elif args.command == "export-import-docs":
        args.output.write_text(_import_docs())
        print(f"Đã ghi tài liệu template vào {args.output}")


def _import_docs() -> str:
    from app.modules.integration.registry import SPECS

    lines = [
        "# Template import dữ liệu",
        "",
        "> File sinh tự động từ code (`uv run python -m app.cli export-import-docs ...`),"
        " không sửa tay.",
        "",
        "## Quy tắc chung",
        "",
        "- Định dạng: `.xlsx` (sheet `Dữ liệu` hoặc sheet đầu tiên) hoặc `.csv` UTF-8"
        " (phân cách `,` hoặc `;`). Dòng 1 là header.",
        "- Header dùng **nhãn tiếng Việt** (có/không dấu, dấu `*` được bỏ qua) hoặc"
        " **mã cột**; thứ tự cột tùy ý, cột thừa bị bỏ qua.",
        "- Tải template mẫu: `GET /api/v1/imports/templates/{loại}` hoặc màn hình Import trên web.",
        "- **All-or-nothing**: có bất kỳ lỗi nào thì không dòng nào được ghi;"
        " kết quả trả về danh sách lỗi theo dòng/cột.",
        "- `dry_run=true`: chỉ kiểm tra, không ghi.",
        "- Mã (kho, hàng, KH...) không phân biệt hoa/thường;"
        " mã đã có → cập nhật, chưa có → tạo mới.",
        "- Số: dùng ô số của Excel; với text chấp nhận `12.5` hoặc `12,5`."
        " Ngày: ô ngày của Excel hoặc `dd/mm/yyyy`, `yyyy-mm-dd`. Có/không: `C`/`K`.",
        "- Thứ tự nạp lần đầu: Kho → Đội xe → Mặt hàng → Khách hàng → Tồn kho → Đơn hàng.",
        "",
        "## API tích hợp",
        "",
        "Hệ thống ngoài gọi `POST /api/v1/integration/{loại}` với header `X-API-Key`"
        " (admin công ty tạo key ở màn hình Cấu hình). Body:",
        "",
        "```json",
        '{"dry_run": false, "rows": [{"ma_hang": "SUA-TT-180", "ten_hang": "...", ...}]}',
        "```",
        "",
        "Key của mỗi dòng là **mã cột** bên dưới; tối đa 5.000 dòng/lần."
        " Kết quả và quy tắc giống import file.",
    ]
    for kind, spec in SPECS.items():
        lines += [
            "",
            f"## {spec.title} (`{kind.value}`)",
            "",
            spec.description,
            "",
            "| Cột | Mã cột | Bắt buộc | Mô tả | Ví dụ |",
            "|---|---|---|---|---|",
        ]
        for c in spec.columns:
            example = "" if c.example is None else str(c.example)
            lines.append(
                f"| {c.label} | `{c.key}` | {'Có' if c.required else ''} | {c.description} "
                f"| {example} |"
            )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
