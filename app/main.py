import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.database import connect_to_mongo, close_mongo_connection
from app.core.postgis import connect_to_postgis, close_postgis_connection
from app.core.config import settings
from app.routers.routing import router as routing_router
from app.routers.map_router import router as map_router

logger = logging.getLogger("routing_api")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    raw_body = await request.body()
    logger.error(
        "422 Validation error | method=%s path=%s errors=%s raw_body=%s",
        request.method,
        request.url.path,
        exc.errors(),
        raw_body.decode("utf-8", errors="replace"),
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "raw_body": raw_body.decode("utf-8", errors="replace")},
    )


app.include_router(routing_router, prefix="/api/v1")
app.include_router(map_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}