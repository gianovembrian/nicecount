param(
    [string]$RepoDir = "$env:USERPROFILE\NiceCount",
    [int]$AppPort = 8000,
    [switch]$OpenBrowser,
    [switch]$UseReload,
    [switch]$UseCurrentDirectory
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

function Resolve-RepoDir {
    param(
        [string]$RepoDirValue,
        [switch]$UseCurrentDirectoryValue
    )

    if ($UseCurrentDirectoryValue) {
        $repoRoot = (Resolve-Path ".").Path
        if (-not (Test-Path (Join-Path $repoRoot "pyproject.toml"))) {
            Throw-Friendly "Current directory is not a NiceCount repo root."
        }
        return $repoRoot
    }

    if (-not (Test-Path (Join-Path $RepoDirValue "pyproject.toml"))) {
        Throw-Friendly "NiceCount repo was not found at $RepoDirValue"
    }

    return (Resolve-Path $RepoDirValue).Path
}

function Ensure-EnvFileIfMissing {
    param(
        [string]$RepoRoot,
        [int]$Port
    )

    $envPath = Join-Path $RepoRoot ".env"
    if (Test-Path $envPath) {
        return
    }

    $envExamplePath = Join-Path $RepoRoot ".env.example"
    if (-not (Test-Path $envExamplePath)) {
        Throw-Friendly ".env.example was not found in repo."
    }

    Write-Step "Creating .env from .env.example"
    $lines = Get-Content $envExamplePath
    $updated = foreach ($line in $lines) {
        if ($line -match "^APP_PORT=") {
            "APP_PORT=$Port"
        }
        elseif ($line -match "^APP_BASE_URL=") {
            "APP_BASE_URL=http://localhost:$Port"
        }
        else {
            $line
        }
    }
    Set-Content -Path $envPath -Value $updated -Encoding UTF8
}

function Stop-NiceCountServer {
    param(
        [string]$RepoRoot,
        [int]$Port
    )

    $pidFile = Join-Path $RepoRoot ".nicecount.pid"
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
    for ($index = 0; $index -lt 90; $index++) {
        Start-Sleep -Seconds 1
        try {
            $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200 -and $response.Content -match '"status"\s*:\s*"ok"') {
                return $true
            }
        }
        catch {
        }
    }

    return $false
}

function Start-NiceCountServer {
    param(
        [string]$RepoRoot,
        [string]$PythonPath,
        [int]$Port,
        [switch]$UseReloadValue,
        [switch]$OpenBrowserValue
    )

    Write-Step "Starting NiceCount server"
    $logsDir = Join-Path $RepoRoot "logs"
    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null

    $stdoutLog = Join-Path $logsDir "nicecount.out.log"
    $stderrLog = Join-Path $logsDir "nicecount.err.log"
    $pidFile = Join-Path $RepoRoot ".nicecount.pid"

    $serverArgs = @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$Port")
    if ($UseReloadValue) {
        $serverArgs += "--reload"
    }

    $process = Start-Process -FilePath $PythonPath -ArgumentList $serverArgs -WorkingDirectory $RepoRoot -PassThru -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog
    Set-Content -Path $pidFile -Value $process.Id -Encoding ASCII

    if (-not (Wait-ForHealth -Port $Port)) {
        Throw-Friendly "NiceCount server did not become healthy. Check $stdoutLog and $stderrLog"
    }

    Write-Host ""
    Write-Host "NiceCount server is running." -ForegroundColor Green
    Write-Host "Login URL : http://127.0.0.1:$Port/login"
    Write-Host "PID file  : $pidFile"
    Write-Host "Stdout log: $stdoutLog"
    Write-Host "Stderr log: $stderrLog"

    if ($OpenBrowserValue) {
        Start-Process "http://127.0.0.1:$Port/login"
    }
}

$repoRoot = Resolve-RepoDir -RepoDirValue $RepoDir -UseCurrentDirectoryValue:$UseCurrentDirectory
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Throw-Friendly "Virtual environment was not found at $venvPython. Run install_windows.ps1 first."
}

Ensure-EnvFileIfMissing -RepoRoot $repoRoot -Port $AppPort
Stop-NiceCountServer -RepoRoot $repoRoot -Port $AppPort
Start-NiceCountServer -RepoRoot $repoRoot -PythonPath $venvPython -Port $AppPort -UseReloadValue:$UseReload -OpenBrowserValue:$OpenBrowser
