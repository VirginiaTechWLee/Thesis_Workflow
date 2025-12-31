# Pre-Flight Check Script
# Ensures environment is ready before running setup_thesis_workflows.ps1
# Root: C:\Users\waynelee\Documents

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "Pre-Flight Environment Check" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Ensure we're in Documents folder
$expectedPath = "C:\Users\waynelee\Documents"
$currentPath = Get-Location

if ($currentPath.Path -ne $expectedPath) {
    Write-Host "WARNING: Not in expected directory!" -ForegroundColor Red
    Write-Host "  Current:  $currentPath" -ForegroundColor Yellow
    Write-Host "  Expected: $expectedPath" -ForegroundColor Yellow
    Write-Host ""
    $response = Read-Host "Change to $expectedPath? (Y/N)"
    if ($response -eq "Y" -or $response -eq "y") {
        Set-Location $expectedPath
        Write-Host "Changed to: $expectedPath" -ForegroundColor Green
    } else {
        Write-Host "Exiting..." -ForegroundColor Red
        exit 1
    }
}
Write-Host "v Current directory: $expectedPath" -ForegroundColor Green
Write-Host ""

# Check if Git is initialized
Write-Host "Checking Git repository..." -ForegroundColor Yellow
if (-not (Test-Path ".git")) {
    Write-Host "WARNING: Not a Git repository!" -ForegroundColor Red
    Write-Host "  Run: git init" -ForegroundColor Yellow
    $response = Read-Host "Initialize Git repository? (Y/N)"
    if ($response -eq "Y" -or $response -eq "y") {
        git init
        Write-Host "v Git repository initialized" -ForegroundColor Green
    } else {
        Write-Host "Skipping Git initialization..." -ForegroundColor Yellow
    }
} else {
    Write-Host "v Git repository exists" -ForegroundColor Green
}
Write-Host ""

# Check Git remote
Write-Host "Checking Git remote..." -ForegroundColor Yellow
$remote = git remote -v 2>$null
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrEmpty($remote)) {
    Write-Host "WARNING: No Git remote configured!" -ForegroundColor Red
    Write-Host "  Expected remote: https://github.com/VirginiaTechWLee/Thesis_Workflow.git" -ForegroundColor Yellow
    $response = Read-Host "Add remote? (Y/N)"
    if ($response -eq "Y" -or $response -eq "y") {
        git remote add origin https://github.com/VirginiaTechWLee/Thesis_Workflow.git
        Write-Host "v Git remote added" -ForegroundColor Green
    }
} else {
    Write-Host "v Git remote configured:" -ForegroundColor Green
    Write-Host "  $remote" -ForegroundColor Gray
}
Write-Host ""

# Check PortableGit in PATH
Write-Host "Checking Git in PATH..." -ForegroundColor Yellow
if ($env:Path -notlike "*PortableGit*") {
    Write-Host "WARNING: PortableGit not in PATH for this session!" -ForegroundColor Yellow
    if (Test-Path "C:\Users\waynelee\Desktop\PortableGit\bin") {
        Write-Host "  Adding PortableGit to PATH..." -ForegroundColor Yellow
        $env:Path += ";C:\Users\waynelee\Desktop\PortableGit\bin"
        Write-Host "v PortableGit added to PATH (this session only)" -ForegroundColor Green
    } else {
        Write-Host "ERROR: PortableGit not found at expected location!" -ForegroundColor Red
    }
} else {
    Write-Host "v Git is in PATH" -ForegroundColor Green
}
Write-Host ""

# Create required directory structure
Write-Host "Creating required directories..." -ForegroundColor Yellow

$directories = @(
    ".github",
    ".github\workflows",
    "Scripts",
    "templates", 
    "baseline",
    "current_run",
    "heeds_projects",
    "heeds_results"
)

$createdCount = 0
$existsCount = 0

foreach ($dir in $directories) {
    if (-not (Test-Path $dir)) {
        try {
            New-Item -Path $dir -ItemType Directory -ErrorAction Stop | Out-Null
            Write-Host "  Created: $dir" -ForegroundColor Green
            $createdCount++
        } catch {
            Write-Host "  ERROR creating $dir : $_" -ForegroundColor Red
        }
    } else {
        Write-Host "  Exists: $dir" -ForegroundColor Gray
        $existsCount++
    }
}

Write-Host ""
Write-Host "Directory summary: $createdCount created, $existsCount already existed" -ForegroundColor Cyan
Write-Host ""

# Check for required source files
Write-Host "Checking for required source files..." -ForegroundColor Yellow

$requiredFiles = @{
    "Pch_TO_CSV2.py" = "Python script for feature extraction"
    "Fixed_base_beam.dat" = "Nastran model template"
    "Bush.blk" = "PBUSH property definitions"
    "Square_Beam_scenario_short_rev.heeds" = "HEEDS project file"
}

$missingFiles = @()
foreach ($file in $requiredFiles.Keys) {
    if (Test-Path $file) {
        Write-Host "  v Found: $file" -ForegroundColor Green
    } elseif (Test-Path "Scripts\$file") {
        Write-Host "  v Found: Scripts\$file" -ForegroundColor Green
    } elseif (Test-Path "templates\$file") {
        Write-Host "  v Found: templates\$file" -ForegroundColor Green
    } else {
        Write-Host "  x Missing: $file - $($requiredFiles[$file])" -ForegroundColor Red
        $missingFiles += $file
    }
}

Write-Host ""

# Check Python
Write-Host "Checking Python..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "  v Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "  x Python not found in PATH!" -ForegroundColor Red
}
Write-Host ""

# Check Nastran
Write-Host "Checking Nastran..." -ForegroundColor Yellow
try {
    $nastranCheck = Get-Command nastran -ErrorAction Stop
    Write-Host "  v Nastran found: $($nastranCheck.Source)" -ForegroundColor Green
} catch {
    Write-Host "  x Nastran not found in PATH!" -ForegroundColor Red
}
Write-Host ""

# Check HEEDS
Write-Host "Checking HEEDS..." -ForegroundColor Yellow
try {
    $heedsCheck = Get-Command heeds -ErrorAction Stop
    Write-Host "  v HEEDS found: $($heedsCheck.Source)" -ForegroundColor Green
} catch {
    Write-Host "  x HEEDS not found in PATH!" -ForegroundColor Red
}
Write-Host ""

# Final summary
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "Pre-Flight Check Complete" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

if ($missingFiles.Count -gt 0) {
    Write-Host "WARNING: Some files are missing!" -ForegroundColor Yellow
    Write-Host "You can proceed, but setup may need manual adjustments." -ForegroundColor Yellow
} else {
    Write-Host "v All checks passed!" -ForegroundColor Green
    Write-Host "You can now run: .\setup_thesis_workflows.ps1" -ForegroundColor Green
}
Write-Host ""