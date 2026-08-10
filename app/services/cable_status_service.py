"""
Service cập nhật thống kê trạng thái đoạn cáp (instance_data_hatang_quan_ly_cable).

Luồng xử lý:
1. Lấy parent_id từ payload → _id của cable cha.
2. Truy vấn toàn bộ cable_detail (is_deleted=false) thuộc cable cha.
3. Đếm:
   - error_cable     = số bản ghi có status.value == "Lỗi"
   - used_cable      = số bản ghi có status.value == "Đang hoạt động"
   - available_cable = số bản ghi có status.value == "Không sử dụng"
4. Cập nhật cable cha: error_cable, used_cable, available_cable.
5. Thu thập _id cable_detail → truy vấn sid_cable, lọc trùng SID.value.
6. Cập nhật so_luong_sid (unique), total_sid_raw lên cable cha.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import (
    COLLECTION_CABLES,
    COLLECTION_CABLE_DETAIL,
    COLLECTION_SID_CABLE,
)
from app.models.cable_detail import CableDetailStatusRequest

STATUS_ERROR     = "Lỗi"
STATUS_IN_USE    = "Đang hoạt động"
STATUS_NOT_USED  = "Không sử dụng"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def update_cable_status(
    db: AsyncIOMotorDatabase,
    payload: CableDetailStatusRequest,
) -> Dict[str, Any]:
    now = _now()
    cable_id = payload.parent_id

    # ------------------------------------------------------------------
    # Bước 1: Lấy toàn bộ cable_detail active thuộc cable cha
    # ------------------------------------------------------------------
    detail_cursor = db[COLLECTION_CABLE_DETAIL].find(
        {"parent_id": cable_id, "is_deleted": False},
        {"_id": 1, "status": 1},
    )
    details: List[Dict[str, Any]] = await detail_cursor.to_list(length=None)

    # ------------------------------------------------------------------
    # Bước 2: Đếm theo status
    # ------------------------------------------------------------------
    error_cable     = 0
    used_cable      = 0
    available_cable = 0
    detail_ids: List[str] = []

    for d in details:
        detail_ids.append(d["_id"])
        status_val = None
        if isinstance(d.get("status"), dict):
            status_val = d["status"].get("value")
        if status_val == STATUS_ERROR:
            error_cable += 1
        elif status_val == STATUS_IN_USE:
            used_cable += 1
        elif status_val == STATUS_NOT_USED:
            available_cable += 1

    # ------------------------------------------------------------------
    # Bước 3: Cập nhật error_cable, used_cable, available_cable lên cable cha
    # ------------------------------------------------------------------
    await db[COLLECTION_CABLES].update_one(
        {"_id": cable_id},
        {"$set": {
            "error_cable":     error_cable,
            "used_cable":      used_cable,
            "available_cable": available_cable,
            "modified_by_date": now,
        }},
    )

    # ------------------------------------------------------------------
    # Bước 4: Truy vấn toàn bộ SID active thuộc các cable_detail
    # ------------------------------------------------------------------
    sid_total  = 0
    sid_unique = 0

    if detail_ids:
        sid_cursor = db[COLLECTION_SID_CABLE].find(
            {"parent_id": {"$in": detail_ids}, "is_deleted": False},
            {"_id": 1, "SID": 1},
        )
        sids: List[Dict[str, Any]] = await sid_cursor.to_list(length=None)

        sid_total = len(sids)

        seen_sid_values = set()
        for s in sids:
            sid_obj = s.get("SID")
            sid_value = sid_obj.get("value") if isinstance(sid_obj, dict) else None
            key = sid_value if sid_value else s["_id"]
            seen_sid_values.add(key)

        sid_unique = len(seen_sid_values)

        await db[COLLECTION_CABLES].update_one(
            {"_id": cable_id},
            {"$set": {
                "so_luong_sid":  sid_unique,
                "total_sid_raw": sid_total,
                "modified_by_date": now,
            }},
        )

    return {
        "action": "updated",
        "message": (
            f"Cập nhật cable '{cable_id}': "
            f"error_cable={error_cable}, used_cable={used_cable}, "
            f"available_cable={available_cable}, "
            f"so_luong_sid={sid_unique} (tổng={sid_total})."
        ),
        "cable_id":       cable_id,
        "detail_count":   len(details),
        "error_cable":    error_cable,
        "used_cable":     used_cable,
        "available_cable": available_cable,
        "sid_total":      sid_total,
        "sid_unique":     sid_unique,
    }