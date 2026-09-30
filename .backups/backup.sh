#!/bin/bash
# Automated daily SQLite backup during Phase 1 development
# Prevents data loss during concurrency fix and accessibility work

DB_FILE="./data/ebike_listings.db"
BACKUP_DIR="./.backups"
DATE=$(date +%Y-%m-%d)
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)

# Create backup directory if missing
mkdir -p "$BACKUP_DIR"

# Verify DB exists
if [ ! -f "$DB_FILE" ]; then
    echo "⚠️  Database not found: $DB_FILE"
    exit 1
fi

# Copy current DB with timestamp
cp "$DB_FILE" "$BACKUP_DIR/ebike-listings-${TIMESTAMP}.db"

# Keep only 7-day rolling window (delete older backups)
find "$BACKUP_DIR" -name "ebike-listings-*.db" -mtime +7 -delete

# Report
BACKUP_FILE="$BACKUP_DIR/ebike-listings-${TIMESTAMP}.db"
SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "✅ Backup created: $BACKUP_FILE ($SIZE)"
echo "📁 Backups stored in: $BACKUP_DIR"
echo "🔄 Keeping 7-day rolling history"
