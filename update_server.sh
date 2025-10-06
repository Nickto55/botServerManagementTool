#!/bin/bash

# Скрипт для обновления Bot Server Management Tool
# Этот скрипт должен запускаться из директории botServerManagementTool

echo "=== Обновление Bot Server Management Tool ==="

# Проверяем, что мы в правильной директории
if [[ ! -f "app.py" ]]; then
    echo "ОШИБКА: Скрипт должен запускаться из директории botServerManagementTool"
    exit 1
fi

# Останавливаем службу
echo "Останавливаем службу botmanager..."
sudo systemctl stop botmanager

# Создаем .env файл, если его нет
if [[ ! -f ".env" ]]; then
    echo "Создаем файл .env..."
    cat > .env << 'EOF'
# Конфигурация Bot Server Management Tool
# Скопировано из .env.example и настроено для сервера

# Базовые настройки
SECRET_KEY=your-very-secure-secret-key-change-me-in-production
ADMIN_USER=admin
ADMIN_PASS=admin123

# Сеть и порты
PUBLIC_PORT=80
FLASK_HOST=0.0.0.0
FLASK_PORT=5000

# Docker
DOCKER_BASE_NETWORK=bots_net
BOT_DEFAULT_IMAGE=python:3.11-slim

# Git
GIT_CLONE_DEPTH=1

# Безопасность
BCRYPT_ROUNDS=12
EOF
    echo "Файл .env создан"
else
    echo "Файл .env уже существует, пропускаем"
fi

# Создаем необходимые директории
echo "Создаем необходимые директории..."
mkdir -p logs bots uploads

# Устанавливаем правильные права на директории
echo "Устанавливаем права на директории..."
chmod 755 logs bots uploads

# Проверяем виртуальное окружение
if [[ ! -d "venv" ]]; then
    echo "Создаем виртуальное окружение..."
    python3 -m venv venv
fi

# Активируем виртуальное окружение и устанавливаем зависимости
echo "Устанавливаем зависимости..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Перезапускаем службу
echo "Запускаем службу botmanager..."
sudo systemctl start botmanager

# Ждем немного и проверяем статус
sleep 3
echo ""
echo "=== Статус службы ==="
sudo systemctl status botmanager --no-pager -l

echo ""
echo "=== Проверка портов ==="
echo "Flask (порт 5000):"
ss -tulpn | grep :5000 || echo "  Порт 5000 не прослушивается"
echo "Nginx (порт 80):"  
ss -tulpn | grep :80 || echo "  Порт 80 не прослушивается"

echo ""
echo "=== Проверка логов (последние 10 строк) ==="
journalctl -u botmanager -n 10 --no-pager

echo ""
echo "=== Обновление завершено ==="
echo "Для диагностики используйте:"
echo "  systemctl status botmanager"
echo "  journalctl -u botmanager -f"
echo "  curl http://localhost:5000/health"