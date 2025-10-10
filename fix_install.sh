#!/usr/bin/env bash
# Исправление проблем после установки Bot Manager

set -e

echo "=== Исправление установки Bot Manager ==="

APP_DIR="$(pwd)"

# 1. Исправить права доступа
echo "1. Исправление прав доступа..."
chown -R $SUDO_USER:$SUDO_USER "$APP_DIR" 2>/dev/null || true
chmod +x "$APP_DIR/install.sh"
chmod +x "$APP_DIR/diagnose.sh"

# 2. Пересоздать виртуальное окружение если нужно
if [ ! -f "$APP_DIR/venv/bin/python" ]; then
    echo "2. Пересоздание виртуального окружения..."
    rm -rf "$APP_DIR/venv"
    python3 -m venv "$APP_DIR/venv"
    source "$APP_DIR/venv/bin/activate"
    pip install --upgrade pip
    pip install -r "$APP_DIR/requirements.txt"
fi

# 3. Инициализировать базу данных
echo "3. Инициализация базы данных..."
source "$APP_DIR/venv/bin/activate"
python3 -c "from auth import init_db, ensure_admin; init_db(); ensure_admin(); print('База данных инициализирована')"

# 4. Исправить пользователя botops
echo "4. Проверка пользователя botops..."
if ! id botops >/dev/null 2>&1; then
    echo "Создание пользователя botops..."
    useradd -m -s /bin/bash botops || true
fi

# SSH директория и ключи
mkdir -p /home/botops/.ssh
chown -R botops:botops /home/botops/.ssh
chmod 700 /home/botops/.ssh

if [ ! -f /home/botops/.ssh/id_rsa ]; then
    echo "Генерация SSH ключа..."
    sudo -u botops bash -c 'ssh-keygen -t rsa -b 4096 -N "" -f /home/botops/.ssh/id_rsa -q'
fi

# Добавить в docker группу
usermod -aG docker botops

# 5. Перезагрузить systemd и включить службу
echo "5. Настройка systemd службы..."
systemctl daemon-reload
systemctl enable botmanager.service 2>/dev/null || true

# 6. Проверить и перезапустить nginx
echo "6. Проверка nginx..."
nginx -t && systemctl restart nginx

echo "Исправление завершено!"
echo "Запустите: sudo systemctl start botmanager"
echo "Или для диагностики: ./diagnose.sh"