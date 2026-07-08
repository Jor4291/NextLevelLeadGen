$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$PythonExe = Join-Path $Root ".venv\Scripts\python.exe"
$FrontendDir = Join-Path $Root "frontend"

if (-not (Test-Path $PythonExe)) {
    Write-Host "Creating Python virtual environment..."
    python -m venv .venv
}

if (-not (Test-Path $PythonExe)) {
    Write-Error "Python virtual environment not found at $PythonExe"
    exit 1
}

if (-not (Test-Path ".venv\Lib\site-packages\fastapi")) {
    Write-Host "Installing Python dependencies..."
    & $PythonExe -m pip install -r requirements.txt
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
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
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

$ApiPort = 8000
$UiPort = 5173

Stop-ListenerOnPort -Port $ApiPort -Label "API"
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

$frontendCmd = "Set-Location '$FrontendDir'; npm run dev"
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
