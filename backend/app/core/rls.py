"""SQL dùng trong migration để bật Row-Level Security cho bảng theo công ty.

Context tenant được đặt theo transaction qua `set_config('app.company_id', ...)`
(xem `app.core.db.set_tenant_context`). Khi chưa đặt, `app_current_company()` trả NULL
→ không thấy dòng nào.

Mỗi hàm trả về danh sách câu lệnh riêng lẻ (asyncpg không chạy nhiều lệnh trong một lần
execute): `for stmt in enable_tenant_rls("x"): op.execute(stmt)`.
"""


def create_context_functions() -> list[str]:
    return [
        """
        CREATE OR REPLACE FUNCTION app_current_company() RETURNS uuid
        LANGUAGE sql STABLE AS $$
          SELECT NULLIF(current_setting('app.company_id', true), '')::uuid
        $$
        """,
        """
        CREATE OR REPLACE FUNCTION app_current_user() RETURNS uuid
        LANGUAGE sql STABLE AS $$
          SELECT NULLIF(current_setting('app.user_id', true), '')::uuid
        $$
        """,
    ]


def drop_context_functions() -> list[str]:
    return [
        "DROP FUNCTION IF EXISTS app_current_user()",
        "DROP FUNCTION IF EXISTS app_current_company()",
    ]


def enable_tenant_rls(table: str) -> list[str]:
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"""
        CREATE POLICY tenant_isolation ON {table}
          USING (company_id = app_current_company())
          WITH CHECK (company_id = app_current_company())
        """,
    ]
