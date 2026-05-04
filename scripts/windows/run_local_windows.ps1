param(
    [string]$TargetDir = "C:\NiceCount",
    [int]$AppPort = 8000,
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Throw-Friendly {
    param([string]$Message)
    throw $Message
}

function Stop-NiceCountServer {
    param(
        [string]$RepoDir,
        [int]$Port
    )

    $pidFile = Join-Path $RepoDir ".nicecount.pid"
    $stopped = $false

    if (Test-Path $pidFile) {
        $pidValue = (Get-Content $pidFile | Select-Object -First 1).Trim()
        if ($pidValue -match "^\d+$") {
            $serverProcess = Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue
            if ($serverProcess) {
                Write-Step "Stopping existing NiceCount server (PID $pidValue)"
                Stop-Process -Id ([int]$pidValue) -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 2
                $stopped = $true
            }
        }
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }

    if (-not $stopped) {
        try {
            $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop | Select-Object -First 1
            if ($listener -and $listener.OwningProcess) {
                Write-Step "Stopping process on port $Port (PID $($listener.OwningProcess))"
                Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 2
            }
        }
        catch {
        }
    }
}

function Wait-ForHealth {
    param([int]$Port)

    $healthUrl = "http://127.0.0.1:$Port/health"
    Write-Host "Waiting for server to be ready" -NoNewline
    for ($index = 0; $index -lt 90; $index++) {
        Start-Sleep -Seconds 1
        Write-Host "." -NoNewline
        try {
            $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200 -and $response.Content -match '"status"\s*:\s*"ok"') {
                Write-Host ""
                return $true
            }
        }
        catch {
        }
    }

    Write-Host ""
    return $false
}

function Start-NiceCountServer {
    param(
        [string]$RepoDir,
        [string]$PythonPath,
        [int]$Port,
        [switch]$OpenBrowserValue
    )

    Write-Step "Starting NiceCount server"
    $logsDir = Join-Path $RepoDir "logs"
    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null

    $stdoutLog = Join-Path $logsDir "nicecount.out.log"
    $stderrLog = Join-Path $logsDir "nicecount.err.log"
    $pidFile = Join-Path $RepoDir ".nicecount.pid"

    $serverArgs = @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$Port")

    $process = Start-Process -FilePath $PythonPath -ArgumentList $serverArgs -WorkingDirectory $RepoDir -PassThru -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog
    Set-Content -Path $pidFile -Value $process.Id -Encoding ASCII

    if (-not (Wait-ForHealth -Port $Port)) {
        Throw-Friendly "NiceCount server did not become healthy. Check logs at:`n  $stdoutLog`n  $stderrLog"
    }

    Write-Host ""
    Write-Host "NiceCount is running!" -ForegroundColor Green
    Write-Host "Login URL : http://127.0.0.1:$Port/login"
    Write-Host "PID file  : $pidFile"
    Write-Host "Log dir   : $logsDir"

    if ($OpenBrowserValue) {
        Start-Process "http://127.0.0.1:$Port/login"
    }
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   NiceCount Local Run" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

Write-Step "Checking installation at $TargetDir"

if (-not (Test-Path (Join-Path $TargetDir "pyproject.toml"))) {
    Throw-Friendly "NiceCount was not found at $TargetDir. Run the update/install script first."
}

$venvPython = Join-Path $TargetDir ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Throw-Friendly "Virtual environment not found. Run the update/install script first to set up NiceCount."
}

$envPath = Join-Path $TargetDir ".env"
if (-not (Test-Path $envPath)) {
    Throw-Friendly ".env file not found at $TargetDir. Run the update/install script first to configure NiceCount."
}

Stop-NiceCountServer -RepoDir $TargetDir -Port $AppPort
Start-NiceCountServer -RepoDir $TargetDir -PythonPath $venvPython -Port $AppPort -OpenBrowserValue:$OpenBrowser
