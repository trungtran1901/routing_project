#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Routing API - Docker Deployment Helper${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}\n"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker not found. Please install Docker first.${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}✗ Docker Compose not found. Please install Docker Compose first.${NC}"
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠ .env file not found. Creating from .env.example...${NC}"
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${GREEN}✓ .env created from .env.example${NC}\n"
    else
        echo -e "${RED}✗ .env.example not found${NC}"
        exit 1
    fi
fi

# Display menu
echo -e "${BLUE}Select an option:${NC}\n"
echo "1) Build and Start (build + up)"
echo "2) Start services (up)"
echo "3) Stop services (down)"
echo "4) View logs (API)"
echo "5) View logs (MongoDB)"
echo "6) View all logs"
echo "7) Show status (ps)"
echo "8) Access API shell"
echo "9) Access MongoDB shell"
echo "10) Clean everything (down -v)"
echo "11) Rebuild (clean + build + up)"
echo "0) Exit"
echo ""

read -p "Enter your choice [0-11]: " choice

case $choice in
    1)
        echo -e "\n${YELLOW}Building Docker images...${NC}"
        docker-compose build
        echo -e "\n${YELLOW}Starting services...${NC}"
        docker-compose up -d
        sleep 5
        echo -e "\n${GREEN}✓ Services started successfully!${NC}"
        echo -e "${BLUE}URLs:${NC}"
        echo "  • API: http://localhost:8000"
        echo "  • Swagger UI: http://localhost:8000/docs"
        echo "  • ReDoc: http://localhost:8000/redoc"
        echo "  • MongoDB Express: http://localhost:8081"
        echo ""
        ;;
    2)
        echo -e "\n${YELLOW}Starting services...${NC}"
        docker-compose up -d
        echo -e "${GREEN}✓ Services started${NC}\n"
        docker-compose ps
        ;;
    3)
        echo -e "\n${YELLOW}Stopping services...${NC}"
        docker-compose down
        echo -e "${GREEN}✓ Services stopped${NC}\n"
        ;;
    4)
        echo -e "\n${BLUE}API Logs (Press Ctrl+C to exit)${NC}\n"
        docker-compose logs -f routing_api
        ;;
    5)
        echo -e "\n${BLUE}MongoDB Logs (Press Ctrl+C to exit)${NC}\n"
        docker-compose logs -f mongodb
        ;;
    6)
        echo -e "\n${BLUE}All Logs (Press Ctrl+C to exit)${NC}\n"
        docker-compose logs -f
        ;;
    7)
        echo -e "\n${BLUE}Container Status:${NC}\n"
        docker-compose ps
        ;;
    8)
        echo -e "\n${BLUE}Accessing API shell...${NC}\n"
        docker-compose exec routing_api bash
        ;;
    9)
        echo -e "\n${BLUE}Accessing MongoDB shell...${NC}\n"
        docker-compose exec mongodb mongosh -u admin -p admin123 --authenticationDatabase admin
        ;;
    10)
        echo -e "\n${YELLOW}Cleaning up everything...${NC}"
        docker-compose down -v
        echo -e "${GREEN}✓ Cleaned up${NC}\n"
        ;;
    11)
        echo -e "\n${YELLOW}Full rebuild...${NC}"
        docker-compose down -v
        docker-compose build --no-cache
        docker-compose up -d
        sleep 5
        echo -e "\n${GREEN}✓ Rebuild completed!${NC}"
        echo -e "${BLUE}URLs:${NC}"
        echo "  • API: http://localhost:8000"
        echo "  • Swagger UI: http://localhost:8000/docs"
        echo "  • MongoDB Express: http://localhost:8081"
        echo ""
        ;;
    0)
        echo -e "${BLUE}Goodbye!${NC}\n"
        exit 0
        ;;
    *)
        echo -e "${RED}✗ Invalid choice${NC}"
        exit 1
        ;;
esac
