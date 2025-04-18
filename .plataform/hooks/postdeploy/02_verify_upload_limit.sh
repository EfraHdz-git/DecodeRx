#!/bin/bash
echo "Verifying upload limits in Nginx config..."

# Check if client_max_body_size is set in any Nginx configuration
grep -r "client_max_body_size" /etc/nginx/ || echo "WARNING: client_max_body_size not found in any Nginx configuration"

# Restart Nginx to ensure configuration is applied
systemctl restart nginx || service nginx restart || echo "Failed to restart Nginx"

echo "Verification complete."