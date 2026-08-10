# Docker Quick Start

## Prerequisites
- Docker Desktop (Windows/Mac) hoặc Docker + Docker Compose (Linux)
- Git
- **MongoDB instance chạy bên ngoài** (local, remote, hoặc Atlas)

## Quick Start (30 seconds)

### Windows (PowerShell)
```powershell
# 1. Setup environment và cấu hình MongoDB URI
cp .env.example .env
# Sửa MONGODB_URI trong .env nếu cần (mặc định: localhost:27017)

# 2. Run the deployment helper
.\deploy.ps1
# Chọn option 1: "Build and Start"
```

### Linux/Mac (Bash)
```bash
# 1. Setup environment
cp .env.example .env
# Sửa MONGODB_URI trong .env nếu cần

# 2. Make script executable
chmod +x deploy.sh

# 3. Run the deployment helper
./deploy.sh
# Chọn option 1: "Build and Start"
```

### Manual (tất cả OS)
```bash
# 1. Setup environment
cp .env.example .env

# 2. Build và start
docker-compose build
docker-compose up -d

# 3. Kiểm tra trạng thái
docker-compose ps
```

---

## Configure MongoDB Connection

### Option 1: Local MongoDB (default)
```env
MONGODB_URI=mongodb://localhost:27017
DATABASE_NAME=routing_db
```

### Option 2: MongoDB with Authentication
```env
MONGODB_URI=mongodb://username:password@localhost:27017/?authSource=admin
DATABASE_NAME=routing_db
```

### Option 3: MongoDB Atlas (Cloud)
```env
MONGODB_URI=mongodb+srv://username:password@cluster0.mongodb.net/routing_db
DATABASE_NAME=routing_db
```

### Option 4: Remote MongoDB Server
```env
MONGODB_URI=mongodb://username:password@192.168.1.100:27017/?authSource=admin
DATABASE_NAME=routing_db
```

---

## Access Services

| Service | URL |
|---------|-----|
| **API Docs (Swagger)** | http://localhost:8000/docs |
| **API ReDoc** | http://localhost:8000/redoc |
| **Health Check** | http://localhost:8000/health |

---

## Common Commands

```bash
# View logs
docker-compose logs -f routing_api

# Access container shell
docker-compose exec routing_api bash

# Stop services
docker-compose down

# Rebuild
docker-compose build --no-cache
docker-compose up -d

# Clean everything
docker-compose down -v
```

---

## Files Created

| File | Purpose |
|------|---------|
| `Dockerfile` | Build image cho FastAPI app |
| `docker-compose.yml` | Run chỉ routing_api container |
| `.env.example` | Environment variables template |
| `.dockerignore` | Files to exclude from Docker build |
| `Makefile` | Convenient command shortcuts (Linux/Mac) |
| `deploy.sh` | Interactive deployment helper (Bash) |
| `deploy.ps1` | Interactive deployment helper (PowerShell) |
| `DEPLOYMENT.md` | Detailed deployment guide |

---

## Troubleshooting

**MongoDB connection refused?**
```bash
# Kiểm tra MONGODB_URI trong .env
cat .env | grep MONGODB_URI

# Coba kết nối trực tiếp từ container
docker-compose exec routing_api bash
# Trong container: mongosh <MONGODB_URI>
```

**Port 8000 đã được sử dụng?**
```bash
# Đổi port trong .env
API_PORT=8001

# Restart services
docker-compose down
docker-compose up -d
```

**Container exits immediately?**
```bash
# Kiểm tra logs
docker-compose logs routing_api

# Rebuild từ đầu
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
```

**Kiểm tra kết nối MongoDB từ API?**
```bash
# Xem logs chi tiết
docker-compose logs -f routing_api

# Nếu thấy "Connected to MongoDB" → OK
# Nếu lỗi → kiểm tra MONGODB_URI và xác nhận MongoDB đang chạy
```

---

## For Production

Xem chi tiết trong `DEPLOYMENT.md`:
- Using managed MongoDB (Atlas)
- Scale deployment
- Monitoring & logging
- SSL/TLS setup
- Security best practices
