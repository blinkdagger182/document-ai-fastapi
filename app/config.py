from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://user:password@localhost:5432/documentai"
    
    # Redis/Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    
    # Storage
    storage_backend: Literal["gcs", "s3"] = "gcs"
    gcs_bucket_name: str = "documentai-storage"
    gcs_project_id: str = ""
    s3_bucket_name: str = "documentai-storage"
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    
    # OCR Backend
    ocr_backend: Literal["local", "gcp", "modal"] = "local"
    gcp_ocr_endpoint: str = ""
    modal_ocr_endpoint: str = ""
    
    # Auth
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    
    # App
    environment: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000,capacitor://localhost,ionic://localhost"
    
    # GCP
    google_application_credentials: str = ""
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
