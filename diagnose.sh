#!/usr/bin/env bash
# Диагностика и исправление проблем Bot Manager

echo "=== Bot Manager Диагностика ==="

echo "1. Проверка статуса службы..."
systemctl status botmanager --no-pager -l

echo -e "\n2. Последние логи службы..."
journalctl -u botmanager -n 30 --no-pager

echo -e "\n3. Проверка портов..."
echo "Flask (порт 5000):"
ss -tlnp | grep :5000 || echo "ОШИБКА: Flask не слушает порт 5000"

echo "Nginx:"
ss -tlnp | grep nginx

echo -e "\n4. Проверка конфигурации nginx..."
nginx -t

echo -e "\n5. Проверка Python окружения..."
/opt/botmanager/venv/bin/python --version
echo "Путь к Python: /opt/botmanager/venv/bin/python"

echo -e "\n6. Быстрые исправления..."

echo "Проверка владельца файлов..."
ls -la /opt/botmanager/

echo -e "\n7. Тест запуска приложения..."
echo "Запуск Flask вручную (Ctrl+C для остановки):"
cd /opt/botmanager
sudo -u root /opt/botmanager/venv/bin/python -c "
try:
    import sys
    sys.path.insert(0, '/opt/botmanager')
    print('Importing modules...')
    from config import cfg
    print('Config OK')
    from auth import init_db, ensure_admin
    print('Auth OK')  
    from docker_api import ensure_network
    print('Docker API OK')
    print('All imports successful!')
except Exception as e:
    print(f'Import error: {e}')
    import traceback
    traceback.print_exc()
"