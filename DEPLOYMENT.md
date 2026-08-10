# Deployment Guide - Routing API

Hướng dẫn triển khai ứng dụng Routing API bằng Docker và Docker Compose.

---

## Prerequisite

- Docker Desktop (phiên bản 4.0+)
- Docker Compose (phiên bản 2.0+)
- Git

---

## Quick Start

### 1. Clone và cấu hình

```bash
# Clone project
git clone <your-repo>
cd routing_project

# Copy file environment
cp .env.example .env
```

### 2. Cấu hình .env - MongoDB Connection

**QUAN TRỌNG:** Bạn cần có MongoDB instance chạy bên ngoài Docker.

```bash
# Mở file .env và cấu hình MONGODB_URI tùy theo tình huống:

# Local MongoDB (mặc định)
MONGODB_URI=mongodb://localhost:27017

# Remote MongoDB with auth
MONGODB_URI=mongodb://username:password@192.168.1.100:27017/?authSource=admin

# MongoDB Atlas (Cloud)
MONGODB_URI=mongodb+srv://username:password@cluster0.mongodb.net/routing_db
```

### 3. Build và chạy

```bash
# Cách 1: Sử dụng Make (nếu có)
make build
make up

# Hoặc Cách 2: Sử dụng Docker Compose trực tiếp
docker-compose build
docker-compose up -d
```

### 4. Kiểm tra trạng thái

```bash
docker-compose ps
```

Output:
```
NAME                    COMMAND                  SERVICE             STATUS
routing_api             "uvicorn app.main:app"   routing_api         Up 2 minutes
routing_mongodb         "mongod"                 mongodb             Up 2 minutes
routing_mongo_express   "tini -- node server.js" mongo-express       Up 2 minutes
```

---

## Truy cập ứng dụng

| Dịch vụ | URL | Mô tả |
|---------|-----|--------|
| **API Docs (Swagger)** | http://localhost:8000/docs | Interactive API documentation |
| **API ReDoc** | http://localhost:8000/redoc | Alternative API documentation |
| **Health Check** | http://localhost:8000/health | Kiểm tra trạng thái API |

---

## Các câu lệnh hữu ích

### Kiểm tra logs

```bash
# Logs của API
docker-compose logs -f routing_api
```

### Truy cập container

```bash
# Vào shell của API container
docker-compose exec routing_api bash
```

### Dừng/Khởi động services

```bash
# Dừng tất cả services (giữ lại data)
docker-compose down

# Dừng và xóa volumes (mất data)
docker-compose down -v

# Khởi động lại services
docker-compose restart

# Khởi động lại service cụ thể
docker-compose restart routing_api
```

### Xây dựng lại images

```bash
# Build lại images (nếu có thay đổi code)
docker-compose build --no-cache

# Build và chạy lại
docker-compose up -d --build
```

---

## Cấu trúc Docker Compose

### Services

#### 1. **routing_api** (FastAPI Application)
- Build: `./Dockerfile`
- Ports: `8000` (API)
- Environment: Kế thừa từ `.env`
- **Yêu cầu:** MongoDB instance chạy bên ngoài Docker

---

## Environment Variables

File `.env` chứa các biến cấu hình:

```env
# MongoDB Connection (external)
MONGODB_URI=mongodb://localhost:27017
DATABASE_NAME=routing_db

# API
API_PORT=8000
```

### MongoDB Connection Strings

**Local Development:**
```
MONGODB_URI=mongodb://localhost:27017
```

**With Authentication:**
```
MONGODB_URI=mongodb://username:password@mongodb_host:27017/?authSource=admin
```

**Remote MongoDB:**
```
MONGODB_URI=mongodb://username:password@192.168.1.100:27017/?authSource=admin
```

**MongoDB Atlas (Cloud):**
```
MONGODB_URI=mongodb+srv://username:password@cluster0.mongodb.net/dbname
```

---

## Dockerfile Explanation

File `Dockerfile` sử dụng multi-stage build:

```dockerfile
# Stage 1: Builder
FROM python:3.11-slim as builder
# - Cài đặt dependencies
# - Tối ưu kích thước layer

# Stage 2: Production
FROM python:3.11-slim
# - Copy only necessities
# - Giảm kích thước final image
# - Health check
# - Expose port 8000
```

**Lợi ích:**
- ✅ Final image nhẹ (~150MB)
- ✅ Nhanh hơn deployment
- ✅ Bảo mật tốt hơn

---

## Troubleshooting

### Lỗi: "Port 8000 already in use"

```bash
# Thay đổi port trong .env
API_PORT=8001

# Hoặc tìm và dừng process chiếm port (Windows)
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# (Linux)
lsof -i :8000
kill -9 <PID>
```

### Lỗi: MongoDB connection refused

```bash
# Kiểm tra MONGODB_URI trong .env
cat .env | grep MONGODB_URI

# Kiểm tra MongoDB chạy bên ngoài
# Cố gắng kết nối từ container
docker-compose exec routing_api bash
mongosh <MONGODB_URI>

# Nếu kết nối thành công → OK
# Nếu lỗi → kiểm tra MongoDB instance bên ngoài
```

### API container exits immediately

```bash
# Kiểm tra logs
docker-compose logs routing_api

# Rebuild image
docker-compose build --no-cache

# Run lại
docker-compose up
```

---

## Production Deployment

### Recommendations

1. **Environment Variables:** Sử dụng secret management (Kubernetes Secrets, Docker Secrets)
2. **Database:** Sử dụng managed MongoDB (MongoDB Atlas)
3. **Reverse Proxy:** Sử dụng Nginx/Traefik
4. **SSL/TLS:** Sử dụng Let's Encrypt
5. **Monitoring:** Thêm Prometheus + Grafana
6. **Logging:** Sử dụng ELK Stack

### Thay đổi MongoDB Connection cho Production

**MongoDB Atlas (Recommended):**
```bash
# 1. Tạo cluster trên MongoDB Atlas
# 2. Lấy connection string

# 3. Cập nhật .env
MONGODB_URI=mongodb+srv://username:password@cluster0.mongodb.net/routing_db

# 4. Restart container
docker-compose down
docker-compose up -d
```

### Scale deployment

Sử dụng Docker Swarm hoặc Kubernetes:

```bash
# Docker Swarm
docker swarm init
docker stack deploy -c docker-compose.yml routing

# Kubernetes
kubectl apply -f k8s-manifests/
```

---

## Monitoring & Health Checks

API endpoint:
```
GET /health
```

Response:
```json
{ "status": "ok" }
```

Docker health check: Tự động kiểm tra mỗi 30 giây

---

## Cleanup

Xóa tất cả:

```bash
docker-compose down -v --remove-orphans
docker system prune -a --volumes
```

---

## Support

Nếu gặp vấn đề:
1. Kiểm tra logs: `docker-compose logs -f`
2. Kiểm tra container: `docker-compose ps`
3. Restart services: `docker-compose restart`
4. Rebuild: `docker-compose build --no-cache && docker-compose up`
