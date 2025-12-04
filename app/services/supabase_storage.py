"""
Supabase Storage Service - Alternative to GCS/S3
Uses Supabase Storage REST API for file operations
"""
import httpx
from typing import Optional
from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class SupabaseStorageService:
    """
    Supabase Storage implementation using REST API.
    
    Requires environment variables:
    - SUPABASE_URL
    - SUPABASE_SERVICE_ROLE_KEY
    - SUPABASE_BUCKET_NAME
    """
    
    def __init__(self):
        self.base_url = f"{settings.supabase_url}/storage/v1"
        self.bucket = settings.supabase_bucket_name
        self.headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "apikey": settings.supabase_service_role_key
        }
    
    async def upload_file(self, *, local_path: str, key: str, content_type: str) -> str:
        """Upload file to Supabase Storage"""
        try:
            with open(local_path, 'rb') as f:
                file_content = f.read()
            
            # Use upsert to overwrite if exists
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.base_url}/object/{self.bucket}/{key}",
                    content=file_content,
                    headers={
                        **self.headers,
                        "Content-Type": content_type,
                        "x-upsert": "true"  # Allow overwriting
                    }
                )
                
                # Log response for debugging
                if response.status_code >= 400:
                    logger.error(f"Supabase upload failed: {response.status_code} - {response.text}")
                
                response.raise_for_status()
            
            logger.info(f"Uploaded file to Supabase: {key}")
            return f"{self.base_url}/object/public/{self.bucket}/{key}"
        
        except Exception as e:
            logger.error(f"Failed to upload to Supabase: {str(e)}")
            raise
    
    async def download_to_path(self, *, key: str, local_path: str) -> None:
        """Download file from Supabase Storage"""
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.get(
                    f"{self.base_url}/object/{self.bucket}/{key}",
                    headers=self.headers
                )
                response.raise_for_status()
                
                with open(local_path, 'wb') as f:
                    f.write(response.content)
            
            logger.info(f"Downloaded file from Supabase: {key}")
        
        except Exception as e:
            logger.error(f"Failed to download from Supabase: {str(e)}")
            raise
    
    def generate_presigned_url(self, *, key: str, expires_in: int = 3600) -> str:
        """
        Generate signed URL for Supabase Storage.
        Note: This is a synchronous operation.
        """
        try:
            import requests
            
            response = requests.post(
                f"{self.base_url}/object/sign/{self.bucket}/{key}",
                json={"expiresIn": expires_in},
                headers=self.headers
            )
            response.raise_for_status()
            
            signed_url = response.json().get("signedURL")
            full_url = f"{settings.supabase_url}/storage/v1{signed_url}"
            
            logger.info(f"Generated signed URL for: {key}")
            return full_url
        
        except Exception as e:
            logger.error(f"Failed to generate signed URL: {str(e)}")
            # Fallback to public URL (if bucket is public)
            return f"{self.base_url}/object/public/{self.bucket}/{key}"
