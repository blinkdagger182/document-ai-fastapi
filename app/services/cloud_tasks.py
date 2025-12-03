"""
Cloud Tasks Service - Replace Celery with Cloud Tasks
"""
from google.cloud import tasks_v2
from google.protobuf import timestamp_pb2
import json
from datetime import datetime, timedelta
from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class CloudTasksService:
    """
    Service to enqueue background jobs using Cloud Tasks.
    Workers are separate Cloud Run services.
    """
    
    def __init__(self):
        self.client = tasks_v2.CloudTasksClient()
        self.project = settings.gcp_project_id
        self.location = settings.gcp_region
        self.ocr_queue = settings.ocr_queue_name
        self.compose_queue = settings.compose_queue_name
        
        # Worker URLs (Cloud Run services)
        self.ocr_worker_url = settings.ocr_worker_url
        self.compose_worker_url = settings.compose_worker_url
    
    def enqueue_ocr_task(self, document_id: str) -> str:
        """
        Enqueue OCR task to process a document.
        
        Args:
            document_id: UUID of document to process
            
        Returns:
            Task name
        """
        queue_path = self.client.queue_path(
            self.project,
            self.location,
            self.ocr_queue
        )
        
        # Task payload
        payload = {
            "document_id": document_id
        }
        
        # Create HTTP POST task
        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": f"{self.ocr_worker_url}/ocr",
                "headers": {
                    "Content-Type": "application/json"
                },
                "body": json.dumps(payload).encode(),
                "oidc_token": {
                    "service_account_email": settings.gcp_service_account_email
                }
            }
        }
        
        # Schedule task
        response = self.client.create_task(
            request={"parent": queue_path, "task": task}
        )
        
        logger.info(f"Enqueued OCR task for document {document_id}: {response.name}")
        return response.name
    
    def enqueue_compose_task(self, document_id: str) -> str:
        """
        Enqueue PDF composition task.
        
        Args:
            document_id: UUID of document to compose
            
        Returns:
            Task name
        """
        queue_path = self.client.queue_path(
            self.project,
            self.location,
            self.compose_queue
        )
        
        # Task payload
        payload = {
            "document_id": document_id
        }
        
        # Create HTTP POST task
        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": f"{self.compose_worker_url}/compose",
                "headers": {
                    "Content-Type": "application/json"
                },
                "body": json.dumps(payload).encode(),
                "oidc_token": {
                    "service_account_email": settings.gcp_service_account_email
                }
            }
        }
        
        # Schedule task
        response = self.client.create_task(
            request={"parent": queue_path, "task": task}
        )
        
        logger.info(f"Enqueued compose task for document {document_id}: {response.name}")
        return response.name


# Singleton instance
_cloud_tasks_service = None


def get_cloud_tasks_service() -> CloudTasksService:
    """Get or create CloudTasksService instance"""
    global _cloud_tasks_service
    if _cloud_tasks_service is None:
        _cloud_tasks_service = CloudTasksService()
    return _cloud_tasks_service
