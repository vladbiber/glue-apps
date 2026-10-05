#!/bin/sh
# Remove pacman's database lock left by a crash or a power cut, but only
# when no pacman is running (run through pkexec by Glue Apps).
if pgrep -x pacman >/dev/null 2>&1; then
    echo "pacman is running; the lock is in use." >&2
    exit 1
fi
rm -f /var/lib/pacman/db.lck
