#!/usr/bin/env bash
set -e

# Usage: PUBLIC_PORT=8080 SECRET_KEY=... ADMIN_USER=... ADMIN_PASS=... bash install.sh
# Если PUBLIC_PORT не задан, скрипт спросит порт (по умолчанию 80)

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root (sudo)."; exit 1; fi

# --- Порт ---
if [ -z "${PUBLIC_PORT}" ]; then
  read -p "Введите порт для веб-интерфейса [80]: " PUBLIC_PORT
fi
PUBLIC_PORT=${PUBLIC_PORT:-80}
echo "Используем публичный порт: ${PUBLIC_PORT}" 

apt update
apt install -y python3 python3-venv python3-pip git docker.io nginx
systemctl enable --now docker

# App dir assumption: script executed inside project root
APP_DIR="$(pwd)"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Create .env (добавим PUBLIC_PORT для справки)
if [ ! -f .env ]; then
  cat > .env <<EOF
SECRET_KEY=${SECRET_KEY:-$(openssl rand -hex 16)}
ADMIN_USER=${ADMIN_USER:-admin}
ADMIN_PASS=${ADMIN_PASS:-admin}
PUBLIC_PORT=${PUBLIC_PORT}
EOF
fi

# Initialize DB and admin
python3 -c "from auth import init_db, ensure_admin; init_db(); ensure_admin(); print('DB initialized')"

# Systemd service
SERVICE_FILE=/etc/systemd/system/botmanager.service
cat > $SERVICE_FILE <<EOF
[Unit]
Description=Bot Manager Flask App
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python app.py
Restart=always
RestartSec=5
TimeoutStartSec=60
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now botmanager.service

# Nginx config
cat > /etc/nginx/sites-available/botmanager.conf <<EOF
server {
    listen ${PUBLIC_PORT};
    server_name _;

    proxy_send_timeout 300;
    proxy_read_timeout 300;

    location /socket.io/ {
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_pass http://127.0.0.1:5000/socket.io/;
    }

    location /static/ {
        alias $APP_DIR/static/;
    }

    location /override/ {
        alias $APP_DIR/uploads/;
    }

    location /health {
        proxy_pass http://127.0.0.1:5000/health;
    }

    location / {
        proxy_pass http://127.0.0.1:5000/;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF

ln -sf /etc/nginx/sites-available/botmanager.conf /etc/nginx/sites-enabled/botmanager.conf
rm -f /etc/nginx/sites-enabled/default || true
nginx -t
systemctl restart nginx

IP_ADDR=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -z "$IP_ADDR" ]; then
  IP_ADDR=$(curl -s https://ifconfig.me || echo "<SERVER_IP>")
fi
if [ "$PUBLIC_PORT" = "80" ]; then
  APP_URL="http://${IP_ADDR}/"
else
  APP_URL="http://${IP_ADDR}:${PUBLIC_PORT}/"
fi

echo "Installation complete. Login with ADMIN_USER/ADMIN_PASS."
echo "URL: ${APP_URL}"