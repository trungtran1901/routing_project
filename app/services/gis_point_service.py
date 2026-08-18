"""
Service cập nhật toạ độ điểm - ghi đồng thời cả MongoDB lẫn PostGIS.

Khác với segment (geometry chỉ tồn tại ở PostGIS), toạ độ điểm có 2 bản sao:
- MongoDB: point.vi_do / point.kinh_do -> NGUỒN DỮ LIỆU CHÍNH (business data).
- PostGIS: geo_points.geometry -> chiếu (projection) dùng cho spatial query/map.

MongoDB và PostgreSQL là 2 hệ quản trị khác nhau, KHÔNG có transaction chung
(2-phase commit thật sự nằm ngoài phạm vi cần thiết ở đây). Thay vào đó dùng
chiến lược "ghi PostGIS trước (dễ hoàn tác) -> ghi MongoDB sau (nguồn chính)":
nếu bước ghi MongoDB thất bại, sẽ cố gắng hoàn tác (revert) lại PostGIS về
toạ độ cũ (best-effort) để tránh 2 nơi lệch dữ liệu nhau.

Sau khi cập nhật thành công, MỌI đoạn cáp nối tới điểm này (cả AUTO lẫn
USER) sẽ được cập nhật đầu mút geometry ngay lập tức (xem
gis_repository.sync_connected_segments_endpoint) để bản đồ không bị "đứt"
đoạn khỏi điểm. Đoạn USER chỉ bị dịch đúng đầu mút trùng điểm này - các
điểm uốn giữa đường (hình dạng người dùng tự vẽ) được giữ nguyên.

KHÔNG đổi schema MongoDB - chỉ ghi vào field vi_do/kinh_do đã có sẵn.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

import asyncpg
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import COLLECTION_POINTS
from app.repositories import gis_repository


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def update_point_location(
    db: AsyncIOMotorDatabase,
    pool: asyncpg.pool.Pool,
    point_id: str,
    lng: float,
    lat: float,
    modified_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Cập nhật toạ độ 1 điểm (point_id = ma_diem) tại cả MongoDB và PostGIS.

    Raises:
        ValueError: nếu điểm không tồn tại (hoặc đã bị xóa mềm) trong MongoDB.
        Exception: các lỗi khác (kết nối DB...) được để propagate lên router
                   xử lý thành HTTP 500.
    """
    modified_fields = modified_fields or {}

    # 1) Điểm phải tồn tại ở MongoDB - đây là nguồn xác nhận điểm có thật.
    mongo_point = await db[COLLECTION_POINTS].find_one(
        {"ma_diem": point_id, "is_deleted": False}
    )
    if not mongo_point:
        raise ValueError(f"Không tìm thấy điểm '{point_id}' trong MongoDB (hoặc đã bị xóa).")

    old_lng = mongo_point.get("kinh_do")
    old_lat = mongo_point.get("vi_do")

    # 2) Ghi PostGIS trước. Nếu điểm chưa từng được sync (chưa có trong
    #    geo_points), tạo mới luôn từ dữ liệu Mongo hiện có thay vì báo lỗi
    #    404 khó chịu cho người dùng.
    existing_geo = await gis_repository.get_point(pool, point_id)
    if existing_geo is None:
        pt = mongo_point.get("point_type")
        point_type_val = pt.get("value") if isinstance(pt, dict) else None
        await gis_repository.upsert_points_batch(pool, [{
            "source_id": point_id,
            "parent_id": mongo_point.get("parent_id"),
            "ma_tuyen": mongo_point.get("ma_tuyen"),
            "ten_diem": mongo_point.get("ten_diem"),
            "point_type": point_type_val,
            "lng": lng,
            "lat": lat,
        }])
    else:
        await gis_repository.update_point_geometry(pool, point_id, lng, lat)

    # 3) Ghi MongoDB (nguồn chính). Nếu lỗi, cố gắng hoàn tác PostGIS về toạ
    #    độ cũ (best-effort - không raise thêm lỗi nếu bước hoàn tác cũng lỗi,
    #    để lỗi gốc từ MongoDB được báo lên đúng nguyên nhân).
    now = _now()
    update_fields: Dict[str, Any] = {
        "vi_do": lat,
        "kinh_do": lng,
        "modified_by_date": now,
    }
    for k, v in modified_fields.items():
        if v is not None:
            update_fields[k] = v

    try:
        await db[COLLECTION_POINTS].update_one(
            {"ma_diem": point_id, "is_deleted": False},
            {"$set": update_fields},
        )
    except Exception:
        if old_lng is not None and old_lat is not None:
            try:
                await gis_repository.update_point_geometry(
                    pool, point_id, float(old_lng), float(old_lat)
                )
            except Exception:
                pass  # best-effort - không che lấp lỗi gốc
        raise

    # 4) Dịch chuyển đầu mút của MỌI đoạn cáp nối tới điểm này (AUTO lẫn
    #    USER) theo vị trí mới, để map không bị "đứt" đoạn khỏi điểm.
    refreshed_segments = await gis_repository.sync_connected_segments_endpoint(pool, point_id)

    updated_geo = await gis_repository.get_point(pool, point_id)

    return {
        "point": updated_geo,
        "refreshed_segments": refreshed_segments,
    }