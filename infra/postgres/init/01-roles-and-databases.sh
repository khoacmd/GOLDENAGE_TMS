#!/bin/bash
# Tạo role & database cho TMS.
#  - tms_owner: sở hữu schema, chạy migration.
#  - tms_app:   role runtime của API/worker, KHÔNG phải owner/superuser → luôn chịu RLS.
set -euo pipefail

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" <<SQL
CREATE ROLE tms_owner LOGIN PASSWORD '${TMS_OWNER_PASSWORD}';
CREATE ROLE tms_app LOGIN PASSWORD '${TMS_APP_PASSWORD}';
CREATE DATABASE tms OWNER tms_owner;
CREATE DATABASE tms_test OWNER tms_owner;
SQL

for db in tms tms_test; do
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$db" <<SQL
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
ALTER SCHEMA public OWNER TO tms_owner;
GRANT USAGE ON SCHEMA public TO tms_app;
ALTER DEFAULT PRIVILEGES FOR ROLE tms_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO tms_app;
ALTER DEFAULT PRIVILEGES FOR ROLE tms_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO tms_app;
SQL
done
