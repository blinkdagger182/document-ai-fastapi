# Terraform configuration for GCP infrastructure

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Cloud SQL (PostgreSQL)
resource "google_sql_database_instance" "documentai_db" {
  name             = "documentai-db"
  database_version = "POSTGRES_15"
  region           = var.region

  settings {
    tier = "db-f1-micro"
    
    backup_configuration {
      enabled = true
    }
    
    ip_configuration {
      ipv4_enabled = true
      authorized_networks {
        name  = "all"
        value = "0.0.0.0/0"
      }
    }
  }

  deletion_protection = false
}

resource "google_sql_database" "database" {
  name     = "documentai"
  instance = google_sql_database_instance.documentai_db.name
}

# Cloud Storage bucket
resource "google_storage_bucket" "documentai_storage" {
  name          = "${var.project_id}-documentai-storage"
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  cors {
    origin          = ["*"]
    method          = ["GET", "HEAD", "PUT", "POST", "DELETE"]
    response_header = ["*"]
    max_age_seconds = 3600
  }
}

# Cloud Memorystore (Redis)
resource "google_redis_instance" "documentai_redis" {
  name           = "documentai-redis"
  tier           = "BASIC"
  memory_size_gb = 1
  region         = var.region
  redis_version  = "REDIS_7_0"
}

# Secret Manager secrets
resource "google_secret_manager_secret" "db_url" {
  secret_id = "documentai-db-url"
  
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "redis_url" {
  secret_id = "documentai-redis-url"
  
  replication {
    auto {}
  }
}

# Cloud Run service (API)
resource "google_cloud_run_service" "documentai_api" {
  name     = "documentai-api"
  location = var.region

  template {
    spec {
      containers {
        image = "gcr.io/${var.project_id}/documentai-api:latest"
        
        env {
          name  = "ENVIRONMENT"
          value = "production"
        }
        
        env {
          name  = "STORAGE_BACKEND"
          value = "gcs"
        }
        
        env {
          name  = "GCS_BUCKET_NAME"
          value = google_storage_bucket.documentai_storage.name
        }
        
        resources {
          limits = {
            cpu    = "2"
            memory = "2Gi"
          }
        }
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }
}

# IAM policy for Cloud Run (public access)
resource "google_cloud_run_service_iam_member" "public_access" {
  service  = google_cloud_run_service.documentai_api.name
  location = google_cloud_run_service.documentai_api.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Outputs
output "api_url" {
  value = google_cloud_run_service.documentai_api.status[0].url
}

output "db_connection_name" {
  value = google_sql_database_instance.documentai_db.connection_name
}

output "redis_host" {
  value = google_redis_instance.documentai_redis.host
}

output "storage_bucket" {
  value = google_storage_bucket.documentai_storage.name
}
