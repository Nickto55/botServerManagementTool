#!/usr/bin/env bash
# Диагностика и исправление проблем с запуском контейнеров

set -e

APP_DIR="$(pwd)"
CONTAINER_NAME="$1"

if [ -z "$CONTAINER_NAME" ]; then
    echo "Использование: $0 <имя_контейнера>"
    echo "Пример: $0 my-bot"
    exit 1
fi

echo "=== Диагностика контейнера: $CONTAINER_NAME ==="

# Проверяем существование контейнера
echo "1. Проверка существования контейнера..."
if docker ps -a --filter name="^${CONTAINER_NAME}$" --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo "✓ Контейнер существует"
else
    echo "✗ Контейнер '$CONTAINER_NAME' не найден"
    echo "Доступные контейнеры:"
    docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
    exit 1
fi

# Проверяем статус контейнера
echo -e "\n2. Проверка статуса контейнера..."
STATUS=$(docker ps -a --filter name="^${CONTAINER_NAME}$" --format "{{.Status}}")
echo "Статус: $STATUS"

# Проверяем, запущен ли контейнер
if echo "$STATUS" | grep -q "Up"; then
    echo "✓ Контейнер запущен"
else
    echo "✗ Контейнер остановлен"
fi

# Проверяем команды в базе данных
echo -e "\n3. Проверка команд запуска в базе данных..."
if [ -f "$APP_DIR/venv/bin/python" ]; then
    COMMANDS=$($APP_DIR/venv/bin/python -c "
from auth import get_bot_commands
commands = get_bot_commands('$CONTAINER_NAME')
if commands:
    print(f'Launch command: {commands.launch_command or \"None\"}')
    print(f'Start command: {commands.start_command or \"None\"}')
    print(f'Stop command: {commands.stop_command or \"None\"}')
    print(f'Restart command: {commands.restart_command or \"None\"}')
else:
    print('Команды не найдены в базе данных')
")
    echo "$COMMANDS"
else
    echo "✗ Невозможно проверить базу данных - нет виртуального окружения"
fi

# Проверяем логи контейнера
echo -e "\n4. Последние логи контейнера..."
docker logs --tail 20 "$CONTAINER_NAME" 2>&1 || echo "Не удалось получить логи"

# Проверяем конфигурацию контейнера
echo -e "\n5. Конфигурация контейнера..."
docker inspect "$CONTAINER_NAME" --format "
Имя: {{.Name}}
Образ: {{.Config.Image}}
Команда: {{.Config.Cmd}}
Рабочая директория: {{.Config.WorkingDir}}
Restart Policy: {{.HostConfig.RestartPolicy.Name}}
" 2>/dev/null || echo "Не удалось получить конфигурацию"

echo -e "\n=== Рекомендации по исправлению ==="

# Проверяем на распространенные проблемы
if echo "$COMMANDS" | grep -q "docker run"; then
    echo "⚠️  ОБНАРУЖЕНА ПРОБЛЕМА: В команде запуска используется 'docker run'"
    echo "   Это неправильно! Для запуска существующего контейнера используйте 'docker start'"
    echo ""
    echo "   Решение:"
    echo "   1. Перейдите в настройки команд: /bot/$CONTAINER_NAME/commands"
    echo "   2. Очистите поле 'Команда запуска контейнера'"
    echo "   3. Или замените 'docker run ...' на 'docker start {{ container_name }}'"
    echo "   4. Сохраните изменения"
fi

if echo "$STATUS" | grep -q "Exited"; then
    echo "⚠️  Контейнер остановлен. Попробуйте запустить его:"
    echo "   docker start $CONTAINER_NAME"
fi

echo ""
echo "Быстрое исправление:"
echo "1. Сброс команд: /bot/$CONTAINER_NAME/reset-commands"
echo "2. Ручной запуск: docker start $CONTAINER_NAME"
echo "3. Проверка логов: docker logs $CONTAINER_NAME"

echo -e "\n=== Конец диагностики ==="