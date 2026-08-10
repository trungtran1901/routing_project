#!/bin/bash

# Docker Setup Verification Script

echo "════════════════════════════════════════════════════════"
echo "  Docker Setup Verification"
echo "════════════════════════════════════════════════════════"
echo ""

# Check Docker
echo "1. Checking Docker installation..."
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version)
    echo "   ✓ Docker: $DOCKER_VERSION"
else
    echo "   ✗ Docker not found"
    exit 1
fi

# Check Docker Compose
echo ""
echo "2. Checking Docker Compose installation..."
if command -v docker-compose &> /dev/null; then
    COMPOSE_VERSION=$(docker-compose --version)
    echo "   ✓ Docker Compose: $COMPOSE_VERSION"
else
    echo "   ✗ Docker Compose not found"
    exit 1
fi

# Check .env
echo ""
echo "3. Checking .env file..."
if [ -f ".env" ]; then
    echo "   ✓ .env found"
    MONGO_URI=$(grep "MONGODB_URI" .env | cut -d '=' -f 2)
    echo "   → MONGODB_URI: $MONGO_URI"
else
    echo "   ⚠ .env not found. Creating from .env.example..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "   ✓ .env created"
    else
        echo "   ✗ .env.example not found"
        exit 1
    fi
fi

# Check Dockerfile
echo ""
echo "4. Checking Dockerfile..."
if [ -f "Dockerfile" ]; then
    echo "   ✓ Dockerfile found"
else
    echo "   ✗ Dockerfile not found"
    exit 1
fi

# Check docker-compose.yml
echo ""
echo "5. Checking docker-compose.yml..."
if [ -f "docker-compose.yml" ]; then
    echo "   ✓ docker-compose.yml found"
    SERVICES=$(grep "services:" -A 50 docker-compose.yml | grep "^  [a-z]" | awk '{print $1}')
    echo "   → Services: $(echo $SERVICES | tr '\n' ', ')"
else
    echo "   ✗ docker-compose.yml not found"
    exit 1
fi

# Check Docker daemon
echo ""
echo "6. Checking Docker daemon..."
if docker ps > /dev/null 2>&1; then
    echo "   ✓ Docker daemon is running"
else
    echo "   ✗ Docker daemon is not running"
    echo "   → Please start Docker Desktop or Docker daemon"
    exit 1
fi

# Check existing containers
echo ""
echo "7. Checking existing containers..."
RUNNING=$(docker ps --filter "name=routing" --format "{{.Names}}")
if [ -z "$RUNNING" ]; then
    echo "   ℹ No routing containers running (first time setup)"
else
    echo "   ✓ Found running containers:"
    echo "   → $RUNNING"
fi

# Verify MongoDB connection (optional)
echo ""
echo "8. (Optional) Verifying MongoDB connection..."
MONGODB_URI=$(grep "MONGODB_URI" .env | cut -d '=' -f 2 | tr -d ' ')
if [ -z "$MONGODB_URI" ]; then
    echo "   ⚠ MONGODB_URI not configured in .env"
    echo "   → Please update MONGODB_URI in .env before starting"
else
    echo "   ℹ MONGODB_URI configured: $MONGODB_URI"
    echo "   → Will verify connection when running container"
fi

# Summary
echo ""
echo "════════════════════════════════════════════════════════"
echo "✓ All checks passed! Ready to deploy."
echo "════════════════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo "  1. Update MONGODB_URI in .env if needed"
echo "  2. Run: docker-compose build"
echo "  3. Run: docker-compose up -d"
echo "  4. Access: http://localhost:8000/docs"
echo ""
