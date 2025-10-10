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

if [ "$PUBLIC_PORT" = "443" ]; then
  echo "WARNING: Порт 443 предназначен для HTTPS. Для HTTP рекомендуется порт 80 или 8080."
  read -p "Продолжить с портом 443? (y/N): " confirm
  if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "Установка прервана."
    exit 1
  fi
fi

echo "Используем публичный порт: ${PUBLIC_PORT}" 

apt update --fix-missing
apt install -y python3 python3-venv python3-pip git docker.io nginx
systemctl enable --now docker

# Создание пользователя botops для SSH доступа
echo "Создание пользователя botops..."
useradd -m -s /bin/bash botops || true
mkdir -p /home/botops/.ssh
chown -R botops:botops /home/botops/.ssh
chmod 700 /home/botops/.ssh

# Генерация SSH ключа если не существует
if [ ! -f /home/botops/.ssh/id_rsa ]; then
  echo "Генерация SSH ключа для пользователя botops..."
  sudo -u botops bash -c 'ssh-keygen -t rsa -b 4096 -N "" -f /home/botops/.ssh/id_rsa'
fi

# Добавление пользователя в группу docker
usermod -aG docker botops

echo "Пользователь botops настроен."

# Сделать скрипты исполняемыми
chmod +x diagnose.sh fix_install.sh

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
Environment=EXEC_MODE=ssh
Environment=SSH_HOST=localhost
Environment=SSH_USER=botops
Environment=SSH_KEY_PATH=/home/botops/.ssh/id_rsa

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

# Firewall configuration
ufw --force enable || true
ufw allow ${PUBLIC_PORT}/tcp
if [ "$PUBLIC_PORT" != "22" ]; then
  ufw allow 22/tcp  # SSH always allowed
fi
ufw --force reload || true
echo "Firewall: порт ${PUBLIC_PORT} открыт для веб-доступа"

IP_ADDR=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -z "$IP_ADDR" ]; then
  IP_ADDR=$(curl -s https://ifconfig.me 2>/dev/null || echo "<SERVER_IP>")
fi
if [ "$PUBLIC_PORT" = "80" ]; then
  APP_URL="http://${IP_ADDR}/"
elif [ "$PUBLIC_PORT" = "443" ]; then
  APP_URL="https://${IP_ADDR}/" 
else
  APP_URL="http://${IP_ADDR}:${PUBLIC_PORT}/"
fi

echo "Installation complete. Login with ADMIN_USER/ADMIN_PASS."
echo "URL: ${APP_URL}"

# Диагностика
echo "\n=== Диагностика ==="
echo "Статус службы:"
systemctl is-active botmanager || echo "ОШИБКА: Служба не запущена"
echo "Порт Flask (5000):"
ss -tlnp | grep :5000 || echo "ОШИБКА: Flask не слушает порт 5000"
echo "Порт Nginx (${PUBLIC_PORT}):"
ss -tlnp | grep :${PUBLIC_PORT} || echo "ОШИБКА: Nginx не слушает порт ${PUBLIC_PORT}"

echo "\nДля диагностики ошибок:" 
echo "  journalctl -u botmanager -n 20 --no-pager"
echo "  systemctl status botmanager"