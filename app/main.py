from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.database import connect_to_mongo, close_mongo_connection
from app.core.postgis import connect_to_postgis, close_postgis_connection
from app.core.config import settings
from app.routers.routing import router as routing_router
from app.routers.map_router import router as map_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    # GIS layer (PostgreSQL/PostGIS) độc lập với MongoDB. Nếu Postgres chưa
    # sẵn sàng, connect_to_postgis() chỉ log warning chứ không raise, để
    # routing API (Mongo) hiện tại vẫn hoạt động bình thường.
    await connect_to_postgis()
    yield
    await close_mongo_connection()
    await close_postgis_connection()


app = FastAPI(
    title="Routing API - Quản lý tuyến cáp",
    description=(
        "API xử lý bài toán routing cho hệ thống quản lý tuyến cáp. "
        "Bao gồm GIS/Map layer (PostGIS) cho spatial query, độc lập với "
        "MongoDB (vẫn là source of truth cho business/topology data)."
    ),
    version="1.1.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

app.include_router(routing_router, prefix="/api/v1")
app.include_router(map_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}
