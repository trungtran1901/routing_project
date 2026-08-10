"""
Service cập nhật trạng thái sợi (cable_detail) khi có SID mới được gắn vào.

Luồng xử lý:
1. Nhận dữ liệu SID cable (parent_id = _id của cable_detail).
2. Đếm số SID active trong collection sid_cable có parent_id = cable_detail._id.
3. Nếu count > 0:
   - Cập nhật total_sid trong cable_detail = count.
   - Nếu status hiện tại là "Không sử dụng" → đổi sang "Đang hoạt động".
4. Cập nhật available_cable trên cable cha (cable_detail.parent_id).
"""

from datetime import datetime, timezone
from typing import Dict, Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import (
    COLLECTION_CABLES,
    COLLECTION_CABLE_DETAIL,
    COLLECTION_SID_CABLE,
)
from app.models.sid import SIDCableRequest

STATUS_NOT_USED = "Không sử dụng"
STATUS_ACTIVE = {
    "label": "Đang hoạt động",
    "value": "Đang hoạt động",
    "data_source": "danh_muc_he_thong_list",
    "view_to_open_link": None,
    "display_member": "ten",
    "value_member": "ma",
    "option": {},
    "_id": "b16a8287496b407693986404e9bb2276",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _update_available_cable(
    db: AsyncIOMotorDatabase,
    cable_id: str,
    now: datetime,
) -> int:
    """Đếm lại cable_detail có status = Không sử dụng và cập nhật available_cable trên cable cha."""
    count = await db[COLLECTION_CABLE_DETAIL].count_documents({
        "parent_id": cable_id,
        "is_deleted": False,
        "status.value": STATUS_NOT_USED,
    })
    await db[COLLECTION_CABLES].update_one(
        {"_id": cable_id},
        {"$set": {"available_cable": count, "modified_by_date": now}},
    )
    return count


async def update_fiber_status(
    db: AsyncIOMotorDatabase,
    payload: SIDCableRequest,
) -> Dict[str, Any]:
    """
    Cập nhật trạng thái sợi sau khi SID được gắn vào cable_detail.

    - parent_id trong payload = _id của cable_detail cần cập nhật.
    - Đếm SID active thuộc cable_detail đó.
    - Nếu count > 0: cập nhật total_sid, đổi status nếu đang "Không sử dụng".
    - Tính lại available_cable trên cable cha.
    """
    now = _now()
    detail_id = payload.parent_id  # _id của cable_detail

    # Đếm SID active thuộc cable_detail này
    sid_count = await db[COLLECTION_SID_CABLE].count_documents({
        "parent_id": detail_id,
        "is_deleted": False,
    })

    if sid_count == 0:
        return {
            "action": "skip",
            "message": "Không có SID active, không cập nhật trạng thái sợi.",
            "detail_id": detail_id,
            "sid_count": 0,
        }

    # Lấy cable_detail hiện tại để kiểm tra status và lấy parent_id (cable cha)
    detail_doc = await db[COLLECTION_CABLE_DETAIL].find_one(
        {"_id": detail_id, "is_deleted": False},
        {"status": 1, "parent_id": 1},
    )
    if not detail_doc:
        raise ValueError(f"Không tìm thấy cable_detail '{detail_id}'.")

    current_status_value = None
    if isinstance(detail_doc.get("status"), dict):
        current_status_value = detail_doc["status"].get("value")

    # Xây dựng $set update
    update_fields: Dict[str, Any] = {
        "total_sid": sid_count,
        "modified_by_date": now,
    }
    status_changed = False
    if current_status_value == STATUS_NOT_USED:
        update_fields["status"] = STATUS_ACTIVE
        status_changed = True

    await db[COLLECTION_CABLE_DETAIL].update_one(
        {"_id": detail_id},
        {"$set": update_fields},
    )

    # Cập nhật lại available_cable trên cable cha
    cable_id = detail_doc.get("parent_id")
    available_cable = None
    if cable_id:
        available_cable = await _update_available_cable(db, cable_id, now)

    return {
        "action": "updated",
        "message": (
            f"Cập nhật total_sid = {sid_count} cho cable_detail '{detail_id}'"
            + (", đổi status → 'Đang hoạt động'." if status_changed else ".")
        ),
        "detail_id": detail_id,
        "sid_count": sid_count,
        "status_changed": status_changed,
        "available_cable": available_cable,
    }