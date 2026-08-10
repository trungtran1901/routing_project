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
        extra = "ignore"  # Ignore extra environment variables


settings = Settings()