#!/bin/bash

# Быстрое исправление ошибки Limiter
# Применяется после основного update_server.sh

echo "=== Исправление ошибки Limiter ==="

# Проверяем, что мы в правильной директории
if [[ ! -f "app.py" ]]; then
    echo "ОШИБКА: Скрипт должен запускаться из директории botServerManagementTool"
    exit 1
fi

# Останавливаем службу
echo "Останавливаем службу botmanager..."
sudo systemctl stop botmanager

# Создаем backup текущего app.py
cp app.py app.py.backup.$(date +%Y%m%d_%H%M%S)
echo "Создан backup: app.py.backup.$(date +%Y%m%d_%H%M%S)"

# Применяем исправление для Limiter
echo "Применяем исправление для Limiter..."
sed -i '/^# Rate limiting$/,/^)$/{
    s/limiter = Limiter(/limiter = Limiter(/
    s/    app,//
    /^)$/ a\
limiter.init_app(app)
}' app.py

echo "Исправление применено"

# Проверяем синтаксис Python
echo "Проверяем синтаксис Python..."
source venv/bin/activate
python -m py_compile app.py
if [[ $? -eq 0 ]]; then
    echo "Синтаксис Python корректен"
else
    echo "ОШИБКА: Некорректный синтаксис Python"
    echo "Восстанавливаем из backup..."
    cp app.py.backup.* app.py
    exit 1
fi

# Запускаем службу
echo "Запускаем службу botmanager..."
sudo systemctl start botmanager

# Ждем и проверяем статус
sleep 5
echo ""
echo "=== Статус службы ==="
sudo systemctl status botmanager --no-pager -l

echo ""
echo "=== Проверка здоровья ==="
for i in {1..5}; do
    echo "Попытка $i/5..."
    if curl -s http://localhost:5000/health > /dev/null; then
        echo "✓ Сервис работает!"
        curl -s http://localhost:5000/health | python3 -m json.tool || echo "Ответ получен, но не JSON"
        break
    else
        if [[ $i -eq 5 ]]; then
            echo "✗ Сервис не отвечает"
            echo "Проверим логи..."
            journalctl -u botmanager -n 10 --no-pager
        else
            echo "  Ждем еще 3 секунды..."
            sleep 3
        fi
    fi
done

echo ""
echo "=== Исправление завершено ==="