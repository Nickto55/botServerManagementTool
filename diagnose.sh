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
    echo "✓ SSH приватный ключ существует"
    ls -la /home/botops/.ssh/id_rsa
else
    echo "✗ SSH приватный ключ не найден"
fi

if [ -f "/home/botops/.ssh/id_rsa.pub" ]; then
    echo "✓ SSH публичный ключ существует"
    ls -la /home/botops/.ssh/id_rsa.pub
else
    echo "✗ SSH публичный ключ не найден"
fi

if [ -f "/home/botops/.ssh/authorized_keys" ]; then
    echo "✓ SSH authorized_keys существует"
    ls -la /home/botops/.ssh/authorized_keys
    grep -q "$(cat /home/botops/.ssh/id_rsa.pub 2>/dev/null)" /home/botops/.ssh/authorized_keys && echo "✓ Публичный ключ добавлен в authorized_keys" || echo "✗ Публичный ключ НЕ добавлен в authorized_keys"
else
    echo "✗ SSH authorized_keys не найден"
fi

# Проверяем, что ключ может быть прочитан
if [ -f "$APP_DIR/venv/bin/python" ] && [ -f "/home/botops/.ssh/id_rsa" ]; then
    echo "Тестирование SSH ключа..."
    $APP_DIR/venv/bin/python -c "
import paramiko
try:
    key = paramiko.RSAKey.from_private_key_file('/home/botops/.ssh/id_rsa')
    print('✓ SSH ключ валиден')
except Exception as e:
    print(f'✗ SSH ключ поврежден: {e}')
    print('Перегенерация ключа...')
    import subprocess
    import os
    # Удаляем старые ключи
    os.remove('/home/botops/.ssh/id_rsa')
    os.remove('/home/botops/.ssh/id_rsa.pub') if os.path.exists('/home/botops/.ssh/id_rsa.pub') else None
    # Генерируем новые
    result = subprocess.run(['sudo', '-u', 'botops', 'ssh-keygen', '-t', 'rsa', '-b', '2048', '-N', '', '-f', '/home/botops/.ssh/id_rsa', '-q'], 
                          capture_output=True, text=True)
    if result.returncode == 0:
        print('✓ SSH ключ перегенерирован')
        # Добавляем в authorized_keys
        with open('/home/botops/.ssh/id_rsa.pub', 'r') as f:
            pub_key = f.read().strip()
        with open('/home/botops/.ssh/authorized_keys', 'a') as f:
            f.write(pub_key + '\n')
        os.chmod('/home/botops/.ssh/authorized_keys', 0o600)
        print('✓ Публичный ключ добавлен в authorized_keys')
    else:
        print(f'✗ Ошибка перегенерации: {result.stderr}')
"
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
    
    # Тестируем SSH backend
    try:
        backend = get_backend()
        print(f'✓ Backend: {type(backend).__name__}')
        
        if hasattr(backend, 'key_path'):
            print(f'✓ SSH key path: {backend.key_path}')
            import os
            if os.path.exists(backend.key_path):
                print('✓ SSH key file exists')
            else:
                print('✗ SSH key file not found')
        
        # Простой тест команды
        stdout, stderr, code = backend.run('echo "SSH backend test"')
        if code == 0 and 'SSH backend test' in stdout:
            print('✓ SSH backend работает')
        else:
            print(f'✗ SSH backend ошибка: code={code}, stderr={stderr}')
    except Exception as e:
        print(f'✗ SSH backend недоступен: {e}')
        import traceback
        traceback.print_exc()
    
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
echo ""
echo "Для исправления SSH ключей выполните:"
echo "  sudo -u botops ssh-keygen -t rsa -b 2048 -N '' -f /home/botops/.ssh/id_rsa -q"
echo "  sudo -u botops bash -c 'cat /home/botops/.ssh/id_rsa.pub >> /home/botops/.ssh/authorized_keys'"
echo "  chmod 600 /home/botops/.ssh/authorized_keys"