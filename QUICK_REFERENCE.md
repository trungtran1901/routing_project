# ROUTING API - DOCKER QUICK REFERENCE

## 🎯 ONE-PAGE CHEAT SHEET

### ⚡ 30-SECOND SETUP

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Edit MONGODB_URI in .env
# Set to: mongodb://localhost:27017  (or your MongoDB URL)

# 3. Build and start
docker-compose build
docker-compose up -d

# 4. Open browser
# Go to: http://localhost:8000/docs
```

---

## 🪟 WINDOWS (PowerShell)

```powershell
# Copy template
Copy-Item .env.example .env

# Edit .env with MONGODB_URI

# Run interactive script
.\deploy.ps1
# Then choose option 1
```

---

## 🐧 LINUX/MAC (Bash)

```bash
# Copy template
cp .env.example .env

# Edit .env
nano .env

# Run interactive script
chmod +x deploy.sh
./deploy.sh
# Then choose option 1
```

---

## ⚙️ MONGODB URI EXAMPLES

```env
# Local (default)
MONGODB_URI=mongodb://localhost:27017

# Remote with password
MONGODB_URI=mongodb://user:pass@host:27017/?authSource=admin

# Cloud (MongoDB Atlas)
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/dbname
```

---

## 🌐 ACCESS POINTS

| What | URL |
|------|-----|
| API Docs | http://localhost:8000/docs |
| Alternative | http://localhost:8000/redoc |
| Health | http://localhost:8000/health |

---

## 📊 ESSENTIAL COMMANDS

| Command | Purpose |
|---------|---------|
| `docker-compose build` | Build image |
| `docker-compose up -d` | Start container |
| `docker-compose down` | Stop container |
| `docker-compose ps` | Show status |
| `docker-compose logs -f routing_api` | View logs |
| `docker-compose exec routing_api bash` | Shell access |
| `docker-compose down -v` | Clean up |

---

## 🆘 TROUBLESHOOTING

### MongoDB won't connect?
```bash
# 1. Check .env
cat .env | grep MONGODB_URI

# 2. Verify MongoDB is running
mongosh <your_mongodb_uri>

# 3. Check logs
docker-compose logs routing_api
```

### Port 8000 already in use?
```bash
# Edit .env:
API_PORT=8001

# Restart
docker-compose down
docker-compose up -d
```

### Container exits immediately?
```bash
# See detailed logs
docker-compose logs routing_api

# Rebuild
docker-compose build --no-cache
docker-compose up -d
```

---

## 📁 KEY FILES

| File | Purpose |
|------|---------|
| `Dockerfile` | Build configuration |
| `docker-compose.yml` | Orchestration |
| `.env.example` | Config template |
| `deploy.ps1` | Windows helper |
| `deploy.sh` | Linux/Mac helper |
| `00_START_HERE.md` | Full guide |

---

## ✅ VERIFICATION

```bash
# Is Docker running?
docker ps

# Is image built?
docker images | grep routing

# Is container running?
docker-compose ps

# Is API responding?
curl http://localhost:8000/health
```

---

## 🚀 COMMON WORKFLOWS

### Development (Local MongoDB)
```bash
# 1. Edit .env
MONGODB_URI=mongodb://localhost:27017

# 2. Start local MongoDB (outside Docker)
mongod

# 3. Start API
docker-compose up -d
```

### Production (MongoDB Atlas)
```bash
# 1. Create MongoDB Atlas account
# 2. Get connection string
# 3. Edit .env
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/dbname

# 4. Deploy
docker-compose build
docker-compose up -d
```

### Testing
```bash
# 1. See logs in real-time
docker-compose logs -f routing_api

# 2. Access container
docker-compose exec routing_api bash

# 3. Test endpoints
curl http://localhost:8000/health
curl http://localhost:8000/docs
```

---

## 📝 CHECKLIST

Before deploying:
- [ ] Docker installed?
- [ ] MongoDB accessible?
- [ ] .env configured?
- [ ] Port 8000 free?
- [ ] `docker-compose build` ok?
- [ ] `docker-compose up -d` ok?
- [ ] Can access http://localhost:8000/docs?

---

## 🎓 MORE INFO

**For complete guide:** See `00_START_HERE.md`  
**For production:** See `DEPLOYMENT.md`  
**For troubleshooting:** See `DOCKER_QUICKSTART.md`

---

**Generated:** May 25, 2026  
**Keep this handy while deploying!** 📌
