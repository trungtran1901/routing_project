from pydantic import BaseModel, Field
from typing import Optional, Any, Dict
from datetime import datetime


class SIDOptionModel(BaseModel):
    ten_khach_hang: Optional[str] = None


class SIDRefModel(BaseModel):
    label: Optional[str] = None
    value: Optional[str] = None
    data_source: Optional[str] = None
    view_to_open_link: Optional[Any] = None
    display_member: Optional[str] = None
    value_member: Optional[str] = None
    option: Optional[Dict] = {}
    _id: Optional[str] = None


class SIDCableRequest(BaseModel):
    """Payload dữ liệu SID cable truyền vào API cập nhật trạng thái sợi."""
    id: str = Field(..., alias="_id")
    SID: Optional[SIDRefModel] = None
    ten_khach_hang: Optional[str] = None
    link_vi_tri_trien_khai: Optional[Any] = None
    dia_chi_dich_vu_diem_dau: Optional[Any] = None
    parent_id: str  # _id của cable_detail cha
    ma_tuyen: Optional[str] = None
    is_deleted: bool = False
    is_active: bool = True
    created_by_id: Optional[str] = None
    created_by_name: Optional[str] = None
    created_by_fullname: Optional[str] = None
    created_by_email: Optional[str] = None
    created_by_date: Optional[datetime] = None
    modified_by_id: Optional[str] = None
    modified_by_name: Optional[str] = None
    modified_by_fullname: Optional[str] = None
    modified_by_email: Optional[str] = None
    modified_by_date: Optional[datetime] = None
    company_code: Optional[str] = None

    model_config = {"populate_by_name": True}