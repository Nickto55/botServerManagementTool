# Добавлена консоль основного сервера

## Изменения в этом коммите:

### Новые файлы:
- `templates/server_console.html` - интерфейс консоли сервера
- `SERVER_CONSOLE_DEBUG.md` - руководство по диагностике
- `SERVER_CONSOLE_FIX.md` - решение проблем
- `diagnose_server_console.sh` - скрипт автоматической диагностики
- `test_server_console.py` - тесты для консоли сервера

### Измененные файлы:
- `app.py`:
  - Добавлен маршрут `/server-console`
  - Добавлены обработчики SocketIO для консоли сервера
  - Исправлен дубликат импорта `emit`
  
- `terminal_manager.py`:
  - Добавлены функции консоли сервера:
    - `start_server_console_session()`
    - `handle_server_console_input()`
    - `close_server_console_session()`
  
- `templates/dashboard.html`:
  - Добавлена кнопка "Консоль сервера" в панель управления

- `TROUBLESHOOTING.md`:
  - Добавлен раздел о проблемах запуска контейнеров

## Функционал:

Консоль основного сервера позволяет:
- ✅ Выполнять команды на хост-системе (не в контейнерах)
- ✅ Просматривать историю команд
- ✅ Использовать специальные команды (`:history`, `:clear`)
- ✅ Работать в полноэкранном режиме
- ✅ Видеть код выхода и время выполнения команд
- ✅ Отладочные логи в консоли браузера

## Установка на сервере:

```bash
cd /root/botServerManagementTool
git pull origin main
pip install flask-socketio python-socketio eventlet
systemctl restart bot-manager
```

## Использование:

1. Откройте `/server-console` в браузере
2. Введите команду (например: `ls`, `docker ps`, `systemctl status`)
3. Просмотрите результат выполнения

## Диагностика:

Если консоль не работает:
```bash
bash diagnose_server_console.sh
tail -f logs/app.log
```

Проверьте в браузере (F12 → Console) наличие логов WebSocket.

## Безопасность:

- Требуется авторизация пользователя
- Все команды выполняются от имени пользователя сервера
- История команд сохраняется для каждой сессии
