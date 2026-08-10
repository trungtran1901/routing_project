"""
Service tính toán và cập nhật các trường thống kê trên tuyến chính
(instance_data_hatang_quanlytuyen_newversion).

Khi nhận một đoạn cáp (cable) thuộc tuyến:
1. Lấy toàn bộ cable có cùng parent_id (is_deleted=false).
2. Tính:
   - so_luong_link_mang_kh = sum(so_luong_sid)
   - chieu_dai_km          = sum(length_cable)
3. Tìm cable có total_cable nhỏ nhất.
   - Nếu nhiều cable cùng total_cable nhỏ nhất → lấy cable có available_cable nhỏ nhất.
   - Cập nhật:
       so_soi_kha_dung_hitc = available_cable của cable đó
       so_soi_su_dung       = used_cable của cable đó
4. Cập nhật tuyến cha.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.tuyen import TuyenStatsRequest

COLLECTION_CABLES = "instance_data_hatang_quan_ly_cable"
COLLECTION_TUYEN  = "instance_data_hatang_quanlytuyen_newversion"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def update_tuyen_stats(
    db: AsyncIOMotorDatabase,
    payload: TuyenStatsRequest,
) -> Dict[str, Any]:
    tuyen_id = payload.parent_id
    now = _now()

    # ------------------------------------------------------------------
    # Bước 1: Lấy toàn bộ cable active thuộc tuyến
    # ------------------------------------------------------------------
    cables_cursor = db[COLLECTION_CABLES].find(
        {"parent_id": tuyen_id, "is_deleted": False},
        {"_id": 1, "so_luong_sid": 1, "length_cable": 1,
         "total_cable": 1, "available_cable": 1, "used_cable": 1},
    )
    cables: List[Dict[str, Any]] = await cables_cursor.to_list(length=None)

    if not cables:
        return {
            "action": "skip",
            "message": "Không có đoạn cáp active thuộc tuyến này.",
            "tuyen_id": tuyen_id,
        }

    # ------------------------------------------------------------------
    # Bước 2: Tính tổng so_luong_sid và length_cable
    # ------------------------------------------------------------------
    so_luong_link_mang_kh = sum(
        (c.get("so_luong_sid") or 0) for c in cables
    )
    chieu_dai_km = sum(
        (c.get("length_cable") or 0) for c in cables
    )

    # ------------------------------------------------------------------
    # Bước 3: Tìm cable có total_cable nhỏ nhất
    #         Trong nhóm đó lấy cable có available_cable nhỏ nhất
    # ------------------------------------------------------------------
    min_total = min((c.get("total_cable") or 0) for c in cables)
    min_total_group = [c for c in cables if (c.get("total_cable") or 0) == min_total]

    target_cable = min(
        min_total_group,
        key=lambda c: (c.get("available_cable") or 0),
    )

    so_soi_kha_dung_hitc = target_cable.get("available_cable") or 0
    so_soi_su_dung       = target_cable.get("used_cable") or 0

    # ------------------------------------------------------------------
    # Bước 4: Cập nhật tuyến cha
    # ------------------------------------------------------------------
    await db[COLLECTION_TUYEN].update_one(
        {"_id": tuyen_id},
        {"$set": {
            "so_luong_link_mang_kh": so_luong_link_mang_kh,
            "chieu_dai_km":          chieu_dai_km,
            "so_soi_kha_dung_hitc":  so_soi_kha_dung_hitc,
            "so_soi_su_dung":        so_soi_su_dung,
            "modified_by_date":      now,
        }},
    )

    return {
        "action": "updated",
        "message": (
            f"Cập nhật tuyến '{tuyen_id}': "
            f"so_luong_link_mang_kh={so_luong_link_mang_kh}, "
            f"chieu_dai_km={chieu_dai_km}, "
            f"so_soi_kha_dung_hitc={so_soi_kha_dung_hitc}, "
            f"so_soi_su_dung={so_soi_su_dung}."
        ),
        "tuyen_id":              tuyen_id,
        "cable_count":           len(cables),
        "so_luong_link_mang_kh": so_luong_link_mang_kh,
        "chieu_dai_km":          chieu_dai_km,
        "min_total_cable":       min_total,
        "so_soi_kha_dung_hitc":  so_soi_kha_dung_hitc,
        "so_soi_su_dung":        so_soi_su_dung,
    }