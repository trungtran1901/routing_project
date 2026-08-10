from pydantic import BaseModel, Field
from typing import Optional, Any, Dict
from datetime import datetime


class PointTypeModel(BaseModel):
    label: Optional[str] = None
    value: Optional[str] = None
    data_source: Optional[str] = None
    view_to_open_link: Optional[Any] = None
    display_member: Optional[str] = None
    value_member: Optional[str] = None
    option: Optional[Dict] = {}
    _id: Optional[str] = None


class StartPointRefModel(BaseModel):
    label: Optional[str] = None
    value: Optional[str] = None
    data_source: Optional[str] = None
    view_to_open_link: Optional[Any] = None
    display_member: Optional[str] = None
    value_member: Optional[str] = None
    option: Optional[Dict] = {}
    _id: Optional[str] = None


class StationModel(BaseModel):
    label: Optional[str] = None
    value: Optional[str] = None
    data_source: Optional[str] = None
    view_to_open_link: Optional[Any] = None
    display_member: Optional[str] = None
    value_member: Optional[str] = None
    option: Optional[Dict] = {}
    _id: Optional[str] = None


class PointCreateRequest(BaseModel):
    """
    Payload khi tạo mới một điểm.
    Nếu start_point bị bỏ trống (None) → thêm vào cuối tuyến.
    Nếu start_point có giá trị (ma_diem của điểm trước đó) → chèn vào giữa.
    """
    ma_diem: str
    ten_diem: str
    vi_do: Optional[float] = None
    kinh_do: Optional[float] = None
    dia_chi: Optional[str] = None
    ngay_van_hanh: Optional[str] = None
    ghi_chu: Optional[str] = None
    parent_id: str
    ma_tuyen: str
    thu_tu: Optional[float] = None
    point_type: Optional[PointTypeModel] = None
    station: Optional[StationModel] = None

    # Nếu None → thêm cuối; nếu có giá trị → chèn giữa (sau điểm này)
    start_point: Optional[StartPointRefModel] = None
    stt_start_point: Optional[int] = 0

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


class PointDeleteRequest(BaseModel):
    """Payload khi xóa mềm một điểm."""
    ma_diem: str
    ma_tuyen: str
    parent_id: str
    # Thông tin người thực hiện xóa (dùng để ghi vào đoạn cáp tạo mới)
    deleted_by_id: Optional[str] = None
    deleted_by_name: Optional[str] = None
    deleted_by_fullname: Optional[str] = None
    deleted_by_email: Optional[str] = None
    company_code: Optional[str] = None


class CableDocument(BaseModel):
    """Cấu trúc document đoạn cáp lưu trong collection cable."""
    id: Optional[str] = Field(None, alias="_id")
    parent_id: str
    code: str
    total_cable: int = 0
    error_cable: int = 0
    available_cable: int = 0
    start_point: Optional[str] = None
    end_point: Optional[str] = None
    length_cable: int = 0
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