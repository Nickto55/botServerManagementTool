#!/usr/bin/env bash
# Исправление SSH ключей для Bot Manager

set -e

echo "=== Исправление SSH ключей ==="

# Проверяем, что скрипт запущен от root
if [ "$(id -u)" -ne 0 ]; then
  echo "Запустите скрипт от root (sudo)"
  exit 1
fi

# Создание пользователя botops если не существует
if ! id botops >/dev/null 2>&1; then
  echo "Создание пользователя botops..."
  useradd -m -s /bin/bash botops
fi

# Настройка SSH директории
echo "Настройка SSH директории..."
mkdir -p /home/botops/.ssh
chown -R botops:botops /home/botops/.ssh
chmod 700 /home/botops/.ssh

# Удаляем старые ключи если они существуют
if [ -f "/home/botops/.ssh/id_rsa" ]; then
  echo "Удаление старых SSH ключей..."
  rm -f /home/botops/.ssh/id_rsa
  rm -f /home/botops/.ssh/id_rsa.pub
fi

# Генерация новых SSH ключей
echo "Генерация новых SSH ключей (RSA 2048)..."
sudo -u botops ssh-keygen -t rsa -b 2048 -N "" -f /home/botops/.ssh/id_rsa -q

# Настройка authorized_keys
echo "Настройка authorized_keys..."
sudo -u botops bash -c 'cat /home/botops/.ssh/id_rsa.pub >> /home/botops/.ssh/authorized_keys'
chmod 600 /home/botops/.ssh/authorized_keys
chown botops:botops /home/botops/.ssh/authorized_keys

# Добавление в группу docker
echo "Добавление пользователя в группу docker..."
usermod -aG docker botops

# Проверка ключей
echo "Проверка сгенерированных ключей..."
python3 -c "
import paramiko
try:
    key = paramiko.RSAKey.from_private_key_file('/home/botops/.ssh/id_rsa')
    print('✓ SSH ключ валиден')
except Exception as e:
    print(f'✗ Ошибка SSH ключа: {e}')
    exit(1)
"

echo "✓ SSH ключи исправлены успешно!"
echo ""
echo "Проверка ключей:"
ls -la /home/botops/.ssh/
echo ""
echo "Перезапустите службу: systemctl restart botmanager"