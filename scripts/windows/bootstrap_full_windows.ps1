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
    [switch]$SkipGitInstall
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

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Ensure-Elevated {
    if (Test-IsAdministrator) {
        return
    }

    Write-Step "Requesting administrator privileges"
    $argumentList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath)
    foreach ($parameter in $PSBoundParameters.GetEnumerator() | Sort-Object Key) {
        if ($parameter.Value -is [switch]) {
            if ($parameter.Value.IsPresent) {
                $argumentList += "-$($parameter.Key)"
            }
        }
        elseif ($null -ne $parameter.Value -and "$($parameter.Value)" -ne "") {
            $argumentList += @("-$($parameter.Key)", "$($parameter.Value)")
        }
    }

    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $argumentList | Out-Null
    exit 0
}

function Test-CommandAvailable {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Assert-WingetAvailable {
    if (-not (Test-CommandAvailable -Name "winget")) {
        Throw-Friendly "winget was not found. This one-shot installer requires Windows Package Manager (App Installer) on Windows 10/11."
    }
}

function Refresh-Path {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $combined = @()
    if ($machinePath) {
        $combined += $machinePath
    }
    if ($userPath) {
        $combined += $userPath
    }
    $env:Path = ($combined -join ";")
}

function Prepend-Path {
    param([string]$Directory)
    if (-not $Directory) {
        return
    }
    if (-not (Test-Path $Directory)) {
        return
    }

    $currentEntries = @($env:Path -split ";" | Where-Object { $_ })
    if ($currentEntries -contains $Directory) {
        return
    }
    $env:Path = "$Directory;$env:Path"
}

function Ensure-GitPath {
    if (Test-CommandAvailable -Name "git") {
        return
    }

    $gitCandidates = @(
        "C:\Program Files\Git\cmd",
        "C:\Program Files\Git\bin"
    )
    foreach ($candidate in $gitCandidates) {
        if (Test-Path (Join-Path $candidate "git.exe")) {
            Prepend-Path -Directory $candidate
            return
        }
    }
}

function Ensure-PythonPath {
    if ((Test-CommandAvailable -Name "py") -or (Test-CommandAvailable -Name "python")) {
        return
    }

    $pythonCandidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python311",
        "$env:LOCALAPPDATA\Programs\Python\Python310",
        "$env:ProgramFiles\Python311",
        "$env:ProgramFiles\Python310"
    )
    foreach ($candidate in $pythonCandidates) {
        if (Test-Path (Join-Path $candidate "python.exe")) {
            Prepend-Path -Directory $candidate
            return
        }
    }
}

function Ensure-PostgresPath {
    if (Test-CommandAvailable -Name "psql") {
        return
    }

    $programFiles = [Environment]::GetFolderPath("ProgramFiles")
    $searchRoots = @(
        (Join-Path $programFiles "PostgreSQL")
    ) | Where-Object { Test-Path $_ }

    foreach ($root in $searchRoots) {
        $candidate = Get-ChildItem -Path $root -Filter "psql.exe" -Recurse -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($candidate) {
            Prepend-Path -Directory $candidate.Directory.FullName
            return
        }
    }
}

function Invoke-WingetInstall {
    param(
        [string]$PackageId,
        [string]$DisplayName,
        [string[]]$ExtraArguments = @()
    )

    Write-Step "Installing $DisplayName"
    $arguments = @(
        "install",
        "--id", $PackageId,
        "--exact",
        "--source", "winget",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--silent"
    ) + $ExtraArguments

    & winget @arguments
    if ($LASTEXITCODE -ne 0) {
        Throw-Friendly "Failed to install $DisplayName with winget."
    }
}

function Ensure-Git {
    if (Test-CommandAvailable -Name "git") {
        return
    }
    if ($SkipGitInstall) {
        Throw-Friendly "Git is not installed and -SkipGitInstall was used."
    }

    Invoke-WingetInstall -PackageId "Git.Git" -DisplayName "Git" -ExtraArguments @("--scope", "machine")
    Refresh-Path
    Ensure-GitPath

    if (-not (Test-CommandAvailable -Name "git")) {
        Throw-Friendly "Git installation finished, but git.exe is still not available in PATH."
    }
}

function Ensure-Python {
    if ((Test-CommandAvailable -Name "py") -or (Test-CommandAvailable -Name "python")) {
        return
    }

    Invoke-WingetInstall -PackageId "Python.Python.3.11" -DisplayName "Python 3.11" -ExtraArguments @("--scope", "machine")
    Refresh-Path
    Ensure-PythonPath

    if (-not ((Test-CommandAvailable -Name "py") -or (Test-CommandAvailable -Name "python"))) {
        Throw-Friendly "Python installation finished, but python.exe is still not available in PATH."
    }
}

function Ensure-PostgreSQL {
    if (Test-CommandAvailable -Name "psql") {
        return
    }

    if ([string]::IsNullOrWhiteSpace($PgPassword)) {
        Throw-Friendly "PgPassword may not be empty for automated PostgreSQL installation."
    }

    $overrideArgs = "--mode unattended --unattendedmodeui minimal --superaccount `"$PgUser`" --superpassword `"$PgPassword`" --servicepassword `"$PgPassword`" --serverport $PgPort"
    Invoke-WingetInstall -PackageId "PostgreSQL.PostgreSQL" -DisplayName "PostgreSQL" -ExtraArguments @("--scope", "machine", "--override", $overrideArgs)
    Refresh-Path
    Ensure-PostgresPath

    if (-not (Test-CommandAvailable -Name "psql")) {
        Throw-Friendly "PostgreSQL installation finished, but psql.exe is still not available in PATH."
    }
}

function Get-InstallScriptUrl {
    param(
        [string]$RepositoryUrl,
        [string]$BranchName
    )

    if ($RepositoryUrl -match "github\.com[:/](?<owner>[^/]+)/(?<repo>[^/.]+?)(?:\.git)?/?$") {
        $owner = $Matches["owner"]
        $repo = $Matches["repo"]
        return "https://raw.githubusercontent.com/$owner/$repo/$BranchName/scripts/windows/install_windows.ps1"
    }

    Throw-Friendly "RepoUrl must be a GitHub repository URL so the installer script can be downloaded automatically."
}

function Invoke-NiceCountInstaller {
    $installScriptUrl = Get-InstallScriptUrl -RepositoryUrl $RepoUrl -BranchName $Branch
    $tempInstallScript = Join-Path $env:TEMP "nicecount_install_windows.ps1"

    Write-Step "Downloading NiceCount installer"
    Invoke-WebRequest -Uri $installScriptUrl -OutFile $tempInstallScript -UseBasicParsing

    Write-Step "Running NiceCount installer"
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $tempInstallScript,
        "-RepoUrl", $RepoUrl,
        "-TargetDir", $TargetDir,
        "-Branch", $Branch,
        "-AppPort", "$AppPort",
        "-PgHost", $PgHost,
        "-PgPort", "$PgPort",
        "-PgUser", $PgUser,
        "-PgPassword", $PgPassword,
        "-DatabaseName", $DatabaseName
    )
    if ($OpenBrowser) {
        $arguments += "-OpenBrowser"
    }
    if ($UseReload) {
        $arguments += "-UseReload"
    }

    & powershell.exe @arguments
    if ($LASTEXITCODE -ne 0) {
        Throw-Friendly "NiceCount installer failed."
    }
}

Ensure-Elevated
Assert-WingetAvailable
Refresh-Path

Write-Step "Preparing prerequisites"
Ensure-Git
Ensure-Python
Ensure-PostgreSQL

Invoke-NiceCountInstaller

Write-Host ""
Write-Host "NiceCount bootstrap finished." -ForegroundColor Green
