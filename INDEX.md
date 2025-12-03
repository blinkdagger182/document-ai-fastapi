# DocumentAI Backend - Documentation Index

Welcome to the DocumentAI backend documentation! This index will help you find what you need.

## 🚀 Getting Started

**New to the project? Start here:**

1. **[README.md](README.md)** - Project overview and quick start
2. **[QUICKSTART.md](QUICKSTART.md)** - Detailed setup guide (5 minutes)
3. **[API.md](API.md)** - Complete API reference

## 📚 Core Documentation

### For Developers

- **[SUPABASE_QUICKSTART.md](SUPABASE_QUICKSTART.md)** - Connect to Supabase in 5 minutes
- **[SUPABASE_SETUP.md](SUPABASE_SETUP.md)** - Complete Supabase integration guide
- **[PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)** - Comprehensive project overview
  - Technology choices and rationale
  - Data flow and architecture
  - File organization
  - Development workflow

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture
  - Component diagrams
  - Data flow diagrams
  - Deployment architecture
  - Scaling strategy

- **[API.md](API.md)** - API documentation
  - All endpoints with examples
  - Request/response formats
  - Error handling
  - Code examples (cURL, Python, JavaScript)

### For Mobile Developers

- **[SWIFTUI_INTEGRATION.md](SWIFTUI_INTEGRATION.md)** - SwiftUI client guide
  - Complete data models
  - API service implementation
  - Full workflow example
  - Testing tips

### For DevOps

- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Deployment guide
  - Local development setup
  - GCP deployment (Cloud Run, VMs)
  - Modal.com worker deployment
  - Terraform infrastructure
  - CI/CD with Cloud Build
  - Monitoring and troubleshooting

## 📖 Quick Reference

### Common Tasks

| Task | Command | Documentation |
|------|---------|---------------|
| Start locally | `./scripts/quickstart.sh` | [QUICKSTART.md](QUICKSTART.md) |
| Run API | `make dev` | [README.md](README.md) |
| Run worker | `make worker` | [README.md](README.md) |
| Run tests | `make test` | [QUICKSTART.md](QUICKSTART.md) |
| Deploy to GCP | `make deploy-gcp` | [DEPLOYMENT.md](DEPLOYMENT.md) |
| View API docs | http://localhost:8080/docs | [API.md](API.md) |

### File Structure

```
documentai-backend/
├── README.md                    # Project overview
├── QUICKSTART.md               # Setup guide
├── API.md                      # API reference
├── ARCHITECTURE.md             # System design
├── PROJECT_SUMMARY.md          # Detailed overview
├── SWIFTUI_INTEGRATION.md      # iOS client guide
├── DEPLOYMENT.md               # Deployment guide
├── INDEX.md                    # This file
│
├── app/                        # Application code
│   ├── main.py                # FastAPI entry point
│   ├── config.py              # Configuration
│   ├── database.py            # Database setup
│   ├── models/                # SQLAlchemy models
│   ├── schemas/               # Pydantic models
│   ├── routers/               # API endpoints
│   ├── services/              # Business logic
│   ├── workers/               # Celery tasks
│   └── utils/                 # Helpers
│
├── tests/                      # Unit tests
├── scripts/                    # Utility scripts
├── deployment/                 # Deployment configs
│   ├── terraform/             # Infrastructure as code
│   ├── gcp-deploy.sh          # GCP deployment
│   ├── modal_worker.py        # Modal.com worker
│   └── cloudbuild.yaml        # CI/CD config
│
├── alembic/                    # Database migrations
├── requirements.txt            # Python dependencies
├── docker-compose.yml          # Local development
├── Dockerfile                  # API container
├── Dockerfile.worker           # Worker container
└── Makefile                    # Common commands
```

## 🎯 By Role

### Backend Developer

**Start here:**
1. [QUICKSTART.md](QUICKSTART.md) - Get running locally
2. [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) - Understand the codebase
3. [ARCHITECTURE.md](ARCHITECTURE.md) - Learn the design

**Key files:**
- `app/routers/documents.py` - API endpoints
- `app/workers/tasks.py` - Background jobs
- `app/services/` - Business logic

### iOS/SwiftUI Developer

**Start here:**
1. [API.md](API.md) - Understand the API
2. [SWIFTUI_INTEGRATION.md](SWIFTUI_INTEGRATION.md) - Integration guide

**Key concepts:**
- camelCase JSON responses
- Polling for async operations
- Document status flow
- Field components and field map

### DevOps Engineer

**Start here:**
1. [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment options
2. [ARCHITECTURE.md](ARCHITECTURE.md) - Infrastructure design

**Key files:**
- `deployment/terraform/` - Infrastructure as code
- `deployment/gcp-deploy.sh` - Deployment script
- `docker-compose.yml` - Local services
- `.env.example` - Configuration template

### QA/Tester

**Start here:**
1. [QUICKSTART.md](QUICKSTART.md) - Setup test environment
2. [API.md](API.md) - API endpoints to test

**Key files:**
- `tests/test_api.py` - Unit tests
- `scripts/test_ocr.py` - OCR testing

## 🔍 By Topic

### API & Endpoints

- **[API.md](API.md)** - Complete API reference
- **[app/routers/](app/routers/)** - Endpoint implementations
- **[app/schemas/](app/schemas/)** - Request/response models

### Database

- **[app/models/](app/models/)** - Database models
- **[alembic/](alembic/)** - Migrations
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Schema design

### OCR & PDF Processing

- **[app/services/ocr_dispatcher.py](app/services/ocr_dispatcher.py)** - OCR backends
- **[app/services/pdf_compose.py](app/services/pdf_compose.py)** - PDF generation
- **[app/workers/tasks.py](app/workers/tasks.py)** - Processing tasks

### Storage

- **[app/services/storage.py](app/services/storage.py)** - Storage abstraction
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Storage setup

### Deployment

- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Full deployment guide
- **[deployment/terraform/](deployment/terraform/)** - Infrastructure code
- **[deployment/gcp-deploy.sh](deployment/gcp-deploy.sh)** - Deployment script

### Testing

- **[tests/](tests/)** - Test suite
- **[pytest.ini](pytest.ini)** - Test configuration
- **[QUICKSTART.md](QUICKSTART.md)** - Running tests

## 📊 Diagrams & Visuals

All diagrams are in **[ARCHITECTURE.md](ARCHITECTURE.md)**:

- System overview diagram
- Component architecture
- Data flow diagrams (upload, OCR, compose)
- Deployment architecture
- Security layers
- Scaling strategy

## 🆘 Troubleshooting

### Common Issues

| Issue | Solution | Documentation |
|-------|----------|---------------|
| Port in use | `lsof -i :8080` | [QUICKSTART.md](QUICKSTART.md#troubleshooting) |
| Database error | Check Docker logs | [QUICKSTART.md](QUICKSTART.md#troubleshooting) |
| Worker not running | Restart Celery | [QUICKSTART.md](QUICKSTART.md#troubleshooting) |
| OCR fails | Test with script | [QUICKSTART.md](QUICKSTART.md#troubleshooting) |
| Import errors | Reinstall deps | [QUICKSTART.md](QUICKSTART.md#troubleshooting) |

### Getting Help

1. Check **[QUICKSTART.md](QUICKSTART.md#troubleshooting)** troubleshooting section
2. Review **[PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)** for architecture
3. Check API docs at http://localhost:8080/docs
4. Review logs in terminal or Docker
5. Open GitHub issue with details

## 🎓 Learning Path

### Beginner

1. Read [README.md](README.md) for overview
2. Follow [QUICKSTART.md](QUICKSTART.md) to get running
3. Explore API at http://localhost:8080/docs
4. Try example requests from [API.md](API.md)

### Intermediate

1. Study [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) for architecture
2. Review [ARCHITECTURE.md](ARCHITECTURE.md) for design patterns
3. Explore codebase starting with `app/main.py`
4. Run and modify tests in `tests/`

### Advanced

1. Implement new features (see roadmap in [README.md](README.md))
2. Optimize performance (see [ARCHITECTURE.md](ARCHITECTURE.md))
3. Deploy to production (see [DEPLOYMENT.md](DEPLOYMENT.md))
4. Set up monitoring and alerts

## 📝 Contributing

### Before You Start

1. Read [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) - Understand the project
2. Review [ARCHITECTURE.md](ARCHITECTURE.md) - Learn the design
3. Check [README.md](README.md) - See the roadmap

### Development Workflow

1. Fork the repository
2. Create a feature branch
3. Follow code style in existing files
4. Add tests for new features
5. Run `make test` before committing
6. Submit pull request with description

### Code Organization

- **Models** (`app/models/`) - Database schema
- **Schemas** (`app/schemas/`) - API contracts
- **Routers** (`app/routers/`) - Endpoints
- **Services** (`app/services/`) - Business logic
- **Workers** (`app/workers/`) - Background tasks
- **Utils** (`app/utils/`) - Helpers

## 🔗 External Resources

### Technologies

- **FastAPI**: https://fastapi.tiangolo.com/
- **SQLAlchemy**: https://docs.sqlalchemy.org/
- **Celery**: https://docs.celeryq.dev/
- **PaddleOCR**: https://github.com/PaddlePaddle/PaddleOCR
- **PyMuPDF**: https://pymupdf.readthedocs.io/

### Cloud Platforms

- **GCP Cloud Run**: https://cloud.google.com/run/docs
- **GCP Cloud SQL**: https://cloud.google.com/sql/docs
- **Modal.com**: https://modal.com/docs

### Tools

- **Docker**: https://docs.docker.com/
- **Terraform**: https://www.terraform.io/docs
- **Alembic**: https://alembic.sqlalchemy.org/

## 📅 Version History

- **v1.0.0** (Current) - Initial production release
  - FastAPI backend
  - PaddleOCR integration
  - GCP deployment
  - SwiftUI support

## 📄 License

MIT License - see [LICENSE](LICENSE) file

---

## Quick Links

| Document | Purpose | Audience |
|----------|---------|----------|
| [README.md](README.md) | Project overview | Everyone |
| [QUICKSTART.md](QUICKSTART.md) | Setup guide | Developers |
| [API.md](API.md) | API reference | All developers |
| [SWIFTUI_INTEGRATION.md](SWIFTUI_INTEGRATION.md) | iOS integration | iOS developers |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Deployment | DevOps |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design | Architects |
| [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) | Deep dive | Backend devs |

---

**Need help? Start with [QUICKSTART.md](QUICKSTART.md) or check the troubleshooting section!**
