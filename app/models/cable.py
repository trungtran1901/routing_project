from pydantic import BaseModel, Field
from typing import Optional, Any, Dict
from datetime import datetime


class CableTypeModel(BaseModel):
    _id: Optional[str] = None
    label: Optional[str] = None
    value: Optional[str] = None
    data_source: Optional[str] = None
    view_to_open_link: Optional[Any] = None
    display_member: Optional[str] = None
    value_member: Optional[str] = None
    option: Optional[Dict] = {}


class CableSyncRequest(BaseModel):
    """
    Payload đoạn cáp truyền vào API đồng bộ cable_detail.
    Chú ý trường total_cable điều khiển số lượng bản ghi chi tiết cần tồn tại.
    """
    id: str = Field(..., alias="_id")
    parent_id: str
    ma_tuyen: str
    code: Optional[str] = None
    total_cable: float = 0
    error_cable: int = 0
    available_cable: int = 0
    start_point: Optional[str] = None
    end_point: Optional[str] = None
    length_cable: float = 0
    ghi_chu: Optional[str] = None
    start_point_text: Optional[str] = None
    end_point_text: Optional[str] = None
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
    cable_type: Optional[CableTypeModel] = None

    model_config = {"populate_by_name": True}