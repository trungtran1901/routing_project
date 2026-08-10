.PHONY: help build up down logs clean restart rebuild ps shell

help:
	@echo "Available commands:"
	@echo "  make build          - Build Docker image"
	@echo "  make up             - Start API container"
	@echo "  make down           - Stop API container"
	@echo "  make restart        - Restart API container"
	@echo "  make rebuild        - Rebuild and restart"
	@echo "  make logs           - View API logs (live)"
	@echo "  make ps             - Show running containers"
	@echo "  make clean          - Remove containers and volumes"
	@echo "  make shell          - Open shell in API container"
	@echo "  make env-setup      - Create .env from .env.example"
	@echo "  make verify         - Verify Docker setup"

build:
	docker-compose build

up:
	docker-compose up -d
	@echo "✓ API started at http://localhost:8000"
	@echo "  Swagger UI: http://localhost:8000/docs"

down:
	docker-compose down
	@echo "✓ API stopped"

restart: down up

rebuild: clean build up

ps:
	docker-compose ps

logs:
	docker-compose logs -f routing_api

clean:
	docker-compose down -v
	@echo "✓ All containers and volumes removed"

shell:
	docker-compose exec routing_api bash

env-setup:
	cp .env.example .env
	@echo "✓ Created .env file from .env.example"

verify:
	@bash verify-docker-setup.sh
