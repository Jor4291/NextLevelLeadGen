$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$PythonExe = Join-Path $Root ".venv\Scripts\python.exe"
$FrontendDir = Join-Path $Root "frontend"

function Get-SystemPython {
    $candidates = @()

    foreach ($cmd in @("py", "python", "python3")) {
        $resolved = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($resolved -and $resolved.Source -notmatch "WindowsApps") {
            if ($cmd -eq "py") {
                $candidates += @{ Path = $resolved.Source; Args = @("-3") }
            } else {
                $candidates += @{ Path = $resolved.Source; Args = @() }
            }
        }
    }

    $localPythonRoot = Join-Path $env:LOCALAPPDATA "Programs\Python"
    if (Test-Path $localPythonRoot) {
        Get-ChildItem $localPythonRoot -Directory -Filter "Python*" -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object {
                $exe = Join-Path $_.FullName "python.exe"
                if (Test-Path $exe) {
                    $candidates += @{ Path = $exe; Args = @() }
                }
            }

        $pyLauncher = Join-Path $localPythonRoot "Launcher\py.exe"
        if (Test-Path $pyLauncher) {
            $candidates += @{ Path = $pyLauncher; Args = @("-3") }
        }
    }

    Get-ChildItem "C:\Program Files\Python*" -Directory -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending |
        ForEach-Object {
            $exe = Join-Path $_.FullName "python.exe"
            if (Test-Path $exe) {
                $candidates += @{ Path = $exe; Args = @() }
            }
        }

    foreach ($candidate in $candidates) {
        if (-not (Test-Path $candidate.Path)) { continue }
        if ($candidate.Path -match "WindowsApps") { continue }
        if ((Get-Item $candidate.Path).Length -lt 1024) { continue }
        try {
            if ($candidate.Args.Count -gt 0) {
                & $candidate.Path @($candidate.Args) --version *> $null
            } else {
                & $candidate.Path --version *> $null
            }
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        } catch {
            continue
        }
    }

    return $null
}

$SystemPython = Get-SystemPython

if (-not (Test-Path $PythonExe)) {
    if (-not $SystemPython) {
        Write-Error @"
Python was not found.

Install Python 3.11+ from https://www.python.org/downloads/ and check "Add python.exe to PATH".
Also disable Windows Store aliases: Settings -> Apps -> Advanced app settings -> App execution aliases -> turn OFF python.exe and python3.exe.
Then close and reopen PowerShell.
"@
        exit 1
    }

    Write-Host "Creating Python virtual environment with $($SystemPython.Path)..."
    if ($SystemPython.Args.Count -gt 0) {
        & $SystemPython.Path @($SystemPython.Args) -m venv .venv
    } else {
        & $SystemPython.Path -m venv .venv
    }
}

if (-not (Test-Path $PythonExe)) {
    Write-Error "Python virtual environment not found at $PythonExe"
    exit 1
}

if (-not (Test-Path ".venv\Lib\site-packages\fastapi")) {
    Write-Host "Installing Python dependencies..."
    & $PythonExe -m pip install -r requirements.txt
}

$playwrightMarker = Join-Path $Root ".venv\Lib\site-packages\playwright"
if ((Test-Path $playwrightMarker) -and -not (Test-Path (Join-Path $env:LOCALAPPDATA "ms-playwright"))) {
    Write-Host "Installing Playwright Chromium (required for scraping)..."
    & $PythonExe -m playwright install chromium
}

if (-not (Test-Path "frontend\node_modules")) {
    Write-Host "Installing frontend dependencies..."
    Push-Location $FrontendDir
    npm install
    Pop-Location
}

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    Write-Error "npm not found. Install Node.js from https://nodejs.org/"
    exit 1
}

if (-not (Test-Path ".env")) {
    # .env.example targets production (Postgres + auth). For local dev we write a
    # SQLite + no-auth config so the API starts without external services.
    $localEnv = @'
# Local development — SQLite + no auth (see .env.example for production/Postgres)
# DATABASE_URL unset falls back to local SQLite at data/leads.db

# Scraping
SCRAPE_RATE_LIMIT_SECONDS=2
SCRAPE_USER_AGENT=NextLevelLeadBot/1.0 (+https://nextlevelstudio.com)
SKIP_WEBSITE_RESOLUTION=false
SKIP_JOB_SIGNALS=false
MAX_COMPANIES_PER_JOB=25

# Auth — disabled for local dev (no login screen)
AUTH_REQUIRED=false
JWT_SECRET=local-dev-secret
JWT_EXPIRE_HOURS=72
ALLOW_REGISTRATION=false
ADMIN_EMAIL=
ADMIN_PASSWORD=
ADMIN_NAME=Admin

# Comma-separated frontend URLs
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# Google Sheets (optional)
GOOGLE_SHEETS_CREDENTIALS_PATH=./credentials/google-service-account.json
GOOGLE_SHEET_ID=

# Email canvas — Phase 2 (optional)
RESEND_API_KEY=
EMAIL_FROM=info@nextlevelstudio.com
EMAIL_FROM_NAME=Next Level Studio
'@
    Set-Content -Path ".env" -Value $localEnv -Encoding UTF8
    Write-Host "Created local dev .env (SQLite + no auth). See .env.example for production settings."
}

New-Item -ItemType Directory -Force -Path "data" | Out-Null
New-Item -ItemType Directory -Force -Path "credentials" | Out-Null

function Get-ListenerProcessId {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($conn) { return [int]$conn.OwningProcess }
    return $null
}

function Stop-ListenerOnPort {
    param(
        [int]$Port,
        [string]$Label
    )
    $processId = Get-ListenerProcessId -Port $Port
    if (-not $processId) { return }
    Write-Host "Port $Port in use (process $processId) - stopping $Label..."
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

function Test-PortBindable {
    # Some Windows ports are reserved (Hyper-V/WSL/WinNAT) and reject binding even
    # when nothing is listening. Try to actually bind to confirm the port is usable.
    param([int]$Port)
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        $listener.Stop()
        return $true
    } catch {
        return $false
    }
}

function Get-UsableApiPort {
    param([int[]]$Candidates)
    foreach ($port in $Candidates) {
        Stop-ListenerOnPort -Port $port -Label "API"
        if (Test-PortBindable -Port $port) { return $port }
        Write-Host "Port $port is reserved or blocked - trying next..."
    }
    return $null
}

$UiPort = 5173
$ApiPort = Get-UsableApiPort -Candidates @(8000, 8010, 8020, 8080, 8100)

if (-not $ApiPort) {
    Write-Error "No usable API port found (tried 8000, 8010, 8020, 8080, 8100)."
    exit 1
}

Stop-ListenerOnPort -Port $UiPort -Label "dashboard"

Write-Host ""
Write-Host "Starting Next Level Studio Lead Generator in separate windows..."
Write-Host "  API:       http://127.0.0.1:$ApiPort"
Write-Host "  Dashboard: http://localhost:$UiPort"
Write-Host ""

$backendCmd = "& '$PythonExe' -m uvicorn backend.main:app --reload --host 127.0.0.1 --port $ApiPort"
Start-Process powershell.exe -WorkingDirectory $Root -WindowStyle Minimized -ArgumentList @(
    "-NoExit",
    "-Command",
    $backendCmd
)

# Pass the chosen API port to Vite so its /api proxy targets the right backend.
$frontendCmd = "`$env:API_PORT='$ApiPort'; Set-Location '$FrontendDir'; npm run dev"
Start-Process powershell.exe -WorkingDirectory $FrontendDir -WindowStyle Minimized -ArgumentList @(
    "-NoExit",
    "-Command",
    $frontendCmd
)

Start-Sleep -Seconds 4

$apiUp = Get-ListenerProcessId -Port $ApiPort
$uiUp = Get-ListenerProcessId -Port $UiPort

if ($apiUp) {
    Write-Host "API started on port $ApiPort."
} else {
    Write-Warning "API did not start. Check the backend PowerShell window for errors."
}

if ($uiUp) {
    Write-Host "Dashboard started on port $UiPort."
} else {
    Write-Warning "Dashboard did not start. Check the frontend PowerShell window for errors."
}

Write-Host ""
Write-Host "Close the two minimized PowerShell windows to stop the servers."
Write-Host ""
