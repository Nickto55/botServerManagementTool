# Исправление проблем с запуском Bot Server Management Tool

## Проблемы и решения

Основные проблемы, из-за которых служба не запускалась:

1. **Отсутствие файла .env** - содержит необходимые переменные окружения
2. **Проблемы с Docker** - приложение падало при недоступности Docker
3. **Недостаточная обработка ошибок** - отсутствовала диагностика проблем

## Внесенные изменения

### 1. Создан файл .env
Содержит базовые настройки приложения:
- SECRET_KEY
- ADMIN_USER/ADMIN_PASS  
- Настройки портов и Docker

### 2. Улучшена функция startup()
- Добавлена детальная обработка ошибок
- Приложение не падает при проблемах с Docker
- Подробное логирование процесса инициализации

### 3. Безопасные импорты
- Docker API импортируется с обработкой ошибок
- Созданы заглушки для функций при недоступности Docker
- Приложение остается функциональным даже без Docker

### 4. Улучшен endpoint /health
- Показывает статус инициализации
- Проверяет доступность Docker и базы данных
- Помогает в диагностике проблем

## Инструкция по обновлению на сервере

1. Скопируйте файлы на сервер:
   ```bash
   scp app.py .env update_server.sh root@your-server:/root/botServerManagementTool/
   ```

2. Запустите скрипт обновления:
   ```bash
   ssh root@your-server
   cd /root/botServerManagementTool
   chmod +x update_server.sh
   ./update_server.sh
   ```

3. Проверьте статус:
   ```bash
   systemctl status botmanager
   curl http://localhost:5000/health
   ```

## Диагностика проблем

Если служба все еще не запускается:

1. Проверьте логи:
   ```bash
   journalctl -u botmanager -n 20 --no-pager
   ```

2. Попробуйте запустить вручную:
   ```bash
   cd /root/botServerManagementTool
   source venv/bin/activate
   python app.py
   ```

3. Проверьте зависимости:
   ```bash
   source venv/bin/activate
   pip install -r requirements.txt
   ```

4. Проверьте права на файлы:
   ```bash
   ls -la /root/botServerManagementTool/
   chmod +x app.py
   ```

## Ожидаемый результат

После исправлений:
- Служба botmanager должна запускаться успешно
- Flask будет слушать порт 5000
- Nginx проксирует запросы с порта 80
- Веб-интерфейс должен быть доступен по http://your-server-ip/
- Даже при недоступности Docker, интерфейс входа должен работать