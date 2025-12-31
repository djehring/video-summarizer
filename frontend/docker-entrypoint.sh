#!/bin/sh

# If BACKEND_URL is not set (Railway), use simple nginx config (no proxy)
# If BACKEND_URL is set (Docker Compose), use full config with proxy
if [ -z "$BACKEND_URL" ]; then
    echo "No BACKEND_URL set - using simple nginx config (Railway mode)"
    cp /etc/nginx/conf.d/nginx.conf.template /etc/nginx/conf.d/default.conf
else
    echo "BACKEND_URL set to $BACKEND_URL - using proxy nginx config (Docker mode)"
    # nginx.conf already has proxy config, keep it
fi

exec nginx -g 'daemon off;'
