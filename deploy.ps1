# Routing API - Docker Deployment Helper (PowerShell)

function Write-Title {
    Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host "  Routing API - Docker Deployment Helper" -ForegroundColor Cyan
    Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host ""
}

function Check-Prerequisites {
    # Check Docker
    try {
        $null = docker --version
    } catch {
        Write-Host "✗ Docker not found. Please install Docker Desktop." -ForegroundColor Red
        exit 1
    }

    # Check Docker Compose
    try {
        $null = docker-compose --version
    } catch {
        Write-Host "✗ Docker Compose not found. Please install Docker Compose." -ForegroundColor Red
        exit 1
    }

    # Check .env
    if (!(Test-Path ".env")) {
        Write-Host "⚠ .env file not found. Creating from .env.example..." -ForegroundColor Yellow
        if (Test-Path ".env.example") {
            Copy-Item ".env.example" ".env"
            Write-Host "✓ .env created from .env.example" -ForegroundColor Green
            Write-Host ""
        } else {
            Write-Host "✗ .env.example not found" -ForegroundColor Red
            exit 1
        }
    }
}

function Show-Menu {
    Write-Host "Select an option:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "1) Build and Start (build + up)"
    Write-Host "2) Start services (up)"
    Write-Host "3) Stop services (down)"
    Write-Host "4) View logs (API)"
    Write-Host "5) View logs (MongoDB)"
    Write-Host "6) View all logs"
    Write-Host "7) Show status (ps)"
    Write-Host "8) Access API shell"
    Write-Host "9) Access MongoDB shell"
    Write-Host "10) Clean everything (down -v)"
    Write-Host "11) Rebuild (clean + build + up)"
    Write-Host "0) Exit"
    Write-Host ""
}

function Execute-Choice {
    param([int]$Choice)

    switch ($Choice) {
        1 {
            Write-Host "`nBuilding Docker images..." -ForegroundColor Yellow
            docker-compose build
            Write-Host "`nStarting services..." -ForegroundColor Yellow
            docker-compose up -d
            Start-Sleep -Seconds 5
            Write-Host "`n✓ Services started successfully!" -ForegroundColor Green
            Write-Host "URLs:" -ForegroundColor Cyan
            Write-Host "  • API: http://localhost:8000"
            Write-Host "  • Swagger UI: http://localhost:8000/docs"
            Write-Host "  • ReDoc: http://localhost:8000/redoc"
            Write-Host "  • MongoDB Express: http://localhost:8081"
            Write-Host ""
        }
        2 {
            Write-Host "`nStarting services..." -ForegroundColor Yellow
            docker-compose up -d
            Write-Host "✓ Services started" -ForegroundColor Green
            Write-Host ""
            docker-compose ps
        }
        3 {
            Write-Host "`nStopping services..." -ForegroundColor Yellow
            docker-compose down
            Write-Host "✓ Services stopped" -ForegroundColor Green
            Write-Host ""
        }
        4 {
            Write-Host "`nAPI Logs (Press Ctrl+C to exit)" -ForegroundColor Cyan
            Write-Host ""
            docker-compose logs -f routing_api
        }
        5 {
            Write-Host "`nMongoDB Logs (Press Ctrl+C to exit)" -ForegroundColor Cyan
            Write-Host ""
            docker-compose logs -f mongodb
        }
        6 {
            Write-Host "`nAll Logs (Press Ctrl+C to exit)" -ForegroundColor Cyan
            Write-Host ""
            docker-compose logs -f
        }
        7 {
            Write-Host "`nContainer Status:" -ForegroundColor Cyan
            Write-Host ""
            docker-compose ps
        }
        8 {
            Write-Host "`nAccessing API shell..." -ForegroundColor Cyan
            Write-Host ""
            docker-compose exec routing_api bash
        }
        9 {
            Write-Host "`nAccessing MongoDB shell..." -ForegroundColor Cyan
            Write-Host ""
            docker-compose exec mongodb mongosh -u admin -p admin123 --authenticationDatabase admin
        }
        10 {
            Write-Host "`nCleaning up everything..." -ForegroundColor Yellow
            docker-compose down -v
            Write-Host "✓ Cleaned up" -ForegroundColor Green
            Write-Host ""
        }
        11 {
            Write-Host "`nFull rebuild..." -ForegroundColor Yellow
            docker-compose down -v
            docker-compose build --no-cache
            docker-compose up -d
            Start-Sleep -Seconds 5
            Write-Host "`n✓ Rebuild completed!" -ForegroundColor Green
            Write-Host "URLs:" -ForegroundColor Cyan
            Write-Host "  • API: http://localhost:8000"
            Write-Host "  • Swagger UI: http://localhost:8000/docs"
            Write-Host "  • MongoDB Express: http://localhost:8081"
            Write-Host ""
        }
        0 {
            Write-Host "Goodbye!" -ForegroundColor Cyan
            Write-Host ""
            exit 0
        }
        default {
            Write-Host "✗ Invalid choice" -ForegroundColor Red
            exit 1
        }
    }
}

# Main script
Write-Title
Check-Prerequisites
Show-Menu

$choice = Read-Host "Enter your choice [0-11]"
[int]$intChoice = 0

if ([int]::TryParse($choice, [ref]$intChoice)) {
    Execute-Choice $intChoice
} else {
    Write-Host "✗ Invalid input" -ForegroundColor Red
}
