#!/usr/bin/env bash
# ==============================================================================
# stop_production.sh - Gracefully stops Gunicorn and Nginx production servers
# ==============================================================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "Stopping MedNear Production stack..."
pkill -f "mednear_gunicorn" 2>/dev/null && echo "✓ Gunicorn stopped" || echo "Gunicorn was not running"
pkill -f "nginx -c $DIR/nginx.conf" 2>/dev/null && echo "✓ Nginx stopped" || echo "Nginx was not running"
echo "MedNear servers stopped."
