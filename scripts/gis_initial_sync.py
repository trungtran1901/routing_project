"""
CLI: đồng bộ (projection) dữ liệu Point/Cable từ MongoDB sang PostGIS.

Dùng cho initial sync (chạy lần đầu để nạp dữ liệu hiện có) hoặc chạy định kỳ
(cron) để đồng bộ lại. An toàn chạy nhiều lần (idempotent, upsert theo
source_id). KHÔNG thay đổi MongoDB.

Cách chạy (từ thư mục gốc project, cùng cấp với app/):

    python -m scripts.gis_initial_sync

Yêu cầu trước khi chạy:
    1. PostgreSQL/PostGIS đã được tạo và đã chạy sql/001_init_postgis.sql
       (xem hướng dẫn trong phần deliverable / README GIS).
    2. .env đã cấu hình POSTGRES_URI trỏ đúng tới database đó.
"""

import asyncio
import json
import sys

import asyncpg
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.services.gis_sync_service import run_full_sync


async def main() -> int:
    print(f"[gis_initial_sync] Kết nối MongoDB: {settings.MONGODB_URI} / db={settings.DATABASE_NAME}")
    mongo_client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = mongo_client[settings.DATABASE_NAME]

    print(f"[gis_initial_sync] Kết nối PostGIS: {settings.POSTGRES_URI}")
    pool = await asyncpg.create_pool(dsn=settings.POSTGRES_URI, min_size=1, max_size=5)

    try:
        result = await run_full_sync(db, pool)
        print("[gis_initial_sync] Kết quả:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except Exception as e:
        print(f"[gis_initial_sync] LỖI: {e}", file=sys.stderr)
        return 1
    finally:
        await pool.close()
        mongo_client.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
