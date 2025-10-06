# Bot Server Management Tool

Веб-приложение на Flask для управления Docker-контейнерами ботов:

Функционал:
- Аутентификация (логин/пароль, хранение в SQLite + bcrypt)
- Создание бота из GitHub репозитория (git clone + сборка/запуск контейнера)
- Управление контейнером: старт, стоп, рестарт, удаление
- Веб-терминал (docker exec + Socket.IO)
- Загрузка и замена frontend файлов (HTML/CSS/JS) через uploads
- Nginx reverse proxy + поддержка WebSocket

## Стек
- Python 3.11
- Flask + Flask-SocketIO (eventlet)
- Docker SDK for Python
- GitPython
- SQLAlchemy (SQLite)
- bcrypt
- Nginx

## Структура
```
app.py                # Точка входа
auth.py               # Аутентификация и модель пользователя
docker_api.py         # Управление Docker контейнерами
terminal_manager.py   # Терминальные сессии через SocketIO
config.py             # Конфигурация
install.sh            # Скрипт установки на Ubuntu
Dockerfile.bot        # Базовый Dockerfile для ботов
nginx.conf            # Пример конфига Nginx
requirements.txt
/templates            # Jinja2 шаблоны
/static/js            # JS (terminal.js)
/bots                 # Склонированные репозитории ботов
/uploads              # Загруженные override файлы фронтенда
/logs                 # Логи (можно использовать позднее)
```

## Быстрый старт (локально)
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
export SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(16))')
export ADMIN_USER=admin
export ADMIN_PASS=admin
python -c "from auth import init_db, ensure_admin; init_db(); ensure_admin()"
python app.py
```
Открыть: http://127.0.0.1:5000

## Установка на Ubuntu (рекомендуемо)
```bash
git clone https://github.com/USER/botServerManagementTool.git
cd botServerManagementTool
sudo bash install.sh
```
Переменные окружения (опционально до запуска):
```bash
sudo SECRET_KEY=$(openssl rand -hex 16) ADMIN_USER=admin ADMIN_PASS=strongpass bash install.sh
```
После установки сервис: `systemctl status botmanager`

## Добавление в Git (если локально создавали проект)
```bash
git init
git add .
git commit -m "Initial version"
git branch -M main
git remote add origin git@github.com:USER/botServerManagementTool.git
git push -u origin main
```

## Использование
1. Войти (admin / admin или заданные переменные)
2. На дашборде указать Git URL репозитория бота (например https://github.com/user/mybot.git)
3. (Опционально) имя контейнера и ветку
4. Нажать Создать — появится контейнер
5. Клик по имени открывает веб-терминал
6. Кнопки управления: ▶ старт, ■ стоп, ↻ рестарт, ✖ удалить

## Ожидания по репозиторию бота
- Если в репо есть свой Dockerfile — он будет использован.
- Если нет, используется `Dockerfile.bot` и каталог монтируется внутрь контейнера `/app`.
- При необходимости добавьте `requirements.txt` и файл `main.py`.

## Безопасность
- Смените SECRET_KEY и ADMIN_PASS сразу после установки.
- Ограничьте доступ к серверу по firewall.
- Для production добавьте HTTPS (certbot + nginx).

## Обновление
```bash
cd /opt/botmanager   # если перенесете туда
sudo systemctl stop botmanager
git pull
source venv/bin/activate
pip install -r requirements.txt --upgrade
sudo systemctl start botmanager
```

## TODO / Возможные улучшения
- Роли пользователей
- Логи контейнеров в веб-интерфейсе
- Управление ресурсами (лимиты CPU/RAM)
- Поддержка docker compose

## Лицензия
MIT (добавьте LICENSE при необходимости)

## Health-check
Маршрут `/health` возвращает `{"status":"ok"}` для использования в мониторинге или проверках Nginx / systemd.

## Чистая переустановка (если всё удалили)
```bash
# предположим вы удалили каталог
sudo systemctl stop botmanager || true
sudo rm -f /etc/systemd/system/botmanager.service
sudo rm -f /etc/nginx/sites-enabled/botmanager.conf /etc/nginx/sites-available/botmanager.conf
sudo systemctl daemon-reload
sudo systemctl restart nginx

# Клонируем заново
cd /opt
sudo git clone https://github.com/USER/botServerManagementTool.git botmanager
cd botmanager
sudo bash install.sh
```
Проверьте:
```bash
curl -f http://127.0.0.1/health
systemctl status botmanager
nginx -t
```

## Деплой в /opt (вариант)
Можно переместить проект до запуска скрипта:
```bash
sudo mv ~/botServerManagementTool /opt/botmanager
cd /opt/botmanager
sudo bash install.sh
```
Тогда пути в nginx будут ссылаться на `/opt/botmanager`.