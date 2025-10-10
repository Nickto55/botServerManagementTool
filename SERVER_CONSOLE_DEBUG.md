# Диагностика проблемы консоли сервера

## Проблема
Консоль сервера открывается, но не реагирует на введенные команды.

## Возможные причины

### 1. WebSocket не подключается
**Проверка на сервере:**
```bash
# Проверить логи приложения
tail -f /root/botServerManagementTool/logs/app.log

# Должны появляться строки при подключении:
# [server_console] start session sid=...
```

**Проверка в браузере (F12 → Console):**
```javascript
// Должны быть сообщения:
[server_console] Output received: ...
Connected to server console
```

### 2. SocketIO не настроен правильно
**Проверка:**
```bash
cd /root/botServerManagementTool
python -c "from app import socketio; print('SocketIO OK')"
```

### 3. Exec backend не работает
**Проверка:**
```bash
cd /root/botServerManagementTool
python -c "from exec_backend import get_backend; b = get_backend(); print(b.run('echo test'))"
```

## Решение

### Шаг 1: Проверьте логи сервера
```bash
# Запустите приложение с выводом в консоль
cd /root/botServerManagementTool
python app.py

# В другом терминале откройте консоль сервера в браузере
# Введите команду и смотрите логи
```

### Шаг 2: Добавьте отладку
Откройте консоль браузера (F12) и введите команду. Должны появиться:
```
[server_console] Sending command: ls
[server_console] Command started: {id: ..., command: "ls"}
[server_console] Command result: {exit_code: 0, stdout: "...", ...}
[server_console] Output received: ...
```

### Шаг 3: Проверьте systemd service
Если приложение запущено через systemd:
```bash
# Перезапустите сервис
systemctl restart bot-manager

# Проверьте статус
systemctl status bot-manager

# Посмотрите логи
journalctl -u bot-manager -f
```

### Шаг 4: Проверьте права доступа
```bash
# Убедитесь что пользователь может выполнять команды
whoami
id

# Проверьте SSH ключи (если используется SSH backend)
ls -la ~/.ssh/
```

## Быстрое исправление

### Вариант 1: Перезапустить приложение
```bash
# Остановить
pkill -f "python.*app.py"

# Запустить заново
cd /root/botServerManagementTool
nohup python app.py > logs/server.log 2>&1 &
```

### Вариант 2: Проверить зависимости
```bash
cd /root/botServerManagementTool
pip install -r requirements.txt
```

### Вариант 3: Проверить файлы
```bash
# Убедитесь что все файлы на месте
ls -la templates/server_console.html
ls -la terminal_manager.py
grep "server_console" app.py
```

## Тестовый скрипт

Создайте файл `test_console.py`:
```python
#!/usr/bin/env python3
from terminal_manager import start_server_console_session, handle_server_console_input
from exec_backend import get_backend

# Тест exec_backend
backend = get_backend()
stdout, stderr, code = backend.run("echo 'Hello World'")
print(f"Test command:")
print(f"  stdout: {stdout}")
print(f"  stderr: {stderr}")
print(f"  exit_code: {code}")

if code == 0 and "Hello World" in stdout:
    print("✅ Exec backend работает!")
else:
    print("❌ Exec backend НЕ работает!")
```

Запустите:
```bash
cd /root/botServerManagementTool
python test_console.py
```

## Что проверить в коде

1. **app.py** - убедитесь что импорты правильные:
```python
from terminal_manager import start_server_console_session, handle_server_console_input, close_server_console_session
```

2. **terminal_manager.py** - убедитесь что функции экспортируются:
```python
def start_server_console_session(sid: str):
    ...

def handle_server_console_input(sid: str, data: str):
    ...
```

3. **server_console.html** - убедитесь что WebSocket подключается:
```javascript
socket.on('connect', function() {
    console.log('Connected to server console');
    socket.emit('server_console_start');
});
```

## Логи для проверки

После выполнения команды в консоли должны появиться:
```
[server_console] start session sid=xxx
Server console start requested
[server_console] input: ls
```

Если этих логов нет - WebSocket не работает.
Если логи есть, но нет ответа - проблема в exec_backend.
