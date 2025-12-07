from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://user:password@localhost:5432/documentai"
    
    # Storage
    storage_backend: Literal["gcs", "s3", "supabase"] = "gcs"
    gcs_bucket_name: str = "documentai-storage"
    gcs_project_id: str = ""
    s3_bucket_name: str = "documentai-storage"
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    
    # Supabase
    supabase_url: str = "https://iixekrmukkpdmmqoheed.supabase.co"
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_bucket_name: str = "documentai-storage"
    
    # Auth
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    
    # App
    environment: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000,capacitor://localhost,ionic://localhost,https://*"
    
    # GCP
    google_application_credentials: str = ""
    gcp_project_id: str = ""
    gcp_region: str = "us-central1"
    gcp_service_account_email: str = ""
    
    # Cloud Tasks
    ocr_queue_name: str = "ocr-queue"
    compose_queue_name: str = "compose-queue"
    commonforms_queue_name: str = "commonforms-queue"
    
    # Worker URLs (Cloud Run services)
    ocr_worker_url: str = ""
    compose_worker_url: str = ""
    vision_worker_url: str = ""
    commonforms_worker_url: str = ""
    
    # Vision AI
    openai_api_key: str = ""
    gemini_api_key: str = ""
    vision_provider: Literal["openai", "gemini"] = "openai"
    vision_model: str = ""  # Defaults to gpt-4o-mini or gemini-1.5-flash
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
