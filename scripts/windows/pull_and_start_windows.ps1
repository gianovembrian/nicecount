param(
    [string]$RepoUrl     = "https://github.com/gianovembrian/nicecount.git",
    [string]$Branch      = "main",
    [string]$TargetDir   = "$env:USERPROFILE\NiceCount",
    [int]$AppPort        = 8000,
    [string]$PgHost      = "localhost",
    [int]$PgPort         = 5432,
    [string]$PgUser      = "postgres",
    [string]$PgPassword  = "postgres",
    [string]$DatabaseName = "vehicle_count",
    [switch]$OpenBrowser,
    [switch]$UseReload,
    [switch]$UseCurrentDirectory
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    param([string]$Name, [string]$Hint)
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
    if ($WorkingDirectory) { Push-Location $WorkingDirectory }
    try {
        $stdoutPath = [System.IO.Path]::GetTempFileName()
        $stderrPath = [System.IO.Path]::GetTempFileName()
        & $FilePath @Arguments > $stdoutPath 2> $stderrPath
        $exitCode = $LASTEXITCODE
        foreach ($line in (Get-Content $stdoutPath -ErrorAction SilentlyContinue)) {
            Write-Host $line
        }
        foreach ($line in (Get-Content $stderrPath -ErrorAction SilentlyContinue)) {
            Write-Host $line
        }
        if ($exitCode -ne 0) {
            Throw-Friendly "Command failed: $FilePath $($Arguments -join ' ')"
        }
        Remove-Item $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
    }
    finally {
        if ($stdoutPath -or $stderrPath) {
            Remove-Item $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
        }
        if ($WorkingDirectory) { Pop-Location }
    }
}

function Resolve-PythonCommand {
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        foreach ($flag in @("-3.11", "-3.10", "-3.9", "-3")) {
            & $pyCmd.Source $flag -c "import sys" *> $null
            if ($LASTEXITCODE -eq 0) {
                return @{ FilePath = $pyCmd.Source; PrefixArgs = @($flag) }
            }
        }
    }
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        return @{ FilePath = $pythonCmd.Source; PrefixArgs = @() }
    }
    Throw-Friendly "Python 3.9+ was not found. Run bootstrap_full_windows.ps1 first."
}

function Build-DatabaseUrl {
    param([string]$DbHost, [int]$Port, [string]$User, [string]$Password, [string]$Name)
    if ($Password) {
        $enc = [System.Uri]::EscapeDataString($Password)
        return "postgresql+psycopg://${User}:${enc}@${DbHost}:${Port}/${Name}"
    }
    return "postgresql+psycopg://${User}@${DbHost}:${Port}/${Name}"
}

function Update-EnvLine {
    param([string[]]$Lines, [string]$Key, [string]$Value)
    $out     = @()
    $matched = $false
    foreach ($line in $Lines) {
        if ($line -match ("^" + [regex]::Escape($Key) + "=")) {
            $out += "$Key=$Value"; $matched = $true
        } else { $out += $line }
    }
    if (-not $matched) { $out += "$Key=$Value" }
    return ,$out
}

# ---------------------------------------------------------------------------
# Step 1 - Resolve repo directory
# ---------------------------------------------------------------------------

function Resolve-RepoDir {
    param(
        [string]$RepoUrlValue,
        [string]$TargetDirValue,
        [string]$BranchValue,
        [switch]$UseCurrentDirectoryValue
    )

    if ($UseCurrentDirectoryValue) {
        $root = (Resolve-Path ".").Path
        if (-not (Test-Path (Join-Path $root "pyproject.toml"))) {
            Throw-Friendly "Current directory is not a NiceCount repo root."
        }
        return $root
    }

    Assert-CommandAvailable -Name "git" -Hint "Run bootstrap_full_windows.ps1 first so Git is installed."

    if (-not (Test-Path $TargetDirValue)) {
        Write-Step "Repo not found locally - cloning"
        $cloneArgs = @("clone")
        if ($BranchValue) { $cloneArgs += @("--branch", $BranchValue, "--single-branch") }
        $cloneArgs += @($RepoUrlValue, $TargetDirValue)
        Invoke-External -FilePath "git" -Arguments $cloneArgs
        return (Resolve-Path $TargetDirValue).Path
    }

    if (-not (Test-Path (Join-Path $TargetDirValue "pyproject.toml"))) {
        Throw-Friendly "TargetDir exists but is not a NiceCount repo: $TargetDirValue"
    }

    return (Resolve-Path $TargetDirValue).Path
}

function Resolve-TargetBranch {
    param([string]$RepoDir, [string]$BranchValue)
    if (-not [string]::IsNullOrWhiteSpace($BranchValue)) { return $BranchValue }
    $branch = (& git -C $RepoDir rev-parse --abbrev-ref HEAD | Select-Object -First 1).Trim()
    if ([string]::IsNullOrWhiteSpace($branch) -or $branch -eq "HEAD") { return "main" }
    return $branch
}

function Test-LocalGitBranch {
    param([string]$RepoDir, [string]$BranchName)
    & git -C $RepoDir show-ref --verify --quiet "refs/heads/$BranchName" *> $null
    return ($LASTEXITCODE -eq 0)
}

function Checkout-TargetBranch {
    param([string]$RepoDir, [string]$BranchName)

    if (Test-LocalGitBranch -RepoDir $RepoDir -BranchName $BranchName) {
        Invoke-External -FilePath "git" -Arguments @("-C", $RepoDir, "checkout", $BranchName)
        return
    }

    Invoke-External -FilePath "git" -Arguments @("-C", $RepoDir, "checkout", "-b", $BranchName, "--track", "origin/$BranchName")
}

# ---------------------------------------------------------------------------
# Step 2 - git pull (standard, non-destructive)
# ---------------------------------------------------------------------------

function Pull-Repo {
    param([string]$RepoDir, [string]$RepoUrlValue, [string]$BranchValue)

    Write-Step "Pulling latest code from GitHub"
    Invoke-External -FilePath "git" -Arguments @("-C", $RepoDir, "remote", "set-url", "origin", $RepoUrlValue)

    $targetBranch = Resolve-TargetBranch -RepoDir $RepoDir -BranchValue $BranchValue

    Invoke-External -FilePath "git" -Arguments @("-C", $RepoDir, "fetch", "--prune", "origin", $targetBranch)
    Checkout-TargetBranch -RepoDir $RepoDir -BranchName $targetBranch
    Invoke-External -FilePath "git" -Arguments @("-C", $RepoDir, "merge", "--ff-only", "origin/$targetBranch")

    $commitHash = (& git -C $RepoDir rev-parse --short HEAD) | Select-Object -First 1
    Write-Host "   Branch : $targetBranch" -ForegroundColor DarkGray
    Write-Host "   Commit : $commitHash"   -ForegroundColor DarkGray
}

# ---------------------------------------------------------------------------
# Step 3 - .env (create only if missing)
# ---------------------------------------------------------------------------

function Ensure-EnvFile {
    param([string]$RepoDir, [string]$DatabaseUrl, [int]$Port)

    $envPath = Join-Path $RepoDir ".env"
    if (Test-Path $envPath) { return }

    $envExamplePath = Join-Path $RepoDir ".env.example"
    if (-not (Test-Path $envExamplePath)) {
        Throw-Friendly ".env.example was not found in repo."
    }

    Write-Step "Creating .env from .env.example"
    $lines = Get-Content $envExamplePath
    $lines = Update-EnvLine -Lines $lines -Key "APP_PORT"     -Value "$Port"
    $lines = Update-EnvLine -Lines $lines -Key "APP_BASE_URL" -Value "http://localhost:$Port"
    $lines = Update-EnvLine -Lines $lines -Key "DATABASE_URL" -Value $DatabaseUrl
    $lines = Update-EnvLine -Lines $lines -Key "AUTO_CREATE_TABLES" -Value "false"
    Set-Content -Path $envPath -Value $lines -Encoding UTF8
}

# ---------------------------------------------------------------------------
# Step 4 - Python venv + packages
# ---------------------------------------------------------------------------

function Ensure-VenvAndPackages {
    param([string]$RepoDir, [hashtable]$PythonCommand)

    $venvDir = Join-Path $RepoDir ".venv"

    if (-not (Test-Path (Join-Path $venvDir "Scripts\python.exe"))) {
        Write-Step "Creating virtual environment"
        $args = $PythonCommand.PrefixArgs + @("-m", "venv", ".venv")
        Invoke-External -FilePath $PythonCommand.FilePath -Arguments $args -WorkingDirectory $RepoDir
    }

    $venvPython = Join-Path $venvDir "Scripts\python.exe"

    # Skip pip install when pyproject.toml hasn't changed since last run.
    $pkgSpec    = Join-Path $RepoDir "pyproject.toml"
    $hashFile   = Join-Path $RepoDir ".nicecount.pkg.hash"
    $currentHash = (Get-FileHash $pkgSpec -Algorithm SHA256 -ErrorAction SilentlyContinue).Hash
    $cachedHash  = (Get-Content $hashFile -ErrorAction SilentlyContinue | Select-Object -First 1)

    if ($currentHash -and $currentHash -eq $cachedHash) {
        Write-Step "Python packages up to date (pyproject.toml unchanged)"
    }
    else {
        Write-Step "Installing / updating Python packages"
        Invoke-External -FilePath $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel") -WorkingDirectory $RepoDir
        Invoke-External -FilePath $venvPython -Arguments @("-m", "pip", "install", "-e", ".") -WorkingDirectory $RepoDir
        if ($currentHash) { Set-Content -Path $hashFile -Value $currentHash -Encoding ASCII }
    }

    return $venvPython
}

# ---------------------------------------------------------------------------
# Step 5 - PostgreSQL: create DB if missing + apply migrations
# ---------------------------------------------------------------------------

function Ensure-Database {
    param(
        [string]$RepoDir,
        [string]$DbHost, [int]$Port,
        [string]$User, [string]$Password,
        [string]$Name
    )

    if ($Name -notmatch "^[A-Za-z0-9_]+$") {
        Throw-Friendly "DatabaseName may only contain letters, numbers, and underscore."
    }

    Assert-CommandAvailable -Name "psql" -Hint "Run bootstrap_full_windows.ps1 first so PostgreSQL tools are installed."

    $prev = $env:PGPASSWORD
    $env:PGPASSWORD = $Password
    try {
        Write-Step "Checking PostgreSQL connection"
        Invoke-External -FilePath "psql" -Arguments @(
            "-v", "ON_ERROR_STOP=1", "-h", $DbHost, "-p", "$Port",
            "-U", $User, "-d", "postgres", "-tAc", "SELECT 1;"
        )

        $exists = & psql -h $DbHost -p "$Port" -U $User -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$Name';"
        if ($LASTEXITCODE -ne 0) { Throw-Friendly "Failed to query pg_database." }

        if (-not ($exists -match "1")) {
            Write-Step "Creating database $Name"
            Invoke-External -FilePath "psql" -Arguments @(
                "-v", "ON_ERROR_STOP=1", "-h", $DbHost, "-p", "$Port",
                "-U", $User, "-d", "postgres", "-c", "CREATE DATABASE $Name;"
            )
        }

        Write-Step "Applying schema migrations"
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
                Write-Host "   Applying $sqlFile" -ForegroundColor DarkGray
                Invoke-External -FilePath "psql" -Arguments @(
                    "-v", "ON_ERROR_STOP=1", "-h", $DbHost, "-p", "$Port",
                    "-U", $User, "-d", $Name, "-f", $sqlPath
                )
            }
        }
    }
    finally {
        $env:PGPASSWORD = $prev
    }
}

# ---------------------------------------------------------------------------
# Step 6 - Stop existing server
# ---------------------------------------------------------------------------

function Stop-NiceCountServer {
    param([string]$RepoDir, [int]$Port)

    $pidFile = Join-Path $RepoDir ".nicecount.pid"

    if (Test-Path $pidFile) {
        $pidValue = (Get-Content $pidFile | Select-Object -First 1).Trim()
        if ($pidValue -match "^\d+$") {
            $proc = Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue
            if ($proc) {
                Write-Step "Stopping existing NiceCount server (PID $pidValue)"
                Stop-Process -Id ([int]$pidValue) -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 2
                Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
                return
            }
        }
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }

    try {
        $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop | Select-Object -First 1
        if ($listener -and $listener.OwningProcess) {
            Write-Step "Stopping process on port $Port (PID $($listener.OwningProcess))"
            Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        }
    }
    catch {}
}

# ---------------------------------------------------------------------------
# Step 7 - Start server
# ---------------------------------------------------------------------------

function Wait-ForHealth {
    param([int]$Port)
    $url = "http://127.0.0.1:$Port/health"
    for ($i = 0; $i -lt 90; $i++) {
        Start-Sleep -Seconds 1
        try {
            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -eq 200 -and $r.Content -match '"status"\s*:\s*"ok"') { return $true }
        }
        catch {}
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
    $pidFile   = Join-Path $RepoDir ".nicecount.pid"

    $serverArgs = @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$Port")
    if ($UseReloadValue) { $serverArgs += "--reload" }

    $proc = Start-Process -FilePath $PythonPath -ArgumentList $serverArgs `
        -WorkingDirectory $RepoDir -PassThru `
        -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog
    Set-Content -Path $pidFile -Value $proc.Id -Encoding ASCII

    if (-not (Wait-ForHealth -Port $Port)) {
        Throw-Friendly "Server did not become healthy within 90 s. Check:`n  $stdoutLog`n  $stderrLog"
    }

    Write-Host ""
    Write-Host "NiceCount is running." -ForegroundColor Green
    Write-Host "Login URL : http://127.0.0.1:$Port/login"
    Write-Host "PID file  : $pidFile"
    Write-Host "Stdout log: $stdoutLog"
    Write-Host "Stderr log: $stderrLog"

    if ($OpenBrowserValue) { Start-Process "http://127.0.0.1:$Port/login" }
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

$repoDir = Resolve-RepoDir `
    -RepoUrlValue $RepoUrl -TargetDirValue $TargetDir `
    -BranchValue $Branch -UseCurrentDirectoryValue:$UseCurrentDirectory

Pull-Repo -RepoDir $repoDir -RepoUrlValue $RepoUrl -BranchValue $Branch

$pythonCommand = Resolve-PythonCommand
$dbUrl         = Build-DatabaseUrl -DbHost $PgHost -Port $PgPort -User $PgUser -Password $PgPassword -Name $DatabaseName

Ensure-EnvFile        -RepoDir $repoDir -DatabaseUrl $dbUrl -Port $AppPort
Stop-NiceCountServer  -RepoDir $repoDir -Port $AppPort
$venvPython = Ensure-VenvAndPackages -RepoDir $repoDir -PythonCommand $pythonCommand
Ensure-Database       -RepoDir $repoDir -DbHost $PgHost -Port $PgPort -User $PgUser -Password $PgPassword -Name $DatabaseName
Start-NiceCountServer -RepoDir $repoDir -PythonPath $venvPython -Port $AppPort -UseReloadValue:$UseReload -OpenBrowserValue:$OpenBrowser
