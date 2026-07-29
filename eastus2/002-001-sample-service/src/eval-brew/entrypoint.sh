#!/bin/sh
# If a TLS cert is already mounted at /app/ssl/ (e.g. from a K8s secret),
# use it. Otherwise generate a self-signed cert so uvicorn can serve HTTPS
# on 8443 without a private key ever appearing in an image layer.
set -e
if [ ! -f /app/ssl/tls.key ]; then
    mkdir -p /app/ssl
    openssl req -x509 -newkey rsa:2048 \
        -keyout /app/ssl/tls.key -out /app/ssl/tls.crt \
        -days 365 -nodes \
        -subj "/CN=eval-brew" 2>/dev/null
    chmod 600 /app/ssl/tls.key
    chmod 644 /app/ssl/tls.crt
fi
exec uvicorn harness.ui:create_app --factory \
    --host 0.0.0.0 --port 8443 \
    --ssl-keyfile /app/ssl/tls.key \
    --ssl-certfile /app/ssl/tls.crt
