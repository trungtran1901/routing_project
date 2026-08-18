from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
import asyncpg
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.postgis import get_pg_pool
from app.core.database import get_database, COLLECTION_POINTS
from app.core.config import settings
from app.models.geo import SegmentGeometryUpdateRequest, PointGeometryUpdateRequest
from app.repositories import gis_repository
from app.services.gis_sync_service import run_full_sync
from app.services.gis_sid_service import build_sid_map_data, get_segment_sid_list, COLLECTION_TUYEN
from app.services.gis_point_service import update_point_location

router = APIRouter(prefix="/map", tags=["Map / GIS"])


def get_pool() -> asyncpg.pool.Pool:
    return get_pg_pool()


def get_db() -> AsyncIOMotorDatabase:
    return get_database()


def _point_row_to_response(row: dict) -> dict:
    return {
        "source_id": row["source_id"],
        "ma_diem": row["source_id"],
        "ten_diem": row.get("ten_diem"),
        "lat": row["lat"],
        "lng": row["lng"],
        "point_type": row.get("point_type"),
        "ma_tuyen": row.get("ma_tuyen"),
        "parent_id": row.get("parent_id"),
    }


def _segment_row_to_response(row: dict) -> dict:
    return {
        "source_id": row["source_id"],
        "start_point_id": row["start_point_id"],
        "end_point_id": row["end_point_id"],
        "ma_tuyen": row.get("ma_tuyen"),
        "parent_id": row.get("parent_id"),
        "geometry": row["geometry"],
        "geometry_source": row["geometry_source"],
        "geometry_version": row["geometry_version"],
    }


def _clamp_limit(limit: int) -> int:
    return min(limit, settings.GIS_MAX_RESULT_LIMIT)


def _zoom_to_simplify_tolerance(zoom: int) -> float:
    """
    Ước lượng tolerance (độ, SRID 4326) cho ST_SimplifyPreserveTopology dựa
    theo zoom Web Mercator chuẩn (không cần chính xác tuyệt đối - chỉ cần đủ
    hợp lý để giảm vertex ở zoom nhỏ mà không làm méo hình dạng ở zoom lớn).

    Công thức gần đúng: độ phân giải (mét/pixel) ở zoom z xấp xỉ
    156543 / 2^z (bỏ qua hệ số cos(lat) cho đơn giản - chấp nhận được vì đây
    chỉ là tolerance đơn giản hoá, không phải toạ độ hiển thị). Nhân với số
    pixel cho phép sai lệch (2px) rồi quy đổi thô sang độ (~111320 m/độ).
    """
    meters_per_pixel = 156543.03392 / (2 ** max(zoom, 0))
    tolerance_m = meters_per_pixel * 2  # cho phép lệch ~2px khi vẽ
    tolerance_deg = tolerance_m / 111320.0
    return tolerance_deg


# ---------------------------------------------------------------------------
# Points
# ---------------------------------------------------------------------------

@router.get("/points", summary="Danh sách điểm theo BBox (viewport), có gom cụm theo zoom")
async def list_points_bbox(
    min_lng: float = Query(..., description="Kinh độ nhỏ nhất viewport"),
    min_lat: float = Query(..., description="Vĩ độ nhỏ nhất viewport"),
    max_lng: float = Query(..., description="Kinh độ lớn nhất viewport"),
    max_lat: float = Query(..., description="Vĩ độ lớn nhất viewport"),
    zoom: Optional[int] = Query(None, description="Zoom level hiện tại (tham khảo, không bắt buộc để gom cụm)"),
    cluster: bool = Query(True, description="Gom cụm điểm theo lưới viewport (giống Google Maps). Tắt để luôn trả điểm thật."),
    grid_size: int = Query(
        None, ge=4, le=128,
        description="Số ô lưới mỗi chiều (NxN) dùng để gom cụm trên viewport hiện tại. Mặc định lấy theo config.",
    ),
    limit: int = Query(2000, ge=1, le=20000),
    pool: asyncpg.pool.Pool = Depends(get_pool),
):
    """
    Trả về danh sách điểm nằm trong viewport (BBox) để render lên Google Maps.
    Tận dụng spatial index GIST trên geo_points.geometry (toán tử &&).

    **Gom cụm (mặc định bật):** chia viewport thành lưới `grid_size x grid_size`
    ô đều nhau (giống marker clustering của Google Maps). Mỗi ô:
    - chỉ có 1 điểm -> trả về điểm thật (`type: "point"`)
    - có nhiều điểm -> gom thành 1 `type: "cluster"` (tâm trung bình + số
      lượng + bbox bao quanh để frontend `fitBounds` khi người dùng click
      vào cụm để zoom sâu hơn)

    Nhờ lưới chia theo chính viewport (không phải toạ độ tuyệt đối cố định),
    **kích thước response luôn bị chặn bởi `grid_size²`, không phụ thuộc số
    điểm thực tế** — giải quyết đúng vấn đề tải toàn bộ điểm khi zoom nhỏ.
    Khi viewport đã hẹp (zoom lớn), số điểm thực tế thường ít hơn số ô ->
    mỗi ô có đúng 1 điểm -> tự động trả điểm thật, không bị gom nữa.

    Truyền `cluster=false` để luôn nhận điểm thật không gom cụm (hành vi cũ).
    """
    if min_lng >= max_lng or min_lat >= max_lat:
        raise HTTPException(status_code=400, detail="BBox không hợp lệ (min phải nhỏ hơn max).")

    try:
        if not cluster:
            rows = await gis_repository.get_points_bbox(
                pool, min_lng, min_lat, max_lng, max_lat, _clamp_limit(limit)
            )
            return {"success": True, "data": [_point_row_to_response(r) for r in rows]}

        effective_grid_size = grid_size or settings.GIS_CLUSTER_DEFAULT_GRID_SIZE
        effective_grid_size = max(
            settings.GIS_CLUSTER_MIN_GRID_SIZE,
            min(effective_grid_size, settings.GIS_CLUSTER_MAX_GRID_SIZE),
        )
        rows = await gis_repository.get_points_bbox_clustered(
            pool, min_lng, min_lat, max_lng, max_lat,
            effective_grid_size, effective_grid_size,
            _clamp_limit(limit),
        )

        data = []
        for r in rows:
            if r["cnt"] <= 1:
                data.append({
                    "type": "point",
                    "source_id": r["sample_source_id"],
                    "ma_diem": r["sample_source_id"],
                    "ten_diem": r["sample_ten_diem"],
                    "lat": r["center_lat"],
                    "lng": r["center_lng"],
                    "point_type": r["sample_point_type"],
                    "ma_tuyen": r["sample_ma_tuyen"],
                    "parent_id": r["sample_parent_id"],
                })
            else:
                data.append({
                    "type": "cluster",
                    "count": r["cnt"],
                    "lat": r["center_lat"],
                    "lng": r["center_lng"],
                    "bbox": {
                        "min_lng": r["min_lng"], "min_lat": r["min_lat"],
                        "max_lng": r["max_lng"], "max_lat": r["max_lat"],
                    },
                    # ma_tuyen mẫu, chỉ để tham khảo hiển thị (cụm có thể gồm
                    # điểm của nhiều tuyến khác nhau)
                    "ma_tuyen": r["sample_ma_tuyen"],
                })
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")


@router.get("/points/{point_id}", summary="Chi tiết 1 điểm (geometry)")
async def get_point_detail(point_id: str, pool: asyncpg.pool.Pool = Depends(get_pool)):
    row = await gis_repository.get_point(pool, point_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy điểm '{point_id}' trong GIS layer.")
    return {"success": True, "data": _point_row_to_response(row)}


@router.put(
    "/points/{point_id}/geometry",
    summary="Cập nhật toạ độ điểm (ghi đồng thời MongoDB lẫn PostGIS)",
)
async def update_point_geometry_api(
    point_id: str,
    payload: PointGeometryUpdateRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    pool: asyncpg.pool.Pool = Depends(get_pool),
):
    """
    Cập nhật vị trí (lat/lng) của 1 điểm, ví dụ khi người dùng kéo marker
    trên Google Maps để chỉnh lại toạ độ chính xác hơn.

    KHÁC với cập nhật geometry đoạn cáp (chỉ ghi PostGIS): cập nhật điểm phải
    ghi **cả MongoDB** (`vi_do`/`kinh_do` - nguồn dữ liệu nghiệp vụ chính,
    được các API routing khác dùng) **lẫn PostGIS** (`geo_points.geometry` -
    dùng cho spatial query/hiển thị map), để 2 nơi luôn khớp nhau.

    Sau khi cập nhật, **mọi đoạn cáp nối tới điểm này sẽ dịch chuyển theo
    ngay lập tức** - cả đoạn `AUTO` lẫn đoạn đã ở chế độ `USER` (đã tự chỉnh
    tay). Với đoạn `USER`, chỉ đúng đầu mút trùng với điểm này được dịch
    chuyển; các điểm uốn ở giữa (hình dạng người dùng đã tự vẽ) được **giữ
    nguyên**. Danh sách các đoạn đã cập nhật trả về trong `refreshed_segments`
    (kèm `geometry_source` của từng đoạn để biết đoạn nào chỉ bị "khớp lại
    đầu mút" thay vì vẽ lại toàn bộ).
    """
    lng, lat = payload.geometry.coordinates[0], payload.geometry.coordinates[1]
    modified_fields = {
        "modified_by_id": payload.modified_by_id,
        "modified_by_name": payload.modified_by_name,
        "modified_by_fullname": payload.modified_by_fullname,
        "modified_by_email": payload.modified_by_email,
    }

    try:
        result = await update_point_location(db, pool, point_id, lng, lat, modified_fields)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")

    return {
        "success": True,
        "data": {
            "point": _point_row_to_response(result["point"]),
            "refreshed_segments": result["refreshed_segments"],
        },
    }


# ---------------------------------------------------------------------------
# Segments
# ---------------------------------------------------------------------------

@router.get("/segments", summary="Danh sách đoạn cáp theo BBox (viewport)")
async def list_segments_bbox(
    min_lng: float = Query(...),
    min_lat: float = Query(...),
    max_lng: float = Query(...),
    max_lat: float = Query(...),
    zoom: Optional[int] = Query(None, description="Zoom level hiện tại - dùng để tự ẩn/đơn giản hoá đường dây khi zoom nhỏ"),
    simplify: bool = Query(True, description="Tự đơn giản hoá geometry (giảm vertex) theo zoom. Tắt để luôn nhận geometry gốc."),
    limit: int = Query(2000, ge=1, le=20000),
    pool: asyncpg.pool.Pool = Depends(get_pool),
):
    """
    Trả về các đoạn cáp (LineString GeoJSON) nằm trong viewport để vẽ polyline.

    **Khác với điểm, đường (LineString) không thể gom cụm thành 1 hình đại
    diện** như cách gom điểm (không có khái niệm "đường trung bình" hợp lý).
    Thay vào đó áp dụng 2 kỹ thuật khi zoom nhỏ (bắt buộc phải truyền `zoom`
    để 2 kỹ thuật này có tác dụng):

    1. **Ẩn hoàn toàn khi zoom < `GIS_SEGMENTS_MIN_ZOOM_TO_LOAD`** (mặc định
       12) — ở mức toàn quốc/toàn tỉnh, hàng trăm nghìn đoạn cáp gần như chỉ
       là các điểm ảnh chồng lên nhau, không có giá trị hiển thị và cực kỳ
       tốn băng thông. Trả về rỗng kèm `message` để frontend biết cần zoom
       gần hơn (khuyến nghị: ở mức zoom này chỉ hiển thị `/map/points` gom
       cụm để người dùng thấy "mật độ hạ tầng ở đâu", chưa cần vẽ đường).
    2. **Tự đơn giản hoá geometry** (`ST_SimplifyPreserveTopology`) theo zoom
       khi đã đủ zoom để tải — giảm số vertex của các đoạn `USER` (tự vẽ tay,
       nhiều điểm uốn) mà không đổi hình dạng đáng kể ở độ phân giải hiển thị
       đó. Đoạn `AUTO` (chỉ 2 điểm) không bị ảnh hưởng.

    Nếu không truyền `zoom`, endpoint giữ hành vi cũ (trả nguyên bản, không
    ẩn/không đơn giản hoá) — dùng cho các trường hợp cần dữ liệu đầy đủ như
    `/map/routes`.
    """
    if min_lng >= max_lng or min_lat >= max_lat:
        raise HTTPException(status_code=400, detail="BBox không hợp lệ (min phải nhỏ hơn max).")

    if zoom is not None and zoom < settings.GIS_SEGMENTS_MIN_ZOOM_TO_LOAD:
        return {
            "success": True,
            "data": [],
            "message": (
                f"Zoom hiện tại ({zoom}) nhỏ hơn mức tối thiểu để tải đường dây "
                f"({settings.GIS_SEGMENTS_MIN_ZOOM_TO_LOAD}). Hiển thị /map/points "
                f"(gom cụm) thay vì đường dây ở mức zoom này."
            ),
        }

    tolerance = None
    if simplify and settings.GIS_SEGMENTS_AUTO_SIMPLIFY and zoom is not None:
        tolerance = _zoom_to_simplify_tolerance(zoom)

    try:
        rows = await gis_repository.get_segments_bbox(
            pool, min_lng, min_lat, max_lng, max_lat, _clamp_limit(limit),
            simplify_tolerance=tolerance,
        )
        return {"success": True, "data": [_segment_row_to_response(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")


@router.get(
    "/segments/{segment_id}",
    summary="Chi tiết đoạn cáp (segment + start/end point + geometry + danh sách SID)",
)
async def get_segment_detail(
    segment_id: str,
    pool: asyncpg.pool.Pool = Depends(get_pool),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Trả chi tiết 1 đoạn cáp để hiển thị khi click vào segment trên map, bao
    gồm cả `sid_list` - danh sách toàn bộ SID (dịch vụ khách hàng) đang active
    trên các sợi (cable_detail) thuộc đoạn cáp này. `sid_list` lấy trực tiếp
    từ MongoDB (không cần đồng bộ sang PostGIS vì đây là business data, không
    phải geometry).
    """
    segment = await gis_repository.get_segment(pool, segment_id)
    if not segment:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy đoạn cáp '{segment_id}' trong GIS layer.")

    start_point = await gis_repository.get_point(pool, segment["start_point_id"])
    end_point = await gis_repository.get_point(pool, segment["end_point_id"])
    sid_list = await get_segment_sid_list(db, segment_id)

    return {
        "success": True,
        "data": {
            "segment": _segment_row_to_response(segment),
            "start_point": _point_row_to_response(start_point) if start_point else None,
            "end_point": _point_row_to_response(end_point) if end_point else None,
            "sid_list": sid_list,
            "sid_count": len(sid_list),
            "editable": True,
        },
    }


@router.get("/segments/{segment_id}/geometry", summary="Lấy riêng geometry (GeoJSON) của đoạn cáp")
async def get_segment_geometry(segment_id: str, pool: asyncpg.pool.Pool = Depends(get_pool)):
    segment = await gis_repository.get_segment(pool, segment_id)
    if not segment:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy đoạn cáp '{segment_id}' trong GIS layer.")
    return {
        "success": True,
        "data": {
            "source_id": segment["source_id"],
            "geometry": segment["geometry"],
            "geometry_source": segment["geometry_source"],
            "geometry_version": segment["geometry_version"],
        },
    }


@router.put("/segments/{segment_id}/geometry", summary="Cập nhật geometry đoạn cáp (từ Google Maps editor)")
async def update_segment_geometry(
    segment_id: str,
    payload: SegmentGeometryUpdateRequest,
    pool: asyncpg.pool.Pool = Depends(get_pool),
):
    """
    Cập nhật geometry (LineString) của 1 đoạn cáp sau khi người dùng chỉnh sửa
    trên Google Maps.

    Validate (ngoài Pydantic validator đã kiểm tra type/số lượng coordinate/
    khoảng giá trị lng-lat hợp lệ):
    - segment phải tồn tại trong GIS layer (start/end point coi như đã tồn
      tại vì segment chỉ được sync sau khi cả 2 điểm có tọa độ hợp lệ).
    - nếu expected_version được truyền, phải khớp version hiện tại (optimistic
      locking) để tránh 2 người ghi đè chồng nhau.

    geometry_version sẽ tự động += 1 sau mỗi lần update thành công.
    """
    coords = payload.geometry.coordinates
    try:
        result = await gis_repository.update_segment_geometry(
            pool,
            source_id=segment_id,
            coordinates=coords,
            geometry_source=payload.geometry_source,
            expected_version=payload.expected_version,
        )
    except ValueError as e:
        # version mismatch
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")

    if result is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy đoạn cáp '{segment_id}' trong GIS layer.")

    return {"success": True, "data": _segment_row_to_response(result)}


# ---------------------------------------------------------------------------
# Routes (tuyến) - trả riêng điểm + đoạn cáp của 1 tuyến, không lẫn tuyến khác
# ---------------------------------------------------------------------------

async def _resolve_tuyen_id(db: AsyncIOMotorDatabase, tuyen_id: Optional[str], ma_tuyen: Optional[str]) -> str:
    """Trả về parent_id (tuyến._id) từ tuyen_id hoặc ma_tuyen. Giống cách
    routing_service._resolve_parent_id đang làm, để 2 nơi hành xử nhất quán."""
    if tuyen_id:
        return tuyen_id
    sample = await db[COLLECTION_POINTS].find_one(
        {"ma_tuyen": ma_tuyen, "is_deleted": False}, {"parent_id": 1},
    )
    if not sample:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy tuyến với mã '{ma_tuyen}'.")
    return sample["parent_id"]


@router.get(
    "/routes",
    summary="Điểm + đoạn cáp của riêng 1 tuyến (để hiển thị tách biệt, không lẫn tuyến khác)",
)
async def get_route_map(
    tuyen_id: Optional[str] = Query(None, description="ID tuyến (parent_id)"),
    ma_tuyen: Optional[str] = Query(None, description="Mã tuyến"),
    pool: asyncpg.pool.Pool = Depends(get_pool),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Truyền **một trong hai** `tuyen_id` hoặc `ma_tuyen`. Trả về toàn bộ điểm
    và đoạn cáp (geometry) CHỈ thuộc tuyến đó, để frontend render riêng 1
    tuyến trên map (ẩn hết các tuyến khác) khi người dùng chọn 1 tuyến từ
    kết quả /map/search hoặc từ danh sách tuyến.

    Không phân trang theo viewport (khác /map/points, /map/segments) vì mục
    đích là xem toàn bộ 1 tuyến / zoom-to-fit, không phải duyệt bản đồ rộng.
    """
    if not tuyen_id and not ma_tuyen:
        raise HTTPException(status_code=400, detail="Cần truyền tuyen_id hoặc ma_tuyen.")

    resolved_tuyen_id = await _resolve_tuyen_id(db, tuyen_id, ma_tuyen)

    points = await gis_repository.get_points_by_parent(pool, resolved_tuyen_id)
    segments = await gis_repository.get_segments_by_parent(pool, resolved_tuyen_id)

    if not points and not segments:
        raise HTTPException(
            status_code=404,
            detail=f"Tuyến '{resolved_tuyen_id}' chưa có dữ liệu trong GIS layer (có thể cần chạy /map/sync).",
        )

    return {
        "success": True,
        "data": {
            "tuyen_id": resolved_tuyen_id,
            "points": [_point_row_to_response(r) for r in points],
            "segments": [_segment_row_to_response(r) for r in segments],
        },
    }


@router.get("/routes/{route_id}", summary="[Alias] Giống GET /map/routes?tuyen_id={route_id}", deprecated=True)
async def get_route_map_by_path(
    route_id: str,
    pool: asyncpg.pool.Pool = Depends(get_pool),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Giữ lại để tương thích ngược. Dùng GET /map/routes?tuyen_id=... hoặc ?ma_tuyen=... thay thế."""
    return await get_route_map(tuyen_id=route_id, ma_tuyen=None, pool=pool, db=db)


# ---------------------------------------------------------------------------
# Nearby
# ---------------------------------------------------------------------------

@router.get("/nearby", summary="Tìm điểm/đoạn cáp gần một vị trí")
async def nearby(
    lat: float = Query(...),
    lng: float = Query(...),
    radius: float = Query(500, gt=0, description="Bán kính tìm kiếm (mét)"),
    include: str = Query("points,segments", description="Danh sách 'points' và/hoặc 'segments', phân cách bởi dấu phẩy"),
    limit: int = Query(50, ge=1, le=500),
    pool: asyncpg.pool.Pool = Depends(get_pool),
):
    if radius > settings.GIS_NEARBY_MAX_RADIUS_M:
        raise HTTPException(
            status_code=400,
            detail=f"radius vượt quá giới hạn cho phép ({settings.GIS_NEARBY_MAX_RADIUS_M}m).",
        )

    include_set = {s.strip() for s in include.split(",") if s.strip()}
    result = {}

    try:
        if "points" in include_set:
            rows = await gis_repository.nearby_points(pool, lat, lng, radius, limit)
            result["points"] = [
                {**_point_row_to_response(r), "distance_m": round(r["distance_m"], 2)} for r in rows
            ]
        if "segments" in include_set:
            rows = await gis_repository.nearby_segments(pool, lat, lng, radius, limit)
            result["segments"] = [
                {
                    "source_id": r["source_id"],
                    "start_point_id": r["start_point_id"],
                    "end_point_id": r["end_point_id"],
                    "ma_tuyen": r.get("ma_tuyen"),
                    "distance_m": round(r["distance_m"], 2),
                }
                for r in rows
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")

    return {"success": True, "data": result}


# ---------------------------------------------------------------------------
# Search (Mongo cho business search, PostGIS chỉ bổ sung tọa độ)
# ---------------------------------------------------------------------------

@router.get(
    "/search",
    summary="Tìm điểm và/hoặc tuyến theo ma_diem / ten_diem / ma_tuyen / ten_tuyen",
)
async def search(
    q: str = Query(..., min_length=1, description="Từ khóa: mã điểm, tên điểm, mã tuyến, hoặc tên tuyến"),
    type: str = Query(
        "point,route",
        description="Loại kết quả cần tìm: 'point', 'route', hoặc 'point,route' (mặc định cả 2)",
    ),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_db),
    pool: asyncpg.pool.Pool = Depends(get_pool),
):
    """
    MongoDB là nguồn tìm kiếm chính xác nhất cho business data. PostGIS chỉ
    dùng để lấy tọa độ (geometry) cho các kết quả tìm được.

    Trả 2 loại kết quả:
    - `type: "point"` — điểm khớp `ma_diem`/`ten_diem`/`ma_tuyen`, có sẵn `lat`/`lng`.
      Nếu khớp qua `ma_tuyen` thì nhiều điểm cùng tuyến sẽ ra nhiều kết quả -
      dùng để nhảy/zoom tới 1 điểm cụ thể, KHÔNG phải cách đúng để "xem cả
      tuyến" (dễ nhầm với các tuyến khác đi qua khu vực gần đó).
    - `type: "route"` — tuyến khớp `ma_tuyen`/`ten_tuyen`, trả về `source_id`
      (= parent_id của tuyến) để gọi tiếp `GET /map/routes?tuyen_id=...`
      hoặc `?ma_tuyen=...` — đây là cách đúng để hiển thị **riêng 1 tuyến**
      trên map mà không lẫn tuyến khác.
    """
    include_types = {t.strip() for t in type.split(",") if t.strip()}
    results: List[dict] = []

    try:
        if "point" in include_types:
            cursor = db[COLLECTION_POINTS].find(
                {
                    "is_deleted": False,
                    "$or": [
                        {"ma_diem": {"$regex": q, "$options": "i"}},
                        {"ten_diem": {"$regex": q, "$options": "i"}},
                        {"ma_tuyen": {"$regex": q, "$options": "i"}},
                    ],
                },
                {"ma_diem": 1, "ten_diem": 1, "ma_tuyen": 1},
            ).limit(limit)
            matched_points: List[dict] = await cursor.to_list(length=limit)

            ma_diem_list = [p["ma_diem"] for p in matched_points if p.get("ma_diem")]
            geo_rows = await gis_repository.get_points_by_ids(pool, ma_diem_list)
            geo_by_id = {r["source_id"]: r for r in geo_rows}

            for p in matched_points:
                ma_diem = p.get("ma_diem")
                geo = geo_by_id.get(ma_diem)
                results.append({
                    "type": "point",
                    "source_id": ma_diem,
                    "label": p.get("ten_diem") or ma_diem,
                    "ma_tuyen": p.get("ma_tuyen"),
                    "lat": geo["lat"] if geo else None,
                    "lng": geo["lng"] if geo else None,
                })

        if "route" in include_types:
            cursor = db[COLLECTION_TUYEN].find(
                {
                    "$or": [
                        {"ma_tuyen": {"$regex": q, "$options": "i"}},
                        {"ten_tuyen": {"$regex": q, "$options": "i"}},
                    ],
                },
                {"ma_tuyen": 1, "ten_tuyen": 1},
            ).limit(limit)
            matched_routes: List[dict] = await cursor.to_list(length=limit)

            for t in matched_routes:
                results.append({
                    "type": "route",
                    "source_id": t["_id"],  # = tuyen_id, dùng cho GET /map/routes?tuyen_id=...
                    "label": t.get("ten_tuyen") or t.get("ma_tuyen") or t["_id"],
                    "ma_tuyen": t.get("ma_tuyen"),
                    "lat": None,
                    "lng": None,
                })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi truy vấn MongoDB: {str(e)}")

    return {"success": True, "data": results}


# ---------------------------------------------------------------------------
# SID map - chế độ xem map theo 1 SID cụ thể
# ---------------------------------------------------------------------------

@router.get(
    "/sid/{sid_value}",
    summary="Sơ đồ map theo SID: các điểm + đoạn cáp (geometry thật) mà SID đi qua",
)
async def get_sid_map(
    sid_value: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    pool: asyncpg.pool.Pool = Depends(get_pool),
):
    """
    Tương tự luồng truy vết của `GET /routing/diagram/sid`
    (SID → sid_cable → cable_detail/sợi → cable/đoạn → tuyến → điểm), nhưng
    dùng cho chế độ xem MAP: trả `nodes` có sẵn `lat`/`lng` và `edges` có sẵn
    `geometry` (LineString GeoJSON thật lấy từ PostGIS, không phải chỉ label).

    Mỗi đoạn cáp (cable) chỉ xuất hiện 1 lần trong `edges` (gộp theo cable_id)
    dù có nhiều sợi/SID cùng đi qua, kèm `list_sid` liệt kê các SID đó -
    tránh vẽ trùng nhiều polyline chồng lên nhau trên cùng 1 đoạn.

    Nếu đoạn cáp chưa được đồng bộ sang PostGIS (`/map/sync` chưa chạy),
    `geometry` sẽ là đường thẳng tạm nối 2 điểm (giống quy tắc AUTO), kèm
    `geometry_source: "AUTO"` để frontend biết đây là geometry ước lượng.
    """
    try:
        result = await build_sid_map_data(db, pool, sid_value)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")


# ---------------------------------------------------------------------------
# Sync (vận hành / admin) - trigger đồng bộ Mongo -> PostGIS
# ---------------------------------------------------------------------------

@router.post(
    "/sync",
    summary="Đồng bộ (projection) dữ liệu Point/Cable từ MongoDB sang PostGIS",
)
async def trigger_sync(
    db: AsyncIOMotorDatabase = Depends(get_db),
    pool: asyncpg.pool.Pool = Depends(get_pool),
):
    """
    Chạy đồng bộ toàn bộ điểm + đoạn cáp active từ MongoDB sang GIS layer.
    Idempotent (upsert theo source_id) - an toàn để gọi lại nhiều lần, kể cả
    trong lúc production đang chạy. KHÔNG thay đổi bất kỳ dữ liệu nào trong
    MongoDB.

    Cho dataset lớn, khuyến nghị chạy qua script CLI (scripts/gis_initial_sync.py)
    thay vì gọi qua HTTP để tránh timeout request.
    """
    try:
        result = await run_full_sync(db, pool)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")