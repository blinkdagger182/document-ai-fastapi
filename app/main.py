from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import documents, health, hybrid, commonforms
from app.utils.logging import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title="DocumentAI API",
    description="Production-ready backend for document OCR and form filling",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS configuration
origins = settings.cors_origins.split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(documents.router)
app.include_router(health.router)
app.include_router(hybrid.router)
app.include_router(commonforms.router)


@app.on_event("startup")
async def startup_event():
    logger.info("DocumentAI API starting up...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Storage backend: {settings.storage_backend}")
    logger.info(f"OCR worker URL: {settings.ocr_worker_url}")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("DocumentAI API shutting down...")


@app.get("/")
async def root():
    return {
        "message": "DocumentAI API",
        "version": "1.0.0",
        "docs": "/docs"
    }
