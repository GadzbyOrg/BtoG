# --- CONFIGURATION ---
$ContainerName = "migration_staging_db"
$DbName = "old_staging_db"
$DbPassword = "password"
$HostPort = "5434"
$DumpFilePath = ".\backup_borgia.dump"

# Check if dump file exists
if (-not (Test-Path $DumpFilePath)) {
    Write-Host "Error: Dump file not found at $DumpFilePath" -ForegroundColor Red
    exit 1
}

Write-Host "--- STARTING AUTOMATED MIGRATION (WINDOWS) ---" -ForegroundColor Cyan

# 1. Cleanup previous runs
Write-Host "Cleaning up old containers..." -ForegroundColor Yellow
docker rm -f $ContainerName 2>$null

# 2. Start Docker Container
Write-Host "Starting Staging Database container..." -ForegroundColor Yellow
docker run --name $ContainerName `
    -e POSTGRES_PASSWORD=$DbPassword `
    -e POSTGRES_DB=$DbName `
    -p "${HostPort}:5432" `
    -d postgres:latest

# 3. Wait for Postgres to wake up
Write-Host "Waiting for Database to accept connections..." -ForegroundColor Yellow
$Retries = 0
do {
    Start-Sleep -Seconds 2
    $Status = docker exec $ContainerName pg_isready -U postgres 2>$null
    Write-Host -NoNewline "."
    $Retries++
    if ($Retries -gt 30) { 
        Write-Host "`nTimeout waiting for Postgres." -ForegroundColor Red
        exit 1 
    }
} until ($Status -match "accepting connections")

Write-Host "Database is ready!" -ForegroundColor Green

# 4. Restore dump
Write-Host "restoring dump..." -ForegroundColor Yellow

# Copy dump file into container
docker cp $DumpFilePath "${ContainerName}:/tmp/restore.dump"

# Restore
# We capture stderr/stdout to a log file because pg_restore is verbose
docker exec $ContainerName pg_restore -U postgres -d $DbName --no-owner -v /tmp/restore.dump 2>&1 | Out-File "restore_log.txt"

Write-Host "Restore complete logs saved to restore_log.txt" -ForegroundColor Green

# 5. Run Python ETL Script
Write-Host "Running Python ETL script..." -ForegroundColor Yellow
try {
    .venv/Scripts/activate
    python script.py
}
catch {
    Write-Host "Python script failed. Check your Python installation." -ForegroundColor Red
}

# 6. Cleanup
Write-Host "🧹 Shutting down container..."
docker stop $ContainerName
docker rm $ContainerName

Write-Host "--- PROCESS COMPLETE ---" -ForegroundColor Cyan