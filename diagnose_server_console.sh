#!/bin/bash
# Скрипт диагностики консоли сервера

echo "======================================"
echo "🔍 Диагностика консоли сервера"
echo "======================================"

cd /root/botServerManagementTool || exit 1

echo ""
echo "1️⃣ Проверка файлов..."
if [ -f "terminal_manager.py" ]; then
    echo "✅ terminal_manager.py найден"
else
    echo "❌ terminal_manager.py НЕ найден"
fi

if [ -f "templates/server_console.html" ]; then
    echo "✅ server_console.html найден"
else
    echo "❌ server_console.html НЕ найден"
fi

echo ""
echo "2️⃣ Проверка импортов Python..."
python3 -c "from terminal_manager import start_server_console_session, handle_server_console_input, close_server_console_session; print('✅ Импорт terminal_manager успешен')" 2>&1

echo ""
echo "3️⃣ Проверка exec_backend..."
python3 -c "from exec_backend import get_backend; b = get_backend(); stdout, stderr, code = b.run('echo test', timeout=5); print(f'✅ Exec backend работает: {stdout.strip()}')" 2>&1

echo ""
echo "4️⃣ Проверка обработчиков SocketIO в app.py..."
grep -c "server_console" app.py
echo "Найдено упоминаний 'server_console' в app.py: $(grep -c 'server_console' app.py)"

echo ""
echo "5️⃣ Проверка процесса приложения..."
if pgrep -f "python.*app.py" > /dev/null; then
    echo "✅ Приложение запущено (PID: $(pgrep -f 'python.*app.py'))"
else
    echo "⚠️  Приложение НЕ запущено"
fi

echo ""
echo "6️⃣ Проверка портов..."
if netstat -tuln | grep -q ":5000"; then
    echo "✅ Порт 5000 открыт"
else
    echo "⚠️  Порт 5000 не слушается"
fi

echo ""
echo "======================================"
echo "📋 Рекомендации:"
echo "======================================"
echo "1. Откройте браузер: http://your-server:5000/server-console"
echo "2. Нажмите F12 и откройте вкладку Console"
echo "3. Введите команду 'ls' и проверьте логи в консоли браузера"
echo "4. Проверьте логи сервера: tail -f /root/botServerManagementTool/logs/app.log"
echo ""
echo "Если команды не выполняются:"
echo "- Проверьте логи браузера на наличие ошибок WebSocket"
echo "- Проверьте что Flask-SocketIO установлен: pip install flask-socketio"
echo "- Перезапустите приложение: systemctl restart bot-manager"
