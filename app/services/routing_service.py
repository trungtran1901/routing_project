"""
Service xử lý bài toán routing cho tuyến cáp.
Việc tạo/xóa điểm do cơ chế riêng bên ngoài xử lý.
API này chỉ quản lý đoạn cáp (cable) giữa các điểm.

Ba trường hợp chính:
1. Điểm mới thêm vào CUỐI tuyến   → tạo 1 đoạn cáp (điểm cuối cũ → điểm mới)
2. Điểm mới CHÈN vào GIỮA 2 điểm → vô hiệu hóa đoạn cũ, tạo 2 đoạn mới
3. Điểm bị XÓA                    → vô hiệu hóa đoạn + detail + sid, nối lại A→C
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import (
    COLLECTION_POINTS,
    COLLECTION_CABLES,
    COLLECTION_CABLE_DETAIL,
    COLLECTION_SID_CABLE,
)
from app.models.point import PointCreateRequest, PointDeleteRequest

# Collection tuyến chính
COLLECTION_TUYEN = "instance_data_hatang_quanlytuyen_newversion"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _extract_user_fields(source: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "created_by_id": source.get("created_by_id"),
        "created_by_name": source.get("created_by_name"),
        "created_by_fullname": source.get("created_by_fullname"),
        "created_by_email": source.get("created_by_email"),
        "created_by_date": source.get("created_by_date"),
        "modified_by_id": source.get("modified_by_id"),
        "modified_by_name": source.get("modified_by_name"),
        "modified_by_fullname": source.get("modified_by_fullname"),
        "modified_by_email": source.get("modified_by_email"),
        "modified_by_date": source.get("modified_by_date"),
        "company_code": source.get("company_code"),
    }


def _build_cable_doc(
    parent_id: str,
    start_ma: str,
    start_ten: str,
    end_ma: str,
    end_ten: str,
    user_fields: Dict[str, Any],
    ma_tuyen: Optional[str] = None,
    total_cable: Optional[float] = None,
    cable_type: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Tạo document đoạn cáp mới."""
    code = f"{start_ma}-{end_ma}"
    now = _now()
    return {
        "_id": _new_id(),
        "parent_id": parent_id,
        "ma_tuyen": ma_tuyen,
        "code": code,
        "total_cable": total_cable if total_cable is not None else 0,
        "error_cable": 0,
        "available_cable": 0,
        "start_point": start_ma,
        "end_point": end_ma,
        "length_cable": 0,
        "ghi_chu": None,
        "start_point_text": start_ten,
        "end_point_text": end_ten,
        "cable_type": cable_type,
        "is_deleted": False,
        "is_active": True,
        **user_fields,
        "modified_by_date": now,
    }


# ---------------------------------------------------------------------------
# Truy vấn helpers
# ---------------------------------------------------------------------------

async def _get_tuyen_info(
    db: AsyncIOMotorDatabase,
    parent_id: str,
) -> Optional[Dict[str, Any]]:
    """Lấy thông tin tuyến từ collection tuyến chính theo _id = parent_id của điểm."""
    return await db[COLLECTION_TUYEN].find_one(
        {"_id": parent_id, "is_deleted": False},
        {"total_cable": 1, "loai_cable_f0": 1},
    )


async def _get_point_by_ma(
    db: AsyncIOMotorDatabase,
    ma_diem: str,
) -> Optional[Dict[str, Any]]:
    return await db[COLLECTION_POINTS].find_one({"ma_diem": ma_diem, "is_deleted": False})


async def _update_so_luong_mx(
    db: AsyncIOMotorDatabase,
    parent_id: str,
    now: datetime,
) -> int:
    """Đếm điểm active thuộc tuyến rồi cập nhật so_luong_mx trên collection tuyến."""
    count = await db[COLLECTION_POINTS].count_documents(
        {"parent_id": parent_id, "is_deleted": False}
    )
    await db[COLLECTION_TUYEN].update_one(
        {"_id": parent_id},
        {"$set": {"so_luong_mx": count, "modified_by_date": now}},
    )
    return count


async def _soft_delete_cables_by_point(
    db: AsyncIOMotorDatabase,
    ma_diem: str,
    now: datetime,
) -> List[str]:
    """
    Vô hiệu hóa tất cả đoạn cáp có start_point HOẶC end_point = ma_diem.
    Trả về danh sách _id các đoạn bị xóa để cascade xuống detail và sid.
    """
    # Lấy _id các đoạn trước khi xóa
    cursor = db[COLLECTION_CABLES].find(
        {
            "$or": [{"start_point": ma_diem}, {"end_point": ma_diem}],
            "is_deleted": False,
        },
        {"_id": 1},
    )
    docs = await cursor.to_list(length=None)
    cable_ids = [d["_id"] for d in docs]

    if cable_ids:
        await db[COLLECTION_CABLES].update_many(
            {"_id": {"$in": cable_ids}},
            {"$set": {"is_deleted": True, "modified_by_date": now}},
        )
        # Cascade → cable_detail
        detail_cursor = db[COLLECTION_CABLE_DETAIL].find(
            {"parent_id": {"$in": cable_ids}, "is_deleted": False},
            {"_id": 1},
        )
        detail_docs = await detail_cursor.to_list(length=None)
        detail_ids = [d["_id"] for d in detail_docs]

        if detail_ids:
            await db[COLLECTION_CABLE_DETAIL].update_many(
                {"_id": {"$in": detail_ids}},
                {"$set": {"is_deleted": True, "modified_by_date": now}},
            )
            # Cascade → sid_cable
            await db[COLLECTION_SID_CABLE].update_many(
                {"parent_id": {"$in": detail_ids}, "is_deleted": False},
                {"$set": {"is_deleted": True, "modified_by_date": now}},
            )

    return cable_ids


async def _soft_delete_cable_between(
    db: AsyncIOMotorDatabase,
    start_ma: str,
    end_ma: str,
    now: datetime,
) -> int:
    """Vô hiệu hóa đoạn cáp nối đúng start_ma → end_ma (không cascade, dùng khi tạo lại)."""
    result = await db[COLLECTION_CABLES].update_many(
        {"start_point": start_ma, "end_point": end_ma, "is_deleted": False},
        {"$set": {"is_deleted": True, "modified_by_date": now}},
    )
    return result.modified_count


# ---------------------------------------------------------------------------
# Use-case 1: Điểm thêm vào CUỐI tuyến
# ---------------------------------------------------------------------------

async def handle_add_point_to_end(
    db: AsyncIOMotorDatabase,
    new_point: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Điểm mới thêm vào cuối tuyến (start_point = None).
    Lấy total_cable và loai_cable_f0 từ collection tuyến chính để gắn vào đoạn cáp tạo mới.
    """
    ma_tuyen = new_point["ma_tuyen"]
    parent_id = new_point["parent_id"]
    ma_diem_moi = new_point["ma_diem"]

    # Tìm điểm cuối hiện tại, loại trừ chính điểm mới
    cursor = (
        db[COLLECTION_POINTS]
        .find({
            "ma_tuyen": ma_tuyen,
            "parent_id": parent_id,
            "is_deleted": False,
            "ma_diem": {"$ne": ma_diem_moi},
        })
        .sort("thu_tu", -1)
        .limit(1)
    )
    docs = await cursor.to_list(length=1)
    last_point = docs[0] if docs else None

    if last_point is None:
        so_luong_mx = await _update_so_luong_mx(db, parent_id, _now())
        return {
            "action": "add_to_end",
            "message": "Điểm đầu tiên của tuyến, không cần tạo đoạn cáp.",
            "created_cables": [],
            "so_luong_mx": so_luong_mx,
        }

    # Lấy thông tin tuyến để gắn total_cable và cable_type
    tuyen_info = await _get_tuyen_info(db, parent_id)
    total_cable = tuyen_info.get("total_cable") if tuyen_info else None
    cable_type = tuyen_info.get("loai_cable_f0") if tuyen_info else None

    user_fields = _extract_user_fields(new_point)
    cable = _build_cable_doc(
        parent_id=parent_id,
        start_ma=last_point["ma_diem"],
        start_ten=last_point["ten_diem"],
        end_ma=ma_diem_moi,
        end_ten=new_point["ten_diem"],
        user_fields=user_fields,
        ma_tuyen=ma_tuyen,
        total_cable=total_cable,
        cable_type=cable_type,
    )
    await db[COLLECTION_CABLES].insert_one(cable)

    # Cập nhật so_luong_mx trên tuyến
    so_luong_mx = await _update_so_luong_mx(db, parent_id, _now())

    return {
        "action": "add_to_end",
        "message": f"Đã tạo đoạn cáp '{cable['code']}'.",
        "created_cables": [cable["code"]],
        "so_luong_mx": so_luong_mx,
    }


# ---------------------------------------------------------------------------
# Use-case 2: Điểm CHÈN vào GIỮA 2 điểm
# ---------------------------------------------------------------------------

async def handle_insert_point_between(
    db: AsyncIOMotorDatabase,
    new_point: Dict[str, Any],
    start_point_ma: str,
) -> Dict[str, Any]:
    """
    Điểm mới chèn vào giữa. Lấy total_cable và loai_cable_f0 từ tuyến chính
    để gắn vào các đoạn cáp tạo mới.
    """
    parent_id = new_point["parent_id"]
    ma_tuyen = new_point.get("ma_tuyen")

    start_point_doc = await _get_point_by_ma(db, start_point_ma)
    if start_point_doc is None:
        raise ValueError(f"Không tìm thấy điểm bắt đầu '{start_point_ma}'")

    # Lấy thông tin tuyến
    tuyen_info = await _get_tuyen_info(db, parent_id)
    total_cable = tuyen_info.get("total_cable") if tuyen_info else None
    cable_type = tuyen_info.get("loai_cable_f0") if tuyen_info else None

    existing_cable = await db[COLLECTION_CABLES].find_one(
        {"start_point": start_point_ma, "is_deleted": False}
    )

    now = _now()
    user_fields = _extract_user_fields(new_point)
    created_cables: List[str] = []
    disabled_cables: List[str] = []

    if existing_cable:
        old_end_ma = existing_cable["end_point"]
        old_end_doc = await _get_point_by_ma(db, old_end_ma)
        old_end_ten = old_end_doc["ten_diem"] if old_end_doc else old_end_ma

        # Vô hiệu hóa đoạn cũ (không cascade vì đoạn đang bị thay thế, không bị xóa vĩnh viễn)
        await _soft_delete_cable_between(db, start_point_ma, old_end_ma, now)
        disabled_cables.append(existing_cable.get("code", f"{start_point_ma}-{old_end_ma}"))

        # Tạo đoạn 1: start → điểm mới
        cable1 = _build_cable_doc(
            parent_id=parent_id,
            start_ma=start_point_ma,
            start_ten=start_point_doc["ten_diem"],
            end_ma=new_point["ma_diem"],
            end_ten=new_point["ten_diem"],
            user_fields=user_fields,
            ma_tuyen=ma_tuyen,
            total_cable=total_cable,
            cable_type=cable_type,
        )
        await db[COLLECTION_CABLES].insert_one(cable1)
        created_cables.append(cable1["code"])

        # Tạo đoạn 2: điểm mới → end_cũ
        cable2 = _build_cable_doc(
            parent_id=parent_id,
            start_ma=new_point["ma_diem"],
            start_ten=new_point["ten_diem"],
            end_ma=old_end_ma,
            end_ten=old_end_ten,
            user_fields=user_fields,
            ma_tuyen=ma_tuyen,
            total_cable=total_cable,
            cable_type=cable_type,
        )
        await db[COLLECTION_CABLES].insert_one(cable2)
        created_cables.append(cable2["code"])

        so_luong_mx = await _update_so_luong_mx(db, parent_id, _now())
        return {
            "action": "insert_between",
            "message": (
                f"Vô hiệu hóa đoạn '{disabled_cables[0]}', "
                f"tạo 2 đoạn mới: {created_cables}."
            ),
            "disabled_cables": disabled_cables,
            "created_cables": created_cables,
            "so_luong_mx": so_luong_mx,
        }
    else:
        cable1 = _build_cable_doc(
            parent_id=parent_id,
            start_ma=start_point_ma,
            start_ten=start_point_doc["ten_diem"],
            end_ma=new_point["ma_diem"],
            end_ten=new_point["ten_diem"],
            user_fields=user_fields,
            ma_tuyen=ma_tuyen,
            total_cable=total_cable,
            cable_type=cable_type,
        )
        await db[COLLECTION_CABLES].insert_one(cable1)
        created_cables.append(cable1["code"])

        so_luong_mx = await _update_so_luong_mx(db, parent_id, _now())
        return {
            "action": "insert_between",
            "message": (
                f"Không tìm thấy đoạn tiếp theo của '{start_point_ma}' "
                f"(đang là cuối tuyến). Tạo 1 đoạn mới: '{cable1['code']}'."
            ),
            "disabled_cables": [],
            "created_cables": created_cables,
            "so_luong_mx": so_luong_mx,
        }


# ---------------------------------------------------------------------------
# Use-case 3: Xóa điểm → vô hiệu hóa đoạn + cascade detail + sid, nối lại A→C
# ---------------------------------------------------------------------------

async def handle_delete_point(
    db: AsyncIOMotorDatabase,
    request: PointDeleteRequest,
) -> Dict[str, Any]:
    """
    Khi điểm B bị xóa:
    1. Tìm đoạn A→B và B→C trước khi xóa.
    2. Soft-delete đoạn liên quan + cascade xuống cable_detail + sid_cable.
    3. Nếu B nằm giữa → tạo đoạn A→C (lấy total_cable, cable_type từ tuyến).
    """
    now = _now()
    ma_diem = request.ma_diem

    # Lấy đoạn vào và ra trước khi xóa
    cable_in = await db[COLLECTION_CABLES].find_one(
        {"end_point": ma_diem, "is_deleted": False}
    )
    cable_out = await db[COLLECTION_CABLES].find_one(
        {"start_point": ma_diem, "is_deleted": False}
    )

    # Soft-delete tất cả đoạn liên quan + cascade detail + sid
    deleted_cable_ids = await _soft_delete_cables_by_point(db, ma_diem, now)

    created_cable: Optional[str] = None

    # Nếu B nằm giữa A và C → nối lại A→C
    if cable_in and cable_out:
        point_a = await _get_point_by_ma(db, cable_in["start_point"])
        point_c = await _get_point_by_ma(db, cable_out["end_point"])

        if point_a and point_c:
            # Lấy thông tin tuyến để gắn total_cable và cable_type
            tuyen_info = await _get_tuyen_info(db, request.parent_id)
            total_cable = tuyen_info.get("total_cable") if tuyen_info else None
            cable_type = tuyen_info.get("loai_cable_f0") if tuyen_info else None

            if request.deleted_by_id:
                user_fields = {
                    "created_by_id": request.deleted_by_id,
                    "created_by_name": request.deleted_by_name,
                    "created_by_fullname": request.deleted_by_fullname,
                    "created_by_email": request.deleted_by_email,
                    "created_by_date": now,
                    "modified_by_id": request.deleted_by_id,
                    "modified_by_name": request.deleted_by_name,
                    "modified_by_fullname": request.deleted_by_fullname,
                    "modified_by_email": request.deleted_by_email,
                    "modified_by_date": now,
                    "company_code": request.company_code,
                }
            else:
                user_fields = _extract_user_fields(point_a)

            new_cable = _build_cable_doc(
                parent_id=request.parent_id,
                start_ma=point_a["ma_diem"],
                start_ten=point_a["ten_diem"],
                end_ma=point_c["ma_diem"],
                end_ten=point_c["ten_diem"],
                user_fields=user_fields,
                ma_tuyen=request.ma_tuyen,
                total_cable=total_cable,
                cable_type=cable_type,
            )
            await db[COLLECTION_CABLES].insert_one(new_cable)
            created_cable = new_cable["code"]

    # Cập nhật so_luong_mx trên tuyến
    so_luong_mx = await _update_so_luong_mx(db, request.parent_id, now)

    return {
        "action": "delete_point",
        "message": (
            f"Đã vô hiệu hóa {len(deleted_cable_ids)} đoạn cáp và cascade detail/sid "
            f"liên quan đến điểm '{ma_diem}'"
            + (f", tạo đoạn nối mới '{created_cable}'." if created_cable else ".")
        ),
        "deleted_point": ma_diem,
        "affected_cables_count": len(deleted_cable_ids),
        "created_cable": created_cable,
        "so_luong_mx": so_luong_mx,
    }


# ---------------------------------------------------------------------------
# Entry point tổng hợp
# ---------------------------------------------------------------------------

async def process_add_point(
    db: AsyncIOMotorDatabase,
    payload: PointCreateRequest,
) -> Dict[str, Any]:
    """
    Điểm đã được tạo sẵn trong DB bởi cơ chế ngoài.
    Phân nhánh dựa vào payload.start_point:
      - None        → điểm thêm vào cuối tuyến
      - có giá trị  → điểm chèn vào giữa
    """
    new_point = payload.model_dump(exclude_none=False)

    start_ma = payload.start_point.value if payload.start_point is not None else None

    if start_ma:
        return await handle_insert_point_between(db, new_point, start_ma)
    else:
        return await handle_add_point_to_end(db, new_point)


# ---------------------------------------------------------------------------
# Use-case 4: Lấy dữ liệu sơ đồ tuyến (nodes + edges)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Helper: làm sạch doc trước khi đưa vào customData
# ---------------------------------------------------------------------------

_AUDIT_FIELDS = {
    "created_by_id", "created_by_name", "created_by_fullname",
    "created_by_email", "created_by_date",
    "modified_by_id", "modified_by_name",
    "modified_by_email", "modified_by_date",
    "company_code",
}


def _clean_doc(doc: Dict[str, Any], exclude_keys: set = None) -> Dict[str, Any]:
    """Loại bỏ _id, audit fields và chuyển ObjectId thành string."""
    skip = {"_id"} | _AUDIT_FIELDS | (exclude_keys or set())
    return {
        k: (str(v) if v.__class__.__name__ == "ObjectId" else v)
        for k, v in doc.items()
        if k not in skip
    }


async def _resolve_parent_id(
    db: AsyncIOMotorDatabase,
    tuyen_id: Optional[str],
    ma_tuyen: Optional[str],
) -> str:
    """Trả về parent_id từ tuyen_id hoặc ma_tuyen."""
    if tuyen_id:
        return tuyen_id
    sample = await db[COLLECTION_POINTS].find_one(
        {"ma_tuyen": ma_tuyen, "is_deleted": False},
        {"parent_id": 1},
    )
    if not sample:
        raise ValueError(f"Không tìm thấy tuyến với mã '{ma_tuyen}'.")
    return sample["parent_id"]


async def get_diagram_data(
    db: AsyncIOMotorDatabase,
    tuyen_id: Optional[str] = None,
    ma_tuyen: Optional[str] = None,
) -> Dict[str, Any]:
    """Sơ đồ tuyến: nodes là điểm, edges là đoạn cáp."""
    if not tuyen_id and not ma_tuyen:
        raise ValueError("Cần truyền tuyen_id hoặc ma_tuyen.")

    parent_id = await _resolve_parent_id(db, tuyen_id, ma_tuyen)

    points_cursor = db[COLLECTION_POINTS].find(
        {"parent_id": parent_id, "is_deleted": False},
    )
    points = await points_cursor.to_list(length=None)

    cable_query = (
        {"ma_tuyen": ma_tuyen, "is_deleted": False}
        if ma_tuyen
        else {"parent_id": parent_id, "is_deleted": False}
    )
    cables_cursor = db[COLLECTION_CABLES].find(cable_query)
    cables = await cables_cursor.to_list(length=None)

    nodes = []
    for p in points:
        pt = p.get("point_type")
        point_type_val = pt.get("value") if isinstance(pt, dict) else None
        custom = _clean_doc(p)
        custom["type"] = point_type_val or ""
        nodes.append({
            "id": p["ma_diem"],
            "label": p.get("ten_diem", ""),
            "customData": custom,
        })

    edges = []
    for c in cables:
        start_text = c.get("start_point_text") or ""
        end_text   = c.get("end_point_text") or ""
        label = f"{start_text} - {end_text}" if start_text and end_text else (start_text or end_text)
        edges.append({
            "id":         c.get("code", ""),
            "from":       c.get("start_point", ""),
            "to":         c.get("end_point", ""),
            "label":      label,
            "customData": _clean_doc(c),
        })

    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Use-case 5: Sơ đồ tuyến theo SỢI (cable_detail là edge, có list_sid)
# ---------------------------------------------------------------------------

async def get_fiber_diagram_data(
    db: AsyncIOMotorDatabase,
    tuyen_id: Optional[str] = None,
    ma_tuyen: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Sơ đồ tuyến: nodes là điểm, edges là SỢI (cable_detail).
    from/to kế thừa từ đoạn cha. Mỗi sợi có thêm list_sid (array SID active).
    """
    if not tuyen_id and not ma_tuyen:
        raise ValueError("Cần truyền tuyen_id hoặc ma_tuyen.")

    parent_id = await _resolve_parent_id(db, tuyen_id, ma_tuyen)

    # Điểm → nodes
    points_cursor = db[COLLECTION_POINTS].find(
        {"parent_id": parent_id, "is_deleted": False},
    )
    points = await points_cursor.to_list(length=None)

    # Đoạn cáp → chỉ cần routing info + _id để map
    cable_query = (
        {"ma_tuyen": ma_tuyen, "is_deleted": False}
        if ma_tuyen
        else {"parent_id": parent_id, "is_deleted": False}
    )
    cables_cursor = db[COLLECTION_CABLES].find(
        cable_query,
        {"_id": 1, "start_point": 1, "end_point": 1,
         "start_point_text": 1, "end_point_text": 1},
    )
    cables = await cables_cursor.to_list(length=None)

    cable_map: Dict[str, Dict[str, Any]] = {
        c["_id"]: {
            "start_point":      c.get("start_point", ""),
            "end_point":        c.get("end_point", ""),
            "start_point_text": c.get("start_point_text", ""),
            "end_point_text":   c.get("end_point_text", ""),
        }
        for c in cables
    }
    cable_ids = list(cable_map.keys())

    # Sợi (cable_detail)
    fibers: List[Dict[str, Any]] = []
    if cable_ids:
        fibers_cursor = db[COLLECTION_CABLE_DETAIL].find(
            {"parent_id": {"$in": cable_ids}, "is_deleted": False},
        )
        fibers = await fibers_cursor.to_list(length=None)

    # SID: lấy toàn bộ SID active theo fiber_ids, group theo parent_id
    fiber_ids = [f["_id"] for f in fibers]
    sid_map: Dict[str, List[Dict[str, Any]]] = {}
    if fiber_ids:
        sid_cursor = db[COLLECTION_SID_CABLE].find(
            {"parent_id": {"$in": fiber_ids}, "is_deleted": False},
        )
        sids = await sid_cursor.to_list(length=None)
        for s in sids:
            pid = s.get("parent_id", "")
            sid_map.setdefault(pid, []).append(_clean_doc(s))

    # Build nodes
    nodes = []
    for p in points:
        pt = p.get("point_type")
        point_type_val = pt.get("value") if isinstance(pt, dict) else None
        custom = _clean_doc(p)
        custom["type"] = point_type_val or ""
        nodes.append({
            "id":    p["ma_diem"],
            "label": p.get("ten_diem", ""),
            "customData": custom,
        })

    # Build edges từ sợi
    edges = []
    for f in fibers:
        cable_parent = cable_map.get(f.get("parent_id"), {})
        from_point = cable_parent.get("start_point", "")
        to_point   = cable_parent.get("end_point", "")
        from_text  = cable_parent.get("start_point_text", "")
        to_text    = cable_parent.get("end_point_text", "")

        cable_number = f.get("cable_number", "")
        label = (
            f"{from_text} - {to_text} (sợi {cable_number})"
            if from_text or to_text
            else f"Sợi {cable_number}"
        )

        custom_edge = _clean_doc(f)
        # Thông tin routing từ đoạn cha
        custom_edge["_cable_start_point"]      = from_point
        custom_edge["_cable_end_point"]        = to_point
        custom_edge["_cable_start_point_text"] = from_text
        custom_edge["_cable_end_point_text"]   = to_text
        # Danh sách SID active thuộc sợi này
        custom_edge["list_sid"] = sid_map.get(str(f["_id"]), [])

        edges.append({
            "id":         str(f["_id"]),
            "from":       from_point,
            "to":         to_point,
            "label":      label,
            "customData": custom_edge,
        })

    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Use-case 6: Sơ đồ dịch vụ theo SID
# ---------------------------------------------------------------------------

COLLECTION_TUYEN_READ = "instance_data_hatang_quanlytuyen_newversion"


async def get_sid_diagram_data(
    db: AsyncIOMotorDatabase,
    sid_value: str,
) -> Dict[str, Any]:
    """
    Sơ đồ dịch vụ cho một SID cụ thể.
    Một SID có thể đi qua nhiều tuyến, nhiều sợi, nhiều đoạn.

    Luồng truy vết:
      SID.value
        → sid_cable (SID.value match, is_deleted=false)
        → cable_detail (_id = sid_cable.parent_id, is_deleted=false)
        → cable (_id = cable_detail.parent_id, is_deleted=false)
        → tuyen (_id = cable.parent_id)
        → điểm (parent_id = tuyen._id, is_deleted=false)

    Trả về:
      nodes: các điểm thuộc các tuyến mà SID đi qua
             customData gồm đầy đủ thông tin điểm + ten_tuyen, ma_tuyen của tuyến
      edges: các đoạn cáp mà SID đi qua
             customData gồm đầy đủ thông tin đoạn + fiber (sợi) + sid info
    """
    # ------------------------------------------------------------------
    # Bước 1: Tìm tất cả sid_cable có SID.value = sid_value
    # ------------------------------------------------------------------
    sid_docs_cursor = db[COLLECTION_SID_CABLE].find(
        {"SID.value": sid_value, "is_deleted": False},
        {"_id": 1, "parent_id": 1, "SID": 1, "ten_khach_hang": 1, "ma_tuyen": 1},
    )
    sid_docs = await sid_docs_cursor.to_list(length=None)

    if not sid_docs:
        return {"nodes": [], "edges": [], "sid": sid_value, "message": "Không tìm thấy SID."}

    fiber_ids = list({s["parent_id"] for s in sid_docs})

    # ------------------------------------------------------------------
    # Bước 2: Lấy cable_detail (sợi) từ fiber_ids
    # ------------------------------------------------------------------
    fibers_cursor = db[COLLECTION_CABLE_DETAIL].find(
        {"_id": {"$in": fiber_ids}, "is_deleted": False},
        {"_id": 1, "parent_id": 1, "cable_number": 1, "status": 1, "ma_tuyen": 1},
    )
    fibers = await fibers_cursor.to_list(length=None)

    cable_ids = list({f["parent_id"] for f in fibers})
    # map fiber_id → fiber doc
    fiber_map: Dict[str, Dict[str, Any]] = {f["_id"]: f for f in fibers}

    # ------------------------------------------------------------------
    # Bước 3: Lấy cable (đoạn) từ cable_ids
    # ------------------------------------------------------------------
    cables_cursor = db[COLLECTION_CABLES].find(
        {"_id": {"$in": cable_ids}, "is_deleted": False},
    )
    cables = await cables_cursor.to_list(length=None)

    tuyen_ids = list({c["parent_id"] for c in cables})
    # map cable_id → cable doc
    cable_map_full: Dict[str, Dict[str, Any]] = {c["_id"]: c for c in cables}

    # ------------------------------------------------------------------
    # Bước 4: Lấy thông tin tuyến
    # ------------------------------------------------------------------
    tuyen_cursor = db[COLLECTION_TUYEN_READ].find(
        {"_id": {"$in": tuyen_ids}},
        {"_id": 1, "ma_tuyen": 1, "ten_tuyen": 1},
    )
    tuyen_docs = await tuyen_cursor.to_list(length=None)
    tuyen_map: Dict[str, Dict[str, Any]] = {t["_id"]: t for t in tuyen_docs}

    # ------------------------------------------------------------------
    # Bước 5: Lấy tất cả điểm thuộc các tuyến đó
    # ------------------------------------------------------------------
    points_cursor = db[COLLECTION_POINTS].find(
        {"parent_id": {"$in": tuyen_ids}, "is_deleted": False},
    )
    all_points = await points_cursor.to_list(length=None)

    # ------------------------------------------------------------------
    # Bước 6: Build nodes - chỉ lấy điểm liên quan đến các đoạn SID đi qua
    # ------------------------------------------------------------------
    # Tập hợp ma_diem xuất hiện trong start_point/end_point của đoạn SID
    relevant_ma_diem: set = set()
    for c in cables:
        if c.get("start_point"):
            relevant_ma_diem.add(c["start_point"])
        if c.get("end_point"):
            relevant_ma_diem.add(c["end_point"])

    nodes = []
    seen_node_ids: set = set()
    for p in all_points:
        if p["ma_diem"] not in relevant_ma_diem:
            continue
        if p["ma_diem"] in seen_node_ids:
            continue
        seen_node_ids.add(p["ma_diem"])

        pt = p.get("point_type")
        point_type_val = pt.get("value") if isinstance(pt, dict) else None
        tuyen_info = tuyen_map.get(p.get("parent_id"), {})

        custom = _clean_doc(p)
        custom["type"]      = point_type_val or ""
        custom["ma_tuyen"]  = tuyen_info.get("ma_tuyen", "")
        custom["ten_tuyen"] = tuyen_info.get("ten_tuyen", "")

        nodes.append({
            "id":    p["ma_diem"],
            "label": p.get("ten_diem", ""),
            "customData": custom,
        })

    # ------------------------------------------------------------------
    # Bước 7: Build edges - mỗi đoạn cáp SID đi qua
    #         Gắn thêm fiber và sid info vào customData
    # ------------------------------------------------------------------
    # Build map sid_cable theo fiber_id để tra nhanh
    sid_by_fiber: Dict[str, List[Dict]] = {}
    for s in sid_docs:
        sid_by_fiber.setdefault(s["parent_id"], []).append(_clean_doc(s))

    edges = []
    seen_edge_ids: set = set()

    for sid_doc in sid_docs:
        fiber_id = sid_doc["parent_id"]
        fiber    = fiber_map.get(fiber_id)
        if not fiber:
            continue

        cable_id = fiber["parent_id"]
        cable    = cable_map_full.get(cable_id)
        if not cable:
            continue

        edge_id = cable.get("code") or cable_id
        # Có thể nhiều sợi/SID cùng đoạn → tạo edge riêng mỗi sợi
        edge_key = f"{edge_id}__fiber__{fiber_id}"
        if edge_key in seen_edge_ids:
            continue
        seen_edge_ids.add(edge_key)

        tuyen_info  = tuyen_map.get(cable.get("parent_id"), {})
        start_text  = cable.get("start_point_text") or ""
        end_text    = cable.get("end_point_text") or ""
        cable_num   = fiber.get("cable_number", "")
        label = (
            f"[{tuyen_info.get('ma_tuyen', '')}] "
            f"{start_text} - {end_text} (sợi {cable_num})"
        )

        custom_edge = _clean_doc(cable)
        custom_edge["ma_tuyen"]  = tuyen_info.get("ma_tuyen", "")
        custom_edge["ten_tuyen"] = tuyen_info.get("ten_tuyen", "")
        custom_edge["fiber"] = {
            "cable_number": fiber.get("cable_number"),
            "status":       fiber.get("status"),
            "ma_tuyen":     fiber.get("ma_tuyen"),
        }
        custom_edge["list_sid"] = sid_by_fiber.get(fiber_id, [])

        edges.append({
            "id":    edge_key,
            "from":  cable.get("start_point", ""),
            "to":    cable.get("end_point", ""),
            "label": label,
            "customData": custom_edge,
        })

    return {
        "sid":   sid_value,
        "nodes": nodes,
        "edges": edges,
    }