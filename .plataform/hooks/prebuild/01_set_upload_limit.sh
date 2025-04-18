#!/bin/bash
echo "Setting upload limits in Nginx config..."

# Create a backup of any existing Nginx configuration
if [ -f /etc/nginx/nginx.conf ]; then
    cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.bak
fi

# Look for all Nginx conf files and add client_max_body_size if not already present
find /etc/nginx -name "*.conf" -exec grep -l "client_max_body_size" {} \; || find /etc/nginx -name "*.conf" -exec sed -i '/http {/a \ \ \ \ client_max_body_size 20M;' {} \;

echo "Setting complete."