"""
Service đồng bộ cable_detail cho một đoạn cáp.

Các trường hợp xử lý dựa trên total_cable và số bản ghi hiện có:

1. total_cable = 0  → bỏ qua, không làm gì.
2. Không có bản ghi nào (count=0)
   → Tạo mới total_cable bản ghi (cable_number 1..N).
   → Cập nhật available_cable trên đoạn cáp.
3. count == total_cable → đã đủ, bỏ qua.
4. count > total_cable (ví dụ có 24, cần 12)
   → Soft-delete các bản ghi có cable_number > total_cable.
   → Với mỗi bản ghi bị xóa: soft-delete SID liên quan.
   → Cập nhật available_cable.
5. count < total_cable (ví dụ có 10, cần 12)
   → Thêm mới các bản ghi cable_number từ (count+1)..total_cable.
   → Cập nhật available_cable.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import COLLECTION_CABLES, COLLECTION_CABLE_DETAIL, COLLECTION_SID_CABLE
from app.models.cable import CableSyncRequest

STATUS_NOT_USED = {
    "label": "Không sử dụng",
    "value": "Không sử dụng",
    "data_source": "danh_muc_he_thong_list",
    "view_to_open_link": None,
    "display_member": "ten",
    "value_member": "ma",
    "option": {},
    "_id": "",
}


def _new_id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _build_detail_doc(
    cable_id: str,
    ma_tuyen: str,
    cable_number: int,
    payload: CableSyncRequest,
    now: datetime,
) -> Dict[str, Any]:
    """Tạo một bản ghi cable_detail mới."""
    return {
        "_id": _new_id(),
        "parent_id": cable_id,
        "cable_number": cable_number,
        "status": STATUS_NOT_USED,
        "ma_tuyen": ma_tuyen,
        "ghi_chu": None,
        "total_sid": 0,
        "is_deleted": False,
        "is_active": True,
        "created_by_id": payload.created_by_id,
        "created_by_name": payload.created_by_name,
        "created_by_fullname": payload.created_by_fullname,
        "created_by_email": payload.created_by_email,
        "created_by_date": now,
        "modified_by_id": payload.modified_by_id,
        "modified_by_name": payload.modified_by_name,
        "modified_by_fullname": payload.modified_by_fullname,
        "modified_by_email": payload.modified_by_email,
        "modified_by_date": now,
        "company_code": payload.company_code,
    }


async def _count_available(db: AsyncIOMotorDatabase, cable_id: str) -> int:
    """Đếm số cable_detail có status = Không sử dụng và is_deleted = false."""
    return await db[COLLECTION_CABLE_DETAIL].count_documents({
        "parent_id": cable_id,
        "is_deleted": False,
        "status.value": "Không sử dụng",
    })


async def _update_available_cable(
    db: AsyncIOMotorDatabase,
    cable_id: str,
    now: datetime,
) -> int:
    """Cập nhật available_cable trên đoạn cáp theo số lượng không sử dụng thực tế."""
    count = await _count_available(db, cable_id)
    await db[COLLECTION_CABLES].update_one(
        {"_id": cable_id},
        {"$set": {"available_cable": count, "modified_by_date": now}},
    )
    return count


async def _soft_delete_details_and_sids(
    db: AsyncIOMotorDatabase,
    detail_ids: List[str],
    now: datetime,
) -> int:
    """
    Soft-delete danh sách cable_detail và toàn bộ SID liên quan.
    Trả về số cable_detail bị xóa.
    """
    if not detail_ids:
        return 0

    # Soft-delete SID trước
    await db[COLLECTION_SID_CABLE].update_many(
        {"parent_id": {"$in": detail_ids}, "is_deleted": False},
        {"$set": {"is_deleted": True, "modified_by_date": now}},
    )

    # Soft-delete cable_detail
    result = await db[COLLECTION_CABLE_DETAIL].update_many(
        {"_id": {"$in": detail_ids}, "is_deleted": False},
        {"$set": {"is_deleted": True, "modified_by_date": now}},
    )
    return result.modified_count


async def sync_cable_detail(
    db: AsyncIOMotorDatabase,
    payload: CableSyncRequest,
) -> Dict[str, Any]:
    """Entry point: đồng bộ cable_detail theo total_cable."""

    cable_id = payload.id
    total_cable = int(payload.total_cable)
    now = _now()

    # total_cable = 0 → không làm gì
    if total_cable <= 0:
        return {
            "action": "skip",
            "message": "total_cable = 0, không xử lý.",
            "cable_id": cable_id,
        }

    # Lấy tất cả cable_detail hiện có (is_deleted = false), sắp xếp theo cable_number
    existing_cursor = db[COLLECTION_CABLE_DETAIL].find(
        {"parent_id": cable_id, "is_deleted": False},
        {"_id": 1, "cable_number": 1},
    ).sort("cable_number", 1)
    existing = await existing_cursor.to_list(length=None)
    current_count = len(existing)

    # --- Trường hợp 1: Chưa có bản ghi nào → tạo mới toàn bộ ---
    if current_count == 0:
        docs = [
            _build_detail_doc(cable_id, payload.ma_tuyen, i, payload, now)
            for i in range(1, total_cable + 1)
        ]
        await db[COLLECTION_CABLE_DETAIL].insert_many(docs)
        available = await _update_available_cable(db, cable_id, now)
        return {
            "action": "created",
            "message": f"Đã tạo mới {total_cable} bản ghi cable_detail.",
            "cable_id": cable_id,
            "created_count": total_cable,
            "available_cable": available,
        }

    # --- Trường hợp 2: Đã đủ → bỏ qua ---
    if current_count == total_cable:
        return {
            "action": "skip",
            "message": f"Số bản ghi hiện tại ({current_count}) khớp total_cable, không cần xử lý.",
            "cable_id": cable_id,
        }

    # --- Trường hợp 3: Dư → soft-delete các bản ghi cable_number > total_cable ---
    if current_count > total_cable:
        # Lấy _id của các bản ghi cần xóa
        excess_ids = [
            doc["_id"] for doc in existing
            if doc["cable_number"] > total_cable
        ]
        deleted_count = await _soft_delete_details_and_sids(db, excess_ids, now)
        available = await _update_available_cable(db, cable_id, now)
        return {
            "action": "trimmed",
            "message": (
                f"Đã soft-delete {deleted_count} bản ghi có cable_number > {total_cable} "
                f"và SID liên quan."
            ),
            "cable_id": cable_id,
            "deleted_count": deleted_count,
            "available_cable": available,
        }

    # --- Trường hợp 4: Thiếu → thêm mới các bản ghi còn thiếu ---
    # Xác định các cable_number đã tồn tại
    existing_numbers = {doc["cable_number"] for doc in existing}
    missing_numbers = [n for n in range(1, total_cable + 1) if n not in existing_numbers]

    docs = [
        _build_detail_doc(cable_id, payload.ma_tuyen, n, payload, now)
        for n in missing_numbers
    ]
    await db[COLLECTION_CABLE_DETAIL].insert_many(docs)
    available = await _update_available_cable(db, cable_id, now)
    return {
        "action": "appended",
        "message": f"Đã thêm {len(docs)} bản ghi cable_detail còn thiếu (cable_number: {missing_numbers}).",
        "cable_id": cable_id,
        "created_count": len(docs),
        "available_cable": available,
    }