from abc import ABC, abstractmethod
from typing import Protocol
import os
from app.config import settings


class StorageService(Protocol):
    async def upload_file(self, *, local_path: str, key: str, content_type: str) -> str:
        """Upload file and return storage URL"""
        ...
    
    async def download_to_path(self, *, key: str, local_path: str) -> None:
        """Download file from storage to local path"""
        ...
    
    def generate_presigned_url(self, *, key: str, expires_in: int = 3600) -> str:
        """Generate presigned URL for download"""
        ...


class GCSStorageService:
    def __init__(self):
        from google.cloud import storage
        self.client = storage.Client(project=settings.gcs_project_id)
        self.bucket = self.client.bucket(settings.gcs_bucket_name)
    
    async def upload_file(self, *, local_path: str, key: str, content_type: str) -> str:
        blob = self.bucket.blob(key)
        blob.upload_from_filename(local_path, content_type=content_type)
        return f"gs://{settings.gcs_bucket_name}/{key}"
    
    async def download_to_path(self, *, key: str, local_path: str) -> None:
        blob = self.bucket.blob(key)
        blob.download_to_filename(local_path)
    
    def generate_presigned_url(self, *, key: str, expires_in: int = 3600) -> str:
        from datetime import timedelta
        blob = self.bucket.blob(key)
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=expires_in),
            method="GET"
        )
        return url


class S3StorageService:
    def __init__(self):
        import boto3
        self.client = boto3.client(
            's3',
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key
        )
        self.bucket_name = settings.s3_bucket_name
    
    async def upload_file(self, *, local_path: str, key: str, content_type: str) -> str:
        with open(local_path, 'rb') as f:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=f,
                ContentType=content_type
            )
        return f"s3://{self.bucket_name}/{key}"
    
    async def download_to_path(self, *, key: str, local_path: str) -> None:
        self.client.download_file(self.bucket_name, key, local_path)
    
    def generate_presigned_url(self, *, key: str, expires_in: int = 3600) -> str:
        url = self.client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket_name, 'Key': key},
            ExpiresIn=expires_in
        )
        return url


def get_storage_service() -> StorageService:
    if settings.storage_backend == "gcs":
        return GCSStorageService()
    elif settings.storage_backend == "s3":
        return S3StorageService()
    else:
        raise ValueError(f"Unknown storage backend: {settings.storage_backend}")
