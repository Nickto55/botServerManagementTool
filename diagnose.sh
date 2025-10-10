#!/usr/bin/env bash
# Диагностика и исправление проблем Bot Manager

APP_DIR="$(pwd)"

echo "=== Bot Manager Диагностика ==="
echo "Рабочая директория: $APP_DIR"

echo -e "\n1. Проверка статуса службы..."
systemctl status botmanager --no-pager -l 2>/dev/null || echo "Служба botmanager не найдена"

echo -e "\n2. Последние логи службы..."
journalctl -u botmanager -n 30 --no-pager 2>/dev/null || echo "Логи службы недоступны"

echo -e "\n3. Проверка портов..."
echo "Flask (порт 5000):"
ss -tlnp | grep :5000 || echo "ОШИБКА: Flask не слушает порт 5000"

echo "Nginx:"
ss -tlnp | grep nginx || echo "Nginx не запущен"

echo -e "\n4. Проверка конфигурации nginx..."
nginx -t 2>/dev/null || echo "Ошибка конфигурации nginx"

echo -e "\n5. Проверка Python окружения..."
if [ -f "$APP_DIR/venv/bin/python" ]; then
    $APP_DIR/venv/bin/python --version
    echo "Путь к Python: $APP_DIR/venv/bin/python"
else
    echo "ОШИБКА: Виртуальное окружение не найдено в $APP_DIR/venv"
fi

echo -e "\n6. Проверка пользователя botops..."
id botops 2>/dev/null || echo "ОШИБКА: Пользователь botops не существует"
groups botops 2>/dev/null | grep -q docker && echo "✓ Пользователь botops в группе docker" || echo "✗ Пользователь botops НЕ в группе docker"

echo -e "\n7. Проверка SSH ключей..."
if [ -f "/home/botops/.ssh/id_rsa" ]; then
    echo "✓ SSH ключ существует"
    ls -la /home/botops/.ssh/id_rsa
else
    echo "✗ SSH ключ не найден"
fi

echo -e "\n8. Проверка Docker..."
docker --version
systemctl status docker --no-pager | head -3

echo -e "\n9. Тест импортов Python..."
cd "$APP_DIR"
if [ -f "venv/bin/python" ]; then
    echo "Тестирование импортов..."
    ./venv/bin/python -c "
try:
    import sys
    sys.path.insert(0, '$APP_DIR')
    print('✓ Config import...')
    from config import cfg
    print('✓ Auth import...')
    from auth import init_db, ensure_admin
    print('✓ Docker API import...')
    from docker_api import ensure_network
    print('✓ Exec backend import...')
    from exec_backend import get_backend
    backend = get_backend()
    print(f'✓ Backend: {type(backend).__name__}')
    print('Все импорты успешны!')
except Exception as e:
    print(f'✗ Ошибка импорта: {e}')
    import traceback
    traceback.print_exc()
"
else
    echo "✗ Невозможно протестировать импорты - нет виртуального окружения"
fi

echo -e "\n10. Проверка прав доступа..."
ls -la "$APP_DIR"
echo "Владелец директории:"
stat -c '%U:%G' "$APP_DIR"

echo -e "\n=== Конец диагностики ==="
echo "Для ручного запуска: cd $APP_DIR && ./venv/bin/python app.py"