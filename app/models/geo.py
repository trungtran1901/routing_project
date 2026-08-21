from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Any, Dict, Literal


GeometrySource = Literal["AUTO", "USER", "IMPORTED", "GOOGLE"]


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
    geometry: LineStringGeoJSON
    geometry_source: GeometrySource = "USER"
    expected_version: Optional[int] = None


class PointGeometryUpdateRequest(BaseModel):
    geometry: PointGeoJSON
    modified_by_id: Optional[str] = None
    modified_by_name: Optional[str] = None
    modified_by_fullname: Optional[str] = None
    modified_by_email: Optional[str] = None


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
    geometry: Dict[str, Any]
    geometry_source: str
    geometry_version: int
    length_m: Optional[float] = None


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


class MeasureRequest(BaseModel):
    points: List[List[float]]

    @field_validator("points")
    @classmethod
    def validate_points(cls, points: List[List[float]]):
        if len(points) < 2:
            raise ValueError("Cần ít nhất 2 điểm để đo khoảng cách.")
        for p in points:
            if len(p) < 2:
                raise ValueError("Mỗi điểm phải có dạng [lng, lat].")
            lng, lat = p[0], p[1]
            if not (-180.0 <= lng <= 180.0):
                raise ValueError(f"Longitude không hợp lệ: {lng}")
            if not (-90.0 <= lat <= 90.0):
                raise ValueError(f"Latitude không hợp lệ: {lat}")
        return points


class MeasureSegmentResult(BaseModel):
    from_index: int
    to_index: int
    length_m: float


class MeasureResponse(BaseModel):
    segments: List[MeasureSegmentResult]
    total_length_m: float
    total_length_km: float
    point_count: int


class MapSearchResultItem(BaseModel):
    type: Literal["point", "segment"]
    source_id: str
    label: str
    ma_tuyen: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None