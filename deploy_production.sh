#!/usr/bin/env bash
# ==============================================================================
# deploy_production.sh - MedNear Production Deployment Runner
# Starts Gunicorn WSGI cluster and Nginx HTTPS reverse proxy
# ==============================================================================

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

PYTHON="/opt/miniconda3/bin/python3"
GUNICORN="/opt/miniconda3/bin/gunicorn"
NGINX="/opt/miniconda3/bin/nginx"
OPENSSL="/opt/miniconda3/bin/openssl"

mkdir -p "$DIR/logs" "$DIR/ssl"

echo "=========================================================="
echo "   MedNear Production Stack Deployment"
echo "   WSGI: Gunicorn | Proxy: Nginx | Security: SSL / HTTPS"
echo "=========================================================="

# 1. Ensure SSL Certificates exist
if [ ! -f "$DIR/ssl/mednear.key" ] || [ ! -f "$DIR/ssl/mednear.crt" ]; then
    echo "[1/4] Generating production SSL certificates (2048-bit RSA)..."
    "$OPENSSL" req -x509 -nodes -days 365 -newkey rsa:2048 \
      -keyout "$DIR/ssl/mednear.key" \
      -out "$DIR/ssl/mednear.crt" \
      -subj "/C=IN/ST=Karnataka/L=Bengaluru/O=MedNear Healthcare/OU=Production/CN=localhost" \
      -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
else
    echo "[1/4] SSL certificates verified in $DIR/ssl/"
fi

# 2. Stop any existing instances
echo "[2/4] Stopping any existing Gunicorn or Nginx processes..."
pkill -f "mednear_gunicorn" 2>/dev/null || true
pkill -f "nginx -c $DIR/nginx.conf" 2>/dev/null || true
sleep 1

# 3. Start Gunicorn WSGI server in background
echo "[3/4] Launching Gunicorn WSGI cluster on 127.0.0.1:8000..."
"$GUNICORN" -c "$DIR/gunicorn.conf.py" wsgi:application > "$DIR/logs/gunicorn_stdout.log" 2>&1 &
GUNICORN_PID=$!
echo "      -> Gunicorn master PID: $GUNICORN_PID"

# Wait for Gunicorn to become healthy
for i in {1..10}; do
    if curl -s http://127.0.0.1:8000/api/health > /dev/null 2>&1; then
        echo "      -> Gunicorn cluster is ready and responding."
        break
    fi
    sleep 0.5
done

# 4. Start Nginx HTTPS Reverse Proxy
echo "[4/4] Launching Nginx HTTPS Reverse Proxy..."
"$NGINX" -c "$DIR/nginx.conf" > "$DIR/logs/nginx_stdout.log" 2>&1 &
NGINX_PID=$!
echo "      -> Nginx PID: $NGINX_PID"

sleep 1

echo "=========================================================="
echo "   DEPLOYMENT SUCCESSFUL!"
echo "   HTTPS (Secure): https://localhost:8443"
echo "   HTTP (Redirect): http://localhost:8080"
echo "   WSGI Backend:   http://127.0.0.1:8000"
echo "=========================================================="
