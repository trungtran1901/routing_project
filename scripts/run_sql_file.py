"""
Chạy 1 file .sql (vd sql/001_init_postgis.sql) lên PostgreSQL server từ xa,
dùng asyncpg - không cần cài psql/PostgreSQL client trên máy local.

Cách 1 - dùng connection string (POSTGRES_URI trong .env, hoặc truyền tham số):

    python scripts/run_sql_file.py sql/001_init_postgis.sql
    python scripts/run_sql_file.py sql/001_init_postgis.sql "postgresql://user:pass@host:5432/dbname"

    LƯU Ý: nếu mật khẩu chứa ký tự đặc biệt (@ : / # ? khoảng trắng...), phải
    percent-encode trước khi nhét vào URI (vd '@' -> '%40'), nếu không phần
    parser sẽ hiểu nhầm ranh giới user:pass@host. Nếu ngại encode tay, dùng
    Cách 2 bên dưới.

Cách 2 - truyền riêng từng phần kết nối (không cần encode mật khẩu):

    python scripts/run_sql_file.py sql/001_init_postgis.sql --host <host> --port 5432 \
        --user gis_user --password "m@tkhau@laco@" --dbname gis_db
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg

from app.core.config import settings


async def run(sql_path: str, connect_kwargs: dict) -> int:
    safe_kwargs = {k: v for k, v in connect_kwargs.items() if k != "password"}
    print(f"[run_sql_file] Kết nối tới: {safe_kwargs}")
    try:
        conn = await asyncpg.connect(**connect_kwargs)
    except Exception as e:
        print(f"[run_sql_file] LỖI kết nối: {e}", file=sys.stderr)
        return 1

    try:
        with open(sql_path, "r", encoding="utf-8") as f:
            sql = f.read()
        print(f"[run_sql_file] Đang chạy file: {sql_path}")
        await conn.execute(sql)
        print("[run_sql_file] ✓ Thành công.")
        return 0
    except Exception as e:
        print(f"[run_sql_file] LỖI khi chạy SQL: {e}", file=sys.stderr)
        return 1
    finally:
        await conn.close()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Chạy 1 file .sql lên PostgreSQL server (dùng asyncpg, không cần psql client)."
    )
    parser.add_argument("sql_file", help="Đường dẫn tới file .sql cần chạy")
    parser.add_argument(
        "dsn", nargs="?", default=None,
        help="Connection string đầy đủ (postgresql://user:pass@host:port/db). "
             "Nếu mật khẩu có ký tự đặc biệt, dùng --host/--user/--password/--dbname thay vì cái này.",
    )
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user", default=None)
    parser.add_argument(
        "--password", default=None,
        help="Mật khẩu ở dạng gốc, KHÔNG cần percent-encode (kể cả có ký tự @, :, /...).",
    )
    parser.add_argument("--dbname", default=None)
    return parser


if __name__ == "__main__":
    args = build_arg_parser().parse_args()

    # Ưu tiên các tham số --host/--user/--password/--dbname (tránh mọi vấn đề
    # encode mật khẩu). Chỉ dùng dsn (URI) nếu không có đủ các tham số rời.
    if args.host and args.user and args.password and args.dbname:
        connect_kwargs = {
            "host": args.host,
            "port": args.port,
            "user": args.user,
            "password": args.password,
            "database": args.dbname,
        }
    else:
        dsn = args.dsn or settings.POSTGRES_URI
        connect_kwargs = {"dsn": dsn}

    exit_code = asyncio.run(run(args.sql_file, connect_kwargs))
    sys.exit(exit_code)
