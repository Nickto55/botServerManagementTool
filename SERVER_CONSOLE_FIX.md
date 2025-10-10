# 🔧 Инструкция по отладке консоли сервера

## Что нужно проверить на сервере

### 1. Запустите диагностику
```bash
cd /root/botServerManagementTool
bash diagnose_server_console.sh
```

### 2. Проверьте логи приложения в реальном времени
```bash
# Откройте терминал на сервере и запустите:
tail -f /root/botServerManagementTool/logs/app.log

# Теперь откройте консоль сервера в браузере
# Введите команду 'ls'
# В логах должно появиться:
# Server console start requested
# [server_console] start session sid=xxx
# Server console input: 'ls'
```

### 3. Проверьте в браузере (это КРИТИЧНО!)

**Откройте консоль разработчика (F12) → вкладка Console**

Должны появляться сообщения:
```
[server_console] Output received: {data: "=== Консоль сервера ===\n"}
Connected to server console
[server_console] Sending command: ls
[server_console] Command started: {id: 1234567890, command: "ls"}
[server_console] Command result: {exit_code: 0, stdout: "...", ...}
[server_console] Output received: {data: "app.py\n..."}
```

**Если сообщений нет** - значит WebSocket не подключается!

### 4. Проверьте ошибки WebSocket в браузере

В консоли браузера (F12 → Console) проверьте:
- Есть ли ошибки подключения?
- Подключается ли socket.io?
- Есть ли ошибка CORS?

**Типичные ошибки:**
```
Failed to load resource: net::ERR_CONNECTION_REFUSED
WebSocket connection to 'ws://...' failed
404 Not Found: /socket.io/
```

## Решения

### Если WebSocket не подключается

1. **Проверьте что Flask-SocketIO установлен:**
```bash
pip install flask-socketio python-socketio eventlet
```

2. **Перезапустите приложение:**
```bash
systemctl restart bot-manager
# или
pkill -f "python.*app.py"
cd /root/botServerManagementTool
python app.py
```

3. **Проверьте nginx/прокси если используется:**
```nginx
# Добавьте в nginx.conf
location /socket.io {
    proxy_pass http://localhost:5000/socket.io;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

### Если WebSocket подключается, но команды не выполняются

1. **Проверьте exec_backend:**
```bash
cd /root/botServerManagementTool
python -c "
from exec_backend import get_backend
backend = get_backend()
stdout, stderr, code = backend.run('echo test')
print(f'stdout: {stdout}')
print(f'code: {code}')
"
```

2. **Проверьте SSH ключи (если используется SSH):**
```bash
ls -la ~/.ssh/
cat ~/.ssh/id_rsa.pub
```

3. **Проверьте права доступа:**
```bash
whoami
id
# Пользователь должен иметь права на выполнение команд
```

### Если ничего не помогает

1. **Проверьте что файлы обновлены на сервере:**
```bash
cd /root/botServerManagementTool
git pull  # если используете git
# или загрузите файлы вручную
```

2. **Перезагрузите все:**
```bash
systemctl restart bot-manager
systemctl restart nginx  # если используется
```

3. **Посмотрите полные логи:**
```bash
journalctl -u bot-manager -n 100
tail -100 /root/botServerManagementTool/logs/app.log
```

## Быстрый тест

Выполните на сервере:
```bash
cd /root/botServerManagementTool

# Тест 1: Импорты
python3 -c "from terminal_manager import start_server_console_session; print('OK')"

# Тест 2: Exec backend  
python3 -c "from exec_backend import get_backend; b=get_backend(); print(b.run('echo OK'))"

# Тест 3: App запускается
python3 -c "from app import app, socketio; print('OK')"
```

Если все 3 теста прошли - проблема скорее всего в WebSocket подключении (nginx/firewall).

## Что должно быть в логах браузера

**ПРАВИЛЬНО (работает):**
```
[server_console] Output received: {data: "..."}
Connected to server console
[server_console] Sending command: ls
[server_console] Command started: ...
[server_console] Output received: {data: "app.py\nauth.py\n..."}
[server_console] Command result: {exit_code: 0, ...}
```

**НЕПРАВИЛЬНО (не работает):**
```
(ничего не появляется)
или
WebSocket connection failed
или  
404 /socket.io/
```

---

## Контрольный список

- [ ] Файл `templates/server_console.html` существует
- [ ] Файл `terminal_manager.py` содержит функции консоли сервера
- [ ] В `app.py` есть обработчики `server_console_start` и `server_console_input`
- [ ] Flask-SocketIO установлен (`pip list | grep socketio`)
- [ ] Приложение запущено (`ps aux | grep app.py`)
- [ ] Порт 5000 открыт (`netstat -tuln | grep 5000`)
- [ ] В браузере нет ошибок 404 для `/socket.io/`
- [ ] В консоли браузера (F12) появляются логи WebSocket

Если все пункты выполнены - консоль должна работать!
