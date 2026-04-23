param(
    [string]$RepoUrl = "https://github.com/gianovembrian/nicecount.git",
    [string]$Branch = "main",
    [string]$TargetDir = "$env:USERPROFILE\NiceCount",
    [int]$AppPort = 8000,
    [string]$PgHost = "localhost",
    [int]$PgPort = 5432,
    [string]$PgUser = "postgres",
    [string]$PgPassword = "postgres",
    [string]$DatabaseName = "vehicle_count",
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

function Test-CommandAvailable {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Assert-CommandAvailable {
    param(
        [string]$Name,
        [string]$Hint
    )
    if (-not (Test-CommandAvailable -Name $Name)) {
        Throw-Friendly "$Name was not found in PATH. $Hint"
    }
}

function Invoke-External {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory = ""
    )

    if ($WorkingDirectory) {
        Push-Location $WorkingDirectory
    }

    try {
        & $FilePath @Arguments
        if ($LASTEXITCODE -ne 0) {
            Throw-Friendly "Command failed: $FilePath $($Arguments -join ' ')"
        }
    }
    finally {
        if ($WorkingDirectory) {
            Pop-Location
        }
    }
}

function Resolve-CurrentBranch {
    param([string]$RepoDir)

    $branchName = (& git -C $RepoDir rev-parse --abbrev-ref HEAD) | Select-Object -First 1
    if ($LASTEXITCODE -ne 0) {
        Throw-Friendly "Failed to resolve the current git branch in $RepoDir"
    }

    $branchName = "$branchName".Trim()
    if ([string]::IsNullOrWhiteSpace($branchName) -or $branchName -eq "HEAD") {
        return "main"
    }

    return $branchName
}

function Force-SyncRepo {
    param(
        [string]$RepoDir,
        [string]$RepoUrlValue,
        [string]$BranchValue
    )

    Write-Step "Force syncing local repo to GitHub"
    Invoke-External -FilePath "git" -Arguments @("-C", $RepoDir, "remote", "set-url", "origin", $RepoUrlValue)

    $targetBranch = $BranchValue
    if ([string]::IsNullOrWhiteSpace($targetBranch)) {
        $targetBranch = Resolve-CurrentBranch -RepoDir $RepoDir
    }

    Invoke-External -FilePath "git" -Arguments @("-C", $RepoDir, "fetch", "origin", $targetBranch, "--prune")
    Invoke-External -FilePath "git" -Arguments @("-C", $RepoDir, "checkout", "-B", $targetBranch, "origin/$targetBranch")
    Invoke-External -FilePath "git" -Arguments @("-C", $RepoDir, "reset", "--hard", "origin/$targetBranch")
    Invoke-External -FilePath "git" -Arguments @("-C", $RepoDir, "clean", "-fd")
}

function Resolve-PythonCommand {
    $pyCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCommand) {
        foreach ($versionFlag in @("-3.11", "-3.10", "-3.9", "-3")) {
            & $pyCommand.Source $versionFlag -c "import sys" *> $null
            if ($LASTEXITCODE -eq 0) {
                return @{
                    FilePath = $pyCommand.Source
                    PrefixArgs = @($versionFlag)
                }
            }
        }
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        return @{
            FilePath = $pythonCommand.Source
            PrefixArgs = @()
        }
    }

    Throw-Friendly "Python 3.9+ was not found. Run bootstrap_full_windows.ps1 first."
}

function Update-EnvLine {
    param(
        [string[]]$Lines,
        [string]$Key,
        [string]$Value
    )

    $updated = @()
    $matched = $false
    foreach ($line in $Lines) {
        if ($line -match ("^" + [regex]::Escape($Key) + "=")) {
            $updated += "$Key=$Value"
            $matched = $true
        }
        else {
            $updated += $line
        }
    }

    if (-not $matched) {
        $updated += "$Key=$Value"
    }

    return ,$updated
}

function Build-DatabaseUrl {
    param(
        [string]$DbHost,
        [int]$Port,
        [string]$User,
        [string]$Password,
        [string]$Name
    )

    if ($Password) {
        $encodedPassword = [System.Uri]::EscapeDataString($Password)
        return "postgresql+psycopg://${User}:${encodedPassword}@${DbHost}:${Port}/${Name}"
    }

    return "postgresql+psycopg://${User}@${DbHost}:${Port}/${Name}"
}

function Ensure-Repo {
    param(
        [string]$RepoUrlValue,
        [string]$TargetDirValue,
        [string]$BranchValue,
        [switch]$UseCurrentDirectoryValue
    )

    if ($UseCurrentDirectoryValue) {
        $repoRoot = (Resolve-Path ".").Path
        if (-not (Test-Path (Join-Path $repoRoot "pyproject.toml"))) {
            Throw-Friendly "Current directory is not a NiceCount repo root."
        }
        return $repoRoot
    }

    Assert-CommandAvailable -Name "git" -Hint "Run bootstrap_full_windows.ps1 first so Git is installed."

    if (Test-Path $TargetDirValue) {
        if (-not (Test-Path (Join-Path $TargetDirValue "pyproject.toml"))) {
            Throw-Friendly "TargetDir exists but is not a NiceCount repo: $TargetDirValue"
        }

        Write-Step "Updating existing repo"
        Force-SyncRepo -RepoDir $TargetDirValue -RepoUrlValue $RepoUrlValue -BranchValue $BranchValue
    }
    else {
        Write-Step "Cloning repo"
        $cloneArgs = @("clone")
        if ($BranchValue) {
            $cloneArgs += @("--branch", $BranchValue, "--single-branch")
        }
        $cloneArgs += @($RepoUrlValue, $TargetDirValue)
        Invoke-External -FilePath "git" -Arguments $cloneArgs
    }

    return (Resolve-Path $TargetDirValue).Path
}

function Ensure-EnvFileIfMissing {
    param(
        [string]$RepoDir,
        [string]$DatabaseUrl,
        [int]$Port
    )

    $envExamplePath = Join-Path $RepoDir ".env.example"
    $envPath = Join-Path $RepoDir ".env"
    if (Test-Path $envPath) {
        return
    }
    if (-not (Test-Path $envExamplePath)) {
        Throw-Friendly ".env.example was not found in repo."
    }

    Write-Step "Creating .env"
    $lines = Get-Content $envExamplePath
    $lines = Update-EnvLine -Lines $lines -Key "APP_PORT" -Value "$Port"
    $lines = Update-EnvLine -Lines $lines -Key "APP_BASE_URL" -Value "http://localhost:$Port"
    $lines = Update-EnvLine -Lines $lines -Key "DATABASE_URL" -Value $DatabaseUrl
    $lines = Update-EnvLine -Lines $lines -Key "AUTO_CREATE_TABLES" -Value "false"
    Set-Content -Path $envPath -Value $lines -Encoding UTF8
}

function Ensure-PostgresDatabase {
    param(
        [string]$RepoDir,
        [string]$DbHost,
        [int]$Port,
        [string]$User,
        [string]$Password,
        [string]$Name
    )

    if ($Name -notmatch "^[A-Za-z0-9_]+$") {
        Throw-Friendly "DatabaseName may only contain letters, numbers, and underscore."
    }

    Assert-CommandAvailable -Name "psql" -Hint "Run bootstrap_full_windows.ps1 first so PostgreSQL tools are installed."

    $previousPassword = $env:PGPASSWORD
    $env:PGPASSWORD = $Password

    try {
        Write-Step "Checking PostgreSQL connection"
        Invoke-External -FilePath "psql" -Arguments @("-v", "ON_ERROR_STOP=1", "-h", $DbHost, "-p", "$Port", "-U", $User, "-d", "postgres", "-tAc", "SELECT 1;")

        $databaseExists = & psql -h $DbHost -p "$Port" -U $User -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$Name';"
        if ($LASTEXITCODE -ne 0) {
            Throw-Friendly "Failed to check PostgreSQL database existence."
        }

        if (-not ($databaseExists -match "1")) {
            Write-Step "Creating database $Name"
            Invoke-External -FilePath "psql" -Arguments @("-v", "ON_ERROR_STOP=1", "-h", $DbHost, "-p", "$Port", "-U", $User, "-d", "postgres", "-c", "CREATE DATABASE $Name;")
        }

        Write-Step "Applying schema and migrations"
        foreach ($sqlFile in @(
            "sql/01_schema.sql",
            "sql/04_video_count_lines.sql",
            "sql/05_vehicle_event_count_lines.sql",
            "sql/06_detection_settings.sql",
            "sql/07_master_classes.sql",
            "sql/08_video_status_converting.sql",
            "sql/09_vehicle_classification_standard.sql",
            "sql/10_detection_pipeline_refactor.sql",
            "sql/11_detection_runtime_settings.sql"
        )) {
            $sqlPath = Join-Path $RepoDir $sqlFile
            if (Test-Path $sqlPath) {
                Invoke-External -FilePath "psql" -Arguments @("-v", "ON_ERROR_STOP=1", "-h", $DbHost, "-p", "$Port", "-U", $User, "-d", $Name, "-f", $sqlPath)
            }
        }
    }
    finally {
        $env:PGPASSWORD = $previousPassword
    }
}

function Ensure-VenvAndPackages {
    param(
        [string]$RepoDir,
        [hashtable]$PythonCommand
    )

    $venvDir = Join-Path $RepoDir ".venv"
    if (-not (Test-Path (Join-Path $venvDir "Scripts\python.exe"))) {
        Write-Step "Creating virtual environment"
        $venvArgs = @()
        $venvArgs += $PythonCommand.PrefixArgs
        $venvArgs += @("-m", "venv", ".venv")
        Invoke-External -FilePath $PythonCommand.FilePath -Arguments $venvArgs -WorkingDirectory $RepoDir
    }

    $venvPython = Join-Path $venvDir "Scripts\python.exe"
    Write-Step "Installing Python packages"
    Invoke-External -FilePath $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel") -WorkingDirectory $RepoDir
    Invoke-External -FilePath $venvPython -Arguments @("-m", "pip", "install", "-e", ".") -WorkingDirectory $RepoDir
    return $venvPython
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
        [string]$RepoDir,
        [string]$PythonPath,
        [int]$Port,
        [switch]$UseReloadValue,
        [switch]$OpenBrowserValue
    )

    Write-Step "Starting NiceCount server"
    $logsDir = Join-Path $RepoDir "logs"
    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null

    $stdoutLog = Join-Path $logsDir "nicecount.out.log"
    $stderrLog = Join-Path $logsDir "nicecount.err.log"
    $pidFile = Join-Path $RepoDir ".nicecount.pid"

    $serverArgs = @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$Port")
    if ($UseReloadValue) {
        $serverArgs += "--reload"
    }

    $process = Start-Process -FilePath $PythonPath -ArgumentList $serverArgs -WorkingDirectory $RepoDir -PassThru -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog
    Set-Content -Path $pidFile -Value $process.Id -Encoding ASCII

    if (-not (Wait-ForHealth -Port $Port)) {
        Throw-Friendly "NiceCount server did not become healthy. Check $stdoutLog and $stderrLog"
    }

    Write-Host ""
    Write-Host "NiceCount update complete." -ForegroundColor Green
    Write-Host "Login URL : http://127.0.0.1:$Port/login"
    Write-Host "PID file  : $pidFile"
    Write-Host "Stdout log: $stdoutLog"
    Write-Host "Stderr log: $stderrLog"

    if ($OpenBrowserValue) {
        Start-Process "http://127.0.0.1:$Port/login"
    }
}

Write-Step "Resolving repo"
$repoDir = Ensure-Repo -RepoUrlValue $RepoUrl -TargetDirValue $TargetDir -BranchValue $Branch -UseCurrentDirectoryValue:$UseCurrentDirectory

Write-Step "Resolving Python"
$pythonCommand = Resolve-PythonCommand

$databaseUrl = Build-DatabaseUrl -DbHost $PgHost -Port $PgPort -User $PgUser -Password $PgPassword -Name $DatabaseName
Ensure-EnvFileIfMissing -RepoDir $repoDir -DatabaseUrl $databaseUrl -Port $AppPort

Stop-NiceCountServer -RepoDir $repoDir -Port $AppPort
$venvPython = Ensure-VenvAndPackages -RepoDir $repoDir -PythonCommand $pythonCommand
Ensure-PostgresDatabase -RepoDir $repoDir -DbHost $PgHost -Port $PgPort -User $PgUser -Password $PgPassword -Name $DatabaseName
Start-NiceCountServer -RepoDir $repoDir -PythonPath $venvPython -Port $AppPort -UseReloadValue:$UseReload -OpenBrowserValue:$OpenBrowser
