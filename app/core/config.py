from pydantic_settings import BaseSettings
from typing import Optional, List
from pydantic import field_validator


class Settings(BaseSettings):
    # MongoDB Configuration
    MONGODB_URI: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "routing_db"

    # API Configuration
    API_PORT: int = 8000

    # HTTPS Configuration
    USE_HTTPS: bool = False
    SSL_KEYFILE: Optional[str] = None
    SSL_CERTFILE: Optional[str] = None

    # CORS Configuration
    CORS_ORIGINS: List[str] = [
        "http://localhost:9000",
        "http://localhost:3000",
        "http://localhost:8080",
        "https://app.hitc.vn",
        "http://192.168.100.92:9000",
        "http://192.168.100.92:3000",
    ]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]

    # Optional configuration
    ENVIRONMENT: Optional[str] = "development"
    LOG_LEVEL: Optional[str] = "INFO"

    # Mongo credentials (optional)
    MONGO_USERNAME: Optional[str] = None
    MONGO_PASSWORD: Optional[str] = None
    MONGO_PORT: Optional[int] = None

    # ------------------------------------------------------------------
    # GIS layer (PostgreSQL + PostGIS) - độc lập với MongoDB
    # ------------------------------------------------------------------
    POSTGRES_URI: str = "postgresql://gis_user:gis_pass@localhost:5432/gis_db"
    POSTGRES_POOL_MAX_SIZE: int = 10
    GIS_SYNC_BATCH_SIZE: int = 500
    # Bán kính tối đa cho phép trong /map/nearby (mét), tránh query quá rộng
    GIS_NEARBY_MAX_RADIUS_M: int = 20000
    # Giới hạn số bản ghi tối đa trả về cho 1 request bbox/nearby
    GIS_MAX_RESULT_LIMIT: int = 5000

    # Gom cụm điểm theo viewport (giống Google Maps marker clustering)
    GIS_CLUSTER_DEFAULT_GRID_SIZE: int = 32   # lưới NxN mặc định trên viewport
    GIS_CLUSTER_MAX_GRID_SIZE: int = 128
    GIS_CLUSTER_MIN_GRID_SIZE: int = 4

    # Đường dây (segments): ẩn khi zoom quá nhỏ (tránh trả hàng trăm nghìn
    # LineString khi đang xem toàn quốc/toàn tỉnh), và tự đơn giản hoá
    # geometry (giảm số vertex) theo zoom khi zoom được truyền vào.
    GIS_SEGMENTS_MIN_ZOOM_TO_LOAD: int = 12
    GIS_SEGMENTS_AUTO_SIMPLIFY: bool = True

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS_ORIGINS from comma-separated string to list"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()