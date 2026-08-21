from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_database
from app.core.postgis import get_pg_pool
from app.models.point import PointCreateRequest, PointDeleteRequest
from app.services.routing_service import process_add_point, handle_delete_point, get_diagram_data, get_fiber_diagram_data, get_sid_diagram_data
from app.services.gis_incremental_sync import sync_route_scope
from app.models.cable import CableSyncRequest
from app.services.cable_detail_service import sync_cable_detail
router = APIRouter(prefix="/routing", tags=["Routing"])


def get_db() -> AsyncIOMotorDatabase:
    return get_database()


def _get_pool_or_none():
    try:
        return get_pg_pool()
    except RuntimeError:
        return None


async def _trigger_gis_incremental_sync(db: AsyncIOMotorDatabase, parent_id: str) -> None:
    try:
        pool = get_pg_pool()
    except RuntimeError as e:
        print(f"[WARN] Bỏ qua GIS incremental sync (PostGIS chưa sẵn sàng): {e}")
        return
    try:
        await sync_route_scope(db, pool, parent_id)
    except Exception as e:
        print(f"[WARN] GIS incremental sync thất bại cho tuyến '{parent_id}' (không ảnh hưởng routing): {e}")


@router.post("/points", summary="Thêm mới điểm vào tuyến (cuối hoặc chèn giữa)")
async def add_point(
    payload: PointCreateRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    try:
        result = await process_add_point(db, payload)
        await _trigger_gis_incremental_sync(db, payload.parent_id)
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
    try:
        result = await handle_delete_point(db, payload)
        await _trigger_gis_incremental_sync(db, payload.parent_id)
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
    if not tuyen_id and not ma_tuyen:
        raise HTTPException(status_code=400, detail="Cần truyền tuyen_id hoặc ma_tuyen.")
    try:
        result = await get_diagram_data(db, tuyen_id=tuyen_id, ma_tuyen=ma_tuyen)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")


@router.post("/sync-cable", summary="Đồng bộ cable_detail theo total_cable")
async def sync_cable_detail_api(
    payload: CableSyncRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    try:
        result = await sync_cable_detail(db, payload)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")

from app.models.sid import SIDCableRequest
from app.services.sid_service import update_fiber_status


@router.post("/cables/update-fiber-status", summary="Cập nhật trạng thái sợi theo SID")
async def update_fiber_status_api(
    payload: SIDCableRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    try:
        result = await update_fiber_status(db, payload)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")

from app.models.cable_detail import CableDetailStatusRequest
from app.services.cable_status_service import update_cable_status


@router.post("/cables/update-status", summary="Cập nhật thống kê trạng thái đoạn cáp")
async def update_cable_status_api(
    payload: CableDetailStatusRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    try:
        result = await update_cable_status(db, payload)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")

from app.models.tuyen import TuyenStatsRequest
from app.services.tuyen_stats_service import update_tuyen_stats


@router.post("/tuyen/update-stats", summary="Tính toán và cập nhật thống kê tuyến")
async def update_tuyen_stats_api(
    payload: TuyenStatsRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    try:
        pool = _get_pool_or_none()
        result = await update_tuyen_stats(db, payload, pool=pool)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")

@router.get("/diagram/fiber", summary="Sơ đồ tuyến theo sợi (cable_detail là edge)")
async def get_fiber_diagram(
    tuyen_id: Optional[str] = Query(None, description="ID tuyến (so sánh theo parent_id)"),
    ma_tuyen: Optional[str] = Query(None, description="Mã tuyến (so sánh theo ma_tuyen)"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
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
    try:
        result = await get_sid_diagram_data(db, sid_value=sid)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")