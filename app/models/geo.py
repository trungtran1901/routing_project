from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Any, Dict, Literal


GeometrySource = Literal["AUTO", "USER", "IMPORTED", "GOOGLE"]


# ---------------------------------------------------------------------------
# GeoJSON-ish input for LineString geometry update
# ---------------------------------------------------------------------------

class LineStringGeoJSON(BaseModel):
    type: Literal["LineString"]
    coordinates: List[List[float]]

    @field_validator("coordinates")
    @classmethod
    def validate_coordinates(cls, coords: List[List[float]]):
        if len(coords) < 2:
            raise ValueError("LineString phải có ít nhất 2 tọa độ (coordinate).")
        for c in coords:
            if len(c) < 2:
                raise ValueError("Mỗi coordinate phải có dạng [lng, lat].")
            lng, lat = c[0], c[1]
            if not (-180.0 <= lng <= 180.0):
                raise ValueError(f"Longitude không hợp lệ: {lng}")
            if not (-90.0 <= lat <= 90.0):
                raise ValueError(f"Latitude không hợp lệ: {lat}")
        return coords


class PointGeoJSON(BaseModel):
    type: Literal["Point"]
    coordinates: List[float]

    @field_validator("coordinates")
    @classmethod
    def validate_coordinates(cls, coords: List[float]):
        if len(coords) < 2:
            raise ValueError("Point phải có dạng [lng, lat].")
        lng, lat = coords[0], coords[1]
        if not (-180.0 <= lng <= 180.0):
            raise ValueError(f"Longitude không hợp lệ: {lng}")
        if not (-90.0 <= lat <= 90.0):
            raise ValueError(f"Latitude không hợp lệ: {lat}")
        return coords


class SegmentGeometryUpdateRequest(BaseModel):
    """Payload PUT /map/segments/{segment_id}/geometry"""
    geometry: LineStringGeoJSON
    geometry_source: GeometrySource = "USER"
    # Optional optimistic-locking: nếu client biết version hiện tại, backend
    # sẽ so khớp trước khi ghi đè để tránh mất chỉnh sửa của người khác.
    expected_version: Optional[int] = None


class PointGeometryUpdateRequest(BaseModel):
    """
    Payload PUT /map/points/{point_id}/geometry.

    Khác với segment (chỉ ghi PostGIS), cập nhật toạ độ điểm phải ghi CẢ
    MongoDB (vi_do/kinh_do - nguồn dữ liệu nghiệp vụ chính) LẪN PostGIS
    (geometry - dùng cho spatial query/hiển thị map).
    """
    geometry: PointGeoJSON
    # Thông tin người thực hiện (tuỳ chọn) để ghi vào modified_by_* trên MongoDB.
    modified_by_id: Optional[str] = None
    modified_by_name: Optional[str] = None
    modified_by_fullname: Optional[str] = None
    modified_by_email: Optional[str] = None


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class MapPointResponse(BaseModel):
    source_id: str
    ma_diem: str
    ten_diem: Optional[str] = None
    lat: float
    lng: float
    point_type: Optional[str] = None
    ma_tuyen: Optional[str] = None
    parent_id: Optional[str] = None


class MapSegmentResponse(BaseModel):
    source_id: str
    start_point_id: str
    end_point_id: str
    ma_tuyen: Optional[str] = None
    parent_id: Optional[str] = None
    geometry: Dict[str, Any]  # GeoJSON LineString
    geometry_source: str
    geometry_version: int


class MapSegmentDetailResponse(BaseModel):
    segment: MapSegmentResponse
    start_point: Optional[MapPointResponse] = None
    end_point: Optional[MapPointResponse] = None
    editable: bool = True


class NearbyPointResult(MapPointResponse):
    distance_m: float


class NearbySegmentResult(BaseModel):
    source_id: str
    start_point_id: str
    end_point_id: str
    ma_tuyen: Optional[str] = None
    distance_m: float


class MapSearchResultItem(BaseModel):
    type: Literal["point", "segment"]
    source_id: str
    label: str
    ma_tuyen: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
