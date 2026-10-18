#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "Stopping any existing server on port 3000..."
PID=$(lsof -ti :3000 || true)
if [ -n "$PID" ]; then
    kill -9 $PID 2>/dev/null || true
    echo "Stopped process $PID."
else
    echo "No process running on port 3000."
fi

echo "Starting MedNear server on http://localhost:3000..."
/opt/miniconda3/bin/python3 server.py
