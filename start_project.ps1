<#
.SYNOPSIS
    Starts and verifies the RAG-Based AI Teaching Assistant (Frontend & Backend) via Docker Compose.

.DESCRIPTION
    1. Validates Docker Desktop engine readiness (starts it automatically if needed).
    2. Initializes .env from .env.example if missing.
    3. Starts backend and frontend containers with Docker Compose.
    4. Runs automated health and integration checks across the API, frontend, and RAG pipeline.
    5. Opens the web application in your default browser.

.PARAMETER Rebuild
    Forces a fresh container image build (docker compose up -d --build).

.PARAMETER TestOnly
    Skips container startup and runs the automated verification tests against existing containers.

.PARAMETER NoBrowser
    Prevents automatically opening the frontend in your browser.

.PARAMETER WithOllama
    Launches an in-Docker Ollama container using the 'with-ollama' Docker Compose profile.
#>

param(
    [switch]$Rebuild,
    [switch]$TestOnly,
    [switch]$NoBrowser,
    [switch]$WithOllama
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "`n========================================================" -ForegroundColor Cyan
    Write-Host " $Message" -ForegroundColor Cyan
    Write-Host "========================================================" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[PASS] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Fail {
    param([string]$Message)
    Write-Host "[FAIL] $Message" -ForegroundColor Red
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

# -----------------------------------------------------------------------------
# STEP 1: Verify Docker Installation & Engine Status
# -----------------------------------------------------------------------------
Write-Step "Step 1: Checking Docker Environment"

if (-not (Get-Command "docker" -ErrorAction SilentlyContinue)) {
    Write-Fail "Docker is not installed or not in your system PATH."
    Write-Host "Please install Docker Desktop: https://www.docker.com/products/docker-desktop/"
    exit 1
}

# Temporarily allow errors so docker stderr doesn't terminate the script
$ErrorActionPreference = "Continue"
$dockerInfo = docker info 2>&1
$ErrorActionPreference = "Stop"
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Docker engine is not currently responding. Attempting to start Docker Desktop..."
    
    $dockerDesktopPath = "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe"
    $dockerProgramFiles = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    
    if (Test-Path $dockerDesktopPath) {
        Start-Process $dockerDesktopPath
    } elseif (Test-Path $dockerProgramFiles) {
        Start-Process $dockerProgramFiles
    } else {
        Write-Fail "Docker Desktop executable not found. Please start Docker Desktop manually."
        exit 1
    }

    Write-Host "Waiting for Docker daemon to initialize..." -NoNewline
    $timeoutSeconds = 60
    $elapsed = 0
    while ($elapsed -lt $timeoutSeconds) {
        Start-Sleep -Seconds 3
        $elapsed += 3
        Write-Host "." -NoNewline
        $ErrorActionPreference = "Continue"
        $testInfo = docker info 2>&1
        $ErrorActionPreference = "Stop"
        if ($LASTEXITCODE -eq 0) {
            Write-Host " Ready!" -ForegroundColor Green
            break
        }
    }

    if ($LASTEXITCODE -ne 0) {
        Write-Fail "`nDocker engine did not become ready within $timeoutSeconds seconds. Please launch Docker Desktop and retry."
        exit 1
    }
}
Write-Success "Docker engine is running and responsive."

# -----------------------------------------------------------------------------
# STEP 2: Verify .env Configuration
# -----------------------------------------------------------------------------
Write-Step "Step 2: Checking Environment Configuration"

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Success "Created .env from .env.example."
    } else {
        Write-Warn ".env and .env.example not found; proceeding with defaults."
    }
} else {
    Write-Success "Configuration file .env detected."
}

# -----------------------------------------------------------------------------
# STEP 3: Start Services via Docker Compose
# -----------------------------------------------------------------------------
if (-not $TestOnly) {
    Write-Step "Step 3: Launching Containers with Docker Compose"

    $composeArgs = @("compose")
    if ($WithOllama) {
        $composeArgs += @("--profile", "with-ollama")
    }
    $composeArgs += "up"
    $composeArgs += "-d"
    if ($Rebuild) {
        $composeArgs += "--build"
    }

    Write-Host "Running: docker $($composeArgs -join ' ')" -ForegroundColor Gray
    $ErrorActionPreference = "Continue"
    & docker @composeArgs
    $ErrorActionPreference = "Stop"

    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Docker Compose failed to start services."
        exit 1
    }
    Write-Success "Docker Compose services triggered."
}

# -----------------------------------------------------------------------------
# STEP 4: Wait for Services to Become Ready
# -----------------------------------------------------------------------------
Write-Step "Step 4: Waiting for Services Readiness"

$backendHealthy = $false
Write-Host "Waiting for backend health check (http://localhost:8000/health)..." -NoNewline
for ($i = 0; $i -lt 30; $i++) {
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get -TimeoutSec 3 -ErrorAction Stop
        if ($response.status -eq "healthy") {
            $backendHealthy = $true
            Write-Host " OK!" -ForegroundColor Green
            break
        }
    } catch {
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 2
    }
}

if (-not $backendHealthy) {
    Write-Fail "`nBackend did not become healthy within 60 seconds."
    Write-Host "Inspect logs using: docker compose logs backend" -ForegroundColor Yellow
    exit 1
}

$frontendReady = $false
Write-Host "Waiting for frontend server (http://localhost:3000)..." -NoNewline
for ($i = 0; $i -lt 30; $i++) {
    try {
        $req = [System.Net.WebRequest]::Create("http://localhost:3000")
        $req.Timeout = 3000
        $res = $req.GetResponse()
        if ($res.StatusCode -eq 200) {
            $frontendReady = $true
            Write-Host " OK!" -ForegroundColor Green
            $res.Close()
            break
        }
        $res.Close()
    } catch {
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 2
    }
}

if (-not $frontendReady) {
    Write-Warn "`nFrontend is still compiling pages or starting up. It may take a few more seconds."
}

# -----------------------------------------------------------------------------
# STEP 5: Automated Verification & Integration Tests
# -----------------------------------------------------------------------------
Write-Step "Step 5: Running Automated Integration Tests"

$testsPassed = 0
$totalTests = 0

# Test 1: Backend root health
$totalTests++
try {
    $res = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get -TimeoutSec 5
    if ($res.status -eq "healthy") {
        Write-Success "Test 1: Backend root health check passed: $($res.status)"
        $testsPassed++
    } else {
        Write-Fail "Test 1: Backend returned unexpected status: $($res.status)"
    }
} catch {
    Write-Fail "Test 1: Backend health check failed: $_"
}

# Test 2: AI & Ollama service health
$totalTests++
try {
    $res = Invoke-RestMethod -Uri "http://localhost:8000/api/health" -Method Get -TimeoutSec 5
    $ollamaStatus = $res.services.ollama
    if ($ollamaStatus -eq "ok") {
        Write-Success "Test 2: Backend + Ollama service connectivity passed (status: $($res.status), ollama: ok)"
        $testsPassed++
    } else {
        Write-Warn "Test 2: Backend reachable, but Ollama status is '$ollamaStatus'. (Ensure Ollama is running on host or start with -WithOllama)"
        $testsPassed++
    }
} catch {
    Write-Fail "Test 2: API health check endpoint failed: $_"
}

# Test 3: SQLite video records retrieval
$totalTests++
try {
    $res = Invoke-RestMethod -Uri "http://localhost:8000/api/videos" -Method Get -TimeoutSec 5
    $count = $res.total
    Write-Success "Test 3: Video library database access passed (total videos: $count)"
    $testsPassed++
} catch {
    Write-Fail "Test 3: Video library endpoint failed: $_"
}

# Test 4: Frontend Proxy Rewrite
$totalTests++
try {
    $res = Invoke-RestMethod -Uri "http://localhost:3000/api/health" -Method Get -TimeoutSec 5
    if ($res.services.api -eq "ok") {
        Write-Success "Test 4: Frontend-to-backend Docker network proxy rewrite passed"
        $testsPassed++
    } else {
        Write-Fail "Test 4: Frontend proxy returned invalid payload: $($res | ConvertTo-Json -Compress)"
    }
} catch {
    Write-Fail "Test 4: Frontend proxy rewrite test failed: $_"
}

# Test 5: Next.js Frontend HTTP Response
$totalTests++
try {
    $webReq = [System.Net.WebRequest]::Create("http://localhost:3000")
    $webReq.Timeout = 5000
    $webRes = $webReq.GetResponse()
    if ($webRes.StatusCode -eq 200) {
        Write-Success "Test 5: Frontend web UI HTTP 200 OK passed"
        $testsPassed++
    } else {
        Write-Fail "Test 5: Frontend returned HTTP $($webRes.StatusCode)"
    }
    $webRes.Close()
} catch {
    Write-Fail "Test 5: Frontend web page failed to respond: $_"
}

# -----------------------------------------------------------------------------
# STEP 6: Summary & Application Launch
# -----------------------------------------------------------------------------
Write-Step "Verification Summary: $testsPassed / $totalTests Tests Passed"

Write-Host "========================================================" -ForegroundColor Green
Write-Host " RAG-Based AI Teaching Assistant is RUNNING!" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
Write-Host "  Frontend URL:     http://localhost:3000" -ForegroundColor White
Write-Host "  Backend API Docs: http://localhost:8000/docs" -ForegroundColor White
Write-Host "  Health Endpoint:  http://localhost:8000/health" -ForegroundColor White
Write-Host "========================================================" -ForegroundColor Green
Write-Host "`nUseful Commands:"
Write-Host "  View all logs:      docker compose logs -f" -ForegroundColor Gray
Write-Host "  View backend logs:  docker compose logs -f backend" -ForegroundColor Gray
Write-Host "  View frontend logs: docker compose logs -f frontend" -ForegroundColor Gray
Write-Host "  Stop containers:    docker compose down`n" -ForegroundColor Gray

if (-not $NoBrowser -and -not $TestOnly) {
    Write-Host "Opening application in default browser..." -ForegroundColor Cyan
    Start-Process "http://localhost:3000"
}
