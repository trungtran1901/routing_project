from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_database
from app.models.point import PointCreateRequest, PointDeleteRequest
from app.services.routing_service import process_add_point, handle_delete_point, get_diagram_data, get_fiber_diagram_data, get_sid_diagram_data
from app.models.cable import CableSyncRequest
from app.services.cable_detail_service import sync_cable_detail
router = APIRouter(prefix="/routing", tags=["Routing"])


def get_db() -> AsyncIOMotorDatabase:
    return get_database()


@router.post("/points", summary="Thêm mới điểm vào tuyến (cuối hoặc chèn giữa)")
async def add_point(
    payload: PointCreateRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Thêm mới một điểm vào tuyến và tự động xử lý routing:

    - **start_point = null/bỏ trống**: Thêm điểm vào **cuối** tuyến.
      Tạo 1 đoạn cáp mới nối từ điểm cuối hiện tại đến điểm mới.

    - **start_point có giá trị** (ma_diem của điểm trước): **Chèn vào giữa**.
      Vô hiệu hóa đoạn cũ, tạo 2 đoạn mới.
    """
    try:
        result = await process_add_point(db, payload)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")


@router.post("/points/delete", summary="Vô hiệu hóa đoạn cáp khi xóa điểm")
async def delete_point(
    payload: PointDeleteRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Khi điểm bị xóa, vô hiệu hóa tất cả đoạn cáp liên quan và nối lại A→C
    nếu điểm bị xóa nằm giữa 2 điểm.

    - Điểm ở **cuối tuyến**: vô hiệu hóa 1 đoạn, không tạo thêm.
    - Điểm ở **giữa tuyến**: vô hiệu hóa 2 đoạn, tạo 1 đoạn nối mới A→C.
    """
    try:
        result = await handle_delete_point(db, payload)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")


@router.get("/diagram", summary="Lấy dữ liệu sơ đồ tuyến (nodes + edges)")
async def get_diagram(
    tuyen_id: Optional[str] = Query(None, description="ID tuyến (so sánh theo parent_id)"),
    ma_tuyen: Optional[str] = Query(None, description="Mã tuyến (so sánh theo ma_tuyen của điểm)"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Trả về dữ liệu sơ đồ tuyến dạng nodes + edges để render biểu đồ.

    Truyền **một trong hai** tham số:
    - `tuyen_id`: truy vấn trực tiếp theo `parent_id` của điểm và đoạn.
    - `ma_tuyen`: tìm `parent_id` từ điểm có `ma_tuyen` tương ứng, rồi truy vấn đoạn.

    Chỉ lấy dữ liệu có `is_deleted = false`.

    **Cấu trúc trả về:**
    ```json
    {
      "nodes": [
        { "id": "AGG001", "label": "Long Xuyên", "customData": { "type": "Trạm" } }
      ],
      "edges": [
        { "id": "MX004-MX005", "from": "MX004", "to": "MX005", "label": "Măng xông 1 - Măng xông 2" }
      ]
    }
    ```
    """
    if not tuyen_id and not ma_tuyen:
        raise HTTPException(status_code=400, detail="Cần truyền tuyen_id hoặc ma_tuyen.")
    try:
        result = await get_diagram_data(db, tuyen_id=tuyen_id, ma_tuyen=ma_tuyen)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")


# ---------------------------------------------------------------------------
# Cable detail sync endpoint
# --------------------------------------------------------------------------


@router.post("/sync-cable", summary="Đồng bộ cable_detail theo total_cable")
async def sync_cable_detail_api(
    payload: CableSyncRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Đồng bộ số lượng bản ghi `cable_detail` theo trường `total_cable` của đoạn cáp.

    **Các trường hợp xử lý:**
    - `total_cable = 0` → bỏ qua.
    - Chưa có bản ghi nào → tạo mới `total_cable` bản ghi (cable_number 1..N).
    - Số bản ghi == total_cable → đã đủ, bỏ qua.
    - Số bản ghi > total_cable → soft-delete các bản ghi dư (cable_number > N) và SID liên quan.
    - Số bản ghi < total_cable → thêm mới các bản ghi còn thiếu.

    Sau mỗi thay đổi, cập nhật lại `available_cable` trên đoạn cáp
    (= số cable_detail có status **Không sử dụng** và is_deleted = false).
    """
    try:
        result = await sync_cable_detail(db, payload)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")
    
# ---------------------------------------------------------------------------
# Fiber status update endpoint
# ---------------------------------------------------------------------------
from app.models.sid import SIDCableRequest
from app.services.sid_service import update_fiber_status
 
 
@router.post("/cables/update-fiber-status", summary="Cập nhật trạng thái sợi theo SID")
async def update_fiber_status_api(
    payload: SIDCableRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Cập nhật trạng thái sợi trong `cable_detail` sau khi SID được gắn vào.
 
    **Luồng xử lý:**
    - `parent_id` trong payload = `_id` của `cable_detail` cần cập nhật.
    - Đếm số SID active (`is_deleted=false`) trong `sid_cable` có `parent_id` đó.
    - Nếu count > 0:
        - Cập nhật `total_sid = count`.
        - Nếu `status.value == "Không sử dụng"` → đổi sang **"Đang hoạt động"**.
    - Tính lại `available_cable` trên đoạn cáp cha.
    """
    try:
        result = await update_fiber_status(db, payload)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")
    
# ---------------------------------------------------------------------------
# Cable status update endpoint
# ---------------------------------------------------------------------------
from app.models.cable_detail import CableDetailStatusRequest
from app.services.cable_status_service import update_cable_status
 
 
@router.post("/cables/update-status", summary="Cập nhật thống kê trạng thái đoạn cáp")
async def update_cable_status_api(
    payload: CableDetailStatusRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Cập nhật các trường thống kê trên **đoạn cáp** (`cable`) dựa vào
    toàn bộ `cable_detail` và `sid_cable` thuộc đoạn cáp đó.
 
    **Luồng xử lý:**
    - `parent_id` trong payload = `_id` của **cable cha** cần cập nhật.
    - Truy vấn tất cả `cable_detail` (`is_deleted=false`) thuộc cable cha.
    - Đếm:
        - `error_cable` = số sợi có `status.value == "Lỗi"`
        - `used_cable`  = số sợi có `status.value == "Đang sử dụng"`
    - Lấy toàn bộ `_id` của các `cable_detail` → truy vấn `sid_cable`.
    - Đếm tổng SID (`sid_total`) và SID unique theo `SID.value` (`sid_unique`).
    - Cập nhật lên cable: `error_cable`, `used_cable`, `so_luong_sid`, `total_sid_raw`.
    """
    try:
        result = await update_cable_status(db, payload)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")
    
# ---------------------------------------------------------------------------
# Tuyen stats update endpoint
# ---------------------------------------------------------------------------
from app.models.tuyen import TuyenStatsRequest
from app.services.tuyen_stats_service import update_tuyen_stats
 
 
@router.post("/tuyen/update-stats", summary="Tính toán và cập nhật thống kê tuyến")
async def update_tuyen_stats_api(
    payload: TuyenStatsRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Tính toán lại các trường thống kê trên **tuyến chính** từ toàn bộ đoạn cáp thuộc tuyến.
 
    **Đầu vào:** một đoạn cáp (`cable`) thuộc tuyến — dùng `parent_id` để xác định tuyến.
 
    **Các trường được cập nhật trên tuyến:**
    - `so_luong_link_mang_kh` = tổng `so_luong_sid` của tất cả cable.
    - `chieu_dai_km`          = tổng `length_cable` của tất cả cable.
    - `so_soi_kha_dung_hitc`  = `available_cable` của cable có `total_cable` nhỏ nhất
      (nếu nhiều cable cùng min thì lấy cable có `available_cable` nhỏ nhất trong nhóm).
    - `so_soi_su_dung`        = `used_cable` của cable nói trên.
    """
    try:
        result = await update_tuyen_stats(db, payload)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")
    
@router.get("/diagram/fiber", summary="Sơ đồ tuyến theo sợi (cable_detail là edge)")
async def get_fiber_diagram(
    tuyen_id: Optional[str] = Query(None, description="ID tuyến (so sánh theo parent_id)"),
    ma_tuyen: Optional[str] = Query(None, description="Mã tuyến (so sánh theo ma_tuyen)"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Trả về sơ đồ tuyến trong đó mỗi **edge là một sợi** (`cable_detail`),
    không phải đoạn cáp.
 
    - `from` / `to` của edge kế thừa từ `start_point` / `end_point` của đoạn cáp cha.
    - Một cặp điểm có thể có nhiều edge (nhiều sợi).
    - `id` của edge = `_id` của sợi.
    - `label` = `"start_text - end_text (sợi N)"`.
    - `customData` chứa toàn bộ fields của sợi + các trường `_cable_*` từ đoạn cha.
 
    Chỉ lấy dữ liệu `is_deleted = false` ở tất cả các tầng.
    """
    if not tuyen_id and not ma_tuyen:
        raise HTTPException(status_code=400, detail="Cần truyền tuyen_id hoặc ma_tuyen.")
    try:
        result = await get_fiber_diagram_data(db, tuyen_id=tuyen_id, ma_tuyen=ma_tuyen)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")
    
@router.get("/diagram/sid", summary="Sơ đồ dịch vụ theo SID")
async def get_sid_diagram(
    sid: str = Query(..., description="Giá trị SID cần tra cứu (VD: AMS0924001)"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Trả về sơ đồ dịch vụ cho một **SID** cụ thể.
 
    Một SID có thể đi qua nhiều tuyến, nhiều sợi, nhiều đoạn.
 
    **Luồng truy vết:**
    ```
    SID.value
      → sid_cable              (SID.value match)
      → cable_detail / sợi    (parent_id = sid_cable.parent_id)
      → cable / đoạn          (parent_id = cable_detail.parent_id)
      → tuyen                 (parent_id = cable.parent_id)
      → điểm                  (parent_id = tuyen._id)
    ```
 
    **Nodes:** các điểm thuộc đoạn SID đi qua.
    `customData` có thêm `ma_tuyen`, `ten_tuyen` của tuyến chứa điểm đó.
 
    **Edges:** mỗi edge = 1 sợi mà SID đi qua (có thể nhiều sợi cùng đoạn).
    `customData` có thêm `ma_tuyen`, `ten_tuyen`, `fiber` (thông tin sợi), `list_sid`.
 
    `label` = `[ma_tuyen] start_text - end_text (sợi N)`
    """
    try:
        result = await get_sid_diagram_data(db, sid_value=sid)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")