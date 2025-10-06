# Исправление ошибки Limiter

## Проблема
Служба botmanager падает с ошибкой:
```
TypeError: Limiter.__init__() got multiple values for argument 'key_func'
```

## Решение

### Способ 1: Ручное исправление на сервере
Выполните на сервере:

```bash
cd /root/botServerManagementTool

# Остановите службу
sudo systemctl stop botmanager

# Создайте backup
cp app.py app.py.backup

# Исправьте код (замените строки 58-62)
nano app.py
```

Найдите блок:
```python
# Rate limiting
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["100 per hour"]
)
```

Замените на:
```python
# Rate limiting
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per hour"]
)
limiter.init_app(app)
```

Сохраните файл (Ctrl+O, Enter, Ctrl+X) и запустите службу:
```bash
sudo systemctl start botmanager
systemctl status botmanager
curl http://localhost:5000/health
```

### Способ 2: Автоматическое исправление
Скопируйте исправленный app.py с Windows машины на сервер:

```bash
# На Windows (в PowerShell):
scp app.py root@87.120.166.213:/root/botServerManagementTool/

# На сервере:
sudo systemctl restart botmanager
systemctl status botmanager
```

### Проверка работоспособности
После исправления проверьте:

1. Статус службы: `systemctl status botmanager`
2. Логи: `journalctl -u botmanager -n 20`
3. Здоровье сервиса: `curl http://localhost:5000/health`
4. Веб-интерфейс: `http://87.120.166.213/`

Если всё работает правильно, вы должны увидеть:
- Служба в статусе "active (running)"
- Порт 5000 прослушивается Flask приложением
- JSON ответ от /health endpoint
- Доступна страница входа в веб-интерфейсе