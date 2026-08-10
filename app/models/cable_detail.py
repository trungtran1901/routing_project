from pydantic import BaseModel, Field
from typing import Optional, Any, Dict
from datetime import datetime


class StatusModel(BaseModel):
    label: Optional[str] = None
    value: Optional[str] = None
    data_source: Optional[str] = None
    view_to_open_link: Optional[Any] = None
    display_member: Optional[str] = None
    value_member: Optional[str] = None
    option: Optional[Dict] = {}
    _id: Optional[str] = None


class CableDetailStatusRequest(BaseModel):
    """Payload cable_detail truyền vào API cập nhật status đoạn cáp."""
    id: str = Field(..., alias="_id")
    parent_id: str  # _id của cable cha
    cable_number: Optional[int] = None
    status: Optional[StatusModel] = None
    ma_tuyen: Optional[str] = None
    ghi_chu: Optional[str] = None
    total_sid: Optional[int] = 0
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