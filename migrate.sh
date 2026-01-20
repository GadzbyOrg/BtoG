#!/bin/bash

# Configuration
CONTAINER_NAME="migration_staging_db"
DB_NAME="old_staging_db"
DB_PASSWORD="password"
HOST_PORT="5433"
DUMP_FILE_PATH="./backup_borgia.dump"

# Check if dump file exists
if [ ! -f "$DUMP_FILE_PATH" ]; then
    echo "❌ Error: Dump introuvable $DUMP_FILE_PATH"
    exit 1
fi

# 1. Cleanup previous runs
echo "Cleaning up old containers..."
docker rm -f $CONTAINER_NAME 2>/dev/null || true

# 2. Start Docker Container
echo "Starting Staging Database container..."
docker run --name $CONTAINER_NAME \
    -e POSTGRES_PASSWORD=$DB_PASSWORD \
    -p $HOST_PORT:5432 \
    -d postgres:latest

# 3. Wait for Postgres to wake up
echo "Waiting for Database to accept connections..."
until docker exec $CONTAINER_NAME pg_isready -U postgres > /dev/null 2>&1; do
    echo -n "."
    sleep 1
done
echo " Ready!"

# 4. Create DB and Restore
echo "Creating database and restoring dump..."
# Create DB
docker exec $CONTAINER_NAME createdb -U postgres $DB_NAME

# Copy dump file into container
docker cp "$DUMP_FILE_PATH" $CONTAINER_NAME:/tmp/restore.dump

# Restore (using --no-owner to avoid permission errors)
docker exec $CONTAINER_NAME pg_restore -U postgres -d $DB_NAME --no-owner -v /tmp/restore.dump > restore_log.txt 2>&1

echo "✅ Restore complete (logs saved to restore_log.txt)."

#TODO : Check user consent before running python

# 5. Run Python script
echo "Running Python script..."
#python3 script.py

# 6. Cleanup
echo "Shutting down container..."
#docker stop $CONTAINER_NAME
#docker rm $CONTAINER_NAME

echo "--- 🎉 PROCESS COMPLETE ---"