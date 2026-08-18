"""
Kết nối PostgreSQL/PostGIS cho GIS layer.

Thiết kế song song với app/core/database.py (MongoDB):
- connect_to_postgis() / close_postgis_connection() được gọi trong lifespan của app.main.
- get_pg_pool() dùng trong Depends() của router GIS.

GIS layer độc lập với MongoDB. Nếu POSTGRES_URI không cấu hình / Postgres
không sẵn sàng, phần routing hiện tại (Mongo) vẫn hoạt động bình thường —
lỗi kết nối Postgres không được làm sập app chính.
"""

import asyncpg
from typing import Optional

from app.core.config import settings

pg_pool: Optional[asyncpg.pool.Pool] = None


async def connect_to_postgis() -> None:
    global pg_pool
    try:
        pg_pool = await asyncpg.create_pool(
            dsn=settings.POSTGRES_URI,
            min_size=1,
            max_size=settings.POSTGRES_POOL_MAX_SIZE,
            command_timeout=30,
        )
        print("Connected to PostGIS")
    except Exception as e:
        # Không để lỗi kết nối GIS layer làm crash toàn bộ API routing hiện tại.
        pg_pool = None
        print(f"[WARN] Không thể kết nối PostGIS: {e}")


async def close_postgis_connection() -> None:
    global pg_pool
    if pg_pool:
        await pg_pool.close()
        pg_pool = None
        print("Disconnected from PostGIS")


def get_pg_pool() -> asyncpg.pool.Pool:
    """Dependency dùng trong router. Raise rõ ràng nếu GIS layer chưa sẵn sàng."""
    if pg_pool is None:
        raise RuntimeError(
            "PostGIS pool chưa được khởi tạo hoặc kết nối thất bại. "
            "Kiểm tra POSTGRES_URI và trạng thái PostgreSQL/PostGIS."
        )
    return pg_pool
