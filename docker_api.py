import os
import shutil
import tempfile
import subprocess
from datetime import datetime
from typing import List, Dict, Optional

import docker
from git import Repo

from config import cfg

_client = None


def normalize_docker_name(name: str) -> str:
    """
    Нормализовать имя для использования в Docker
    - Приводит к нижнему регистру
    - Заменяет недопустимые символы на дефисы
    - Убирает множественные дефисы
    """
    import re
    # Приводим к нижнему регистру и заменяем недопустимые символы
    normalized = re.sub(r'[^a-z0-9_.-]', '-', name.lower())
    # Убираем множественные дефисы
    normalized = re.sub(r'-+', '-', normalized)
    # Убираем дефисы в начале и конце
    normalized = normalized.strip('-')
    # Docker имена не могут быть пустыми или начинаться с цифры
    if not normalized or normalized[0].isdigit():
        normalized = f"bot-{normalized}"
    return normalized


def get_client():
    global _client
    if _client is None:
        try:
            _client = docker.from_env()
        except Exception as e:
            raise RuntimeError(f"Не удалось инициализировать Docker клиент: {e}")
    return _client


def list_bots() -> List[Dict]:
    try:
        containers = get_client().containers.list(all=True)
    except Exception as e:
        return [{'id': '-', 'name': 'ERROR', 'status': f'docker err: {e}', 'image': '-', 'created': '-'}]
    data = []
    for c in containers:
        data.append({
            'id': c.id[:12],
            'name': c.name,
            'status': c.status,
            'image': c.image.tags[0] if c.image.tags else c.image.short_id,
            'created': c.attrs.get('Created')
        })
    return data


def start_bot(name: str):
    """Запустить бот с использованием кастомной команды, если она задана"""
    try:
        # Получаем контейнер
        container = get_client().containers.get(name)
        original_status = container.status
        
        # Сначала запускаем контейнер стандартным способом
        if container.status != 'running':
            container.start()
            # Ждем немного, чтобы контейнер успел запуститься
            import time
            time.sleep(2)
            # Обновляем статус
            container.reload()
        
        # Проверяем команды только после успешного запуска контейнера
        try:
            from auth import get_bot_commands
            commands = get_bot_commands(name)
        except Exception as e:
            # Если база данных недоступна - просто возвращаем успех запуска
            return f"Контейнер запущен (статус: {original_status} → {container.status}). База команд недоступна: {str(e)}"
        
        # Если есть кастомная команда запуска, выполняем её
        if commands and commands.start_command:
            import subprocess
            command = commands.start_command.replace('{{ container_name }}', name)
            
            # Проверяем что контейнер действительно запущен перед выполнением команды
            if container.status != 'running':
                return f"Контейнер не удалось запустить (статус: {container.status}), кастомная команда пропущена"
            
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                # Не падаем, просто сообщаем об ошибке команды
                return f"Контейнер запущен, но кастомная команда завершилась с ошибкой.\nКоманда: {command}\nОшибка: {result.stderr}\nВывод: {result.stdout}"
            return f"Контейнер запущен. Выполнена команда: {command}\nВывод: {result.stdout}"
        else:
            return f"Контейнер запущен стандартным способом (статус: {original_status} → {container.status})"
    except Exception as e:
        raise RuntimeError(f"Ошибка запуска: {str(e)}")


def stop_bot(name: str):
    """Остановить бот с использованием кастомной команды, если она задана"""
    try:
        from auth import get_bot_commands
        commands = get_bot_commands(name)
        container = get_client().containers.get(name)
        
        # Если есть кастомная команда остановки и контейнер запущен, выполняем её
        if commands and commands.stop_command and container.status == 'running':
            import subprocess
            command = commands.stop_command.replace('{{ container_name }}', name)
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                # Если кастомная команда не сработала, всё равно останавливаем контейнер
                container.stop()
                return f"Кастомная команда завершилась с ошибкой, но контейнер остановлен принудительно.\nОшибка: {result.stderr}"
            else:
                # После выполнения кастомной команды останавливаем контейнер (если он всё ещё работает)
                container.reload()
                if container.status == 'running':
                    container.stop()
                return f"Выполнена команда: {command}\nВывод: {result.stdout}\nКонтейнер остановлен"
        else:
            # Стандартное поведение
            if container.status == 'running':
                container.stop()
                return "Контейнер остановлен стандартным способом"
            else:
                return "Контейнер уже остановлен"
    except Exception as e:
        raise RuntimeError(f"Ошибка остановки: {str(e)}")


def restart_bot(name: str):
    """Перезапустить бот с использованием кастомной команды, если она задана"""
    try:
        from auth import get_bot_commands
        commands = get_bot_commands(name)
        container = get_client().containers.get(name)
        
        if commands and commands.restart_command:
            # Выполняем кастомную команду через subprocess
            import subprocess
            command = commands.restart_command.replace('{{ container_name }}', name)
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                # Если кастомная команда не сработала, перезапускаем стандартным способом
                container.restart()
                return f"Кастомная команда завершилась с ошибкой, выполнен стандартный перезапуск.\nОшибка: {result.stderr}"
            return f"Выполнена команда: {command}\nВывод: {result.stdout}"
        else:
            # Стандартное поведение
            container.restart()
            return "Контейнер перезапущен стандартным способом"
    except Exception as e:
        raise RuntimeError(f"Ошибка перезапуска: {str(e)}")


def remove_bot(name: str, force: bool = False):
    container = get_client().containers.get(name)
    container.remove(force=force)
    return True


def remove_workspace(name: str, delete_files: bool = False):
    """
    Удалить workspace контейнер и опционально файлы
    
    Args:
        name: имя workspace (оригинальное или docker-нормализованное)
        delete_files: удалить ли файлы workspace с диска
    """
    cli = get_client()
    
    # Получаем нормализованное имя для Docker
    docker_name = normalize_docker_name(name)
    
    try:
        # Пробуем найти контейнер по нормализованному имени
        container = cli.containers.get(docker_name)
    except:
        try:
            # Если не найден, пробуем по оригинальному имени
            container = cli.containers.get(name)
            docker_name = name
        except:
            raise ValueError(f'Контейнер "{name}" не найден')
    
    # Останавливаем и удаляем контейнер
    try:
        container.stop()
    except:
        pass  # Контейнер может быть уже остановлен
    
    container.remove(force=True)
    
    # Удаляем файлы если запрошено
    if delete_files:
        workspace_dir = os.path.join(cfg.BOTS_DIR, name)
        if os.path.exists(workspace_dir):
            shutil.rmtree(workspace_dir)
            return f'Workspace "{name}" и все файлы удалены'
    
    return f'Workspace контейнер "{name}" удален (файлы сохранены)'


def get_workspace_info(name: str):
    """Получить информацию о workspace"""
    workspace_dir = os.path.join(cfg.BOTS_DIR, name)
    docker_name = normalize_docker_name(name)
    
    info = {
        'name': name,
        'docker_name': docker_name,
        'directory': workspace_dir,
        'exists_on_disk': os.path.exists(workspace_dir),
        'container_exists': False,
        'container_status': None,
        'files_count': 0,
        'directory_size': 0
    }
    
    # Проверяем контейнер
    cli = get_client()
    try:
        container = cli.containers.get(docker_name)
        info['container_exists'] = True
        info['container_status'] = container.status
    except:
        try:
            container = cli.containers.get(name)
            info['container_exists'] = True
            info['container_status'] = container.status
        except:
            pass
    
    # Считаем файлы и размер
    if info['exists_on_disk']:
        try:
            for root, dirs, files in os.walk(workspace_dir):
                info['files_count'] += len(files)
                for file in files:
                    file_path = os.path.join(root, file)
                    if os.path.exists(file_path):
                        info['directory_size'] += os.path.getsize(file_path)
        except:
            pass
    
    return info


def create_bot_from_repo(git_url: str, bot_name: Optional[str] = None, branch: Optional[str] = None):
    # Получаем исходное имя бота
    if not bot_name:
        bot_name = os.path.splitext(os.path.basename(git_url.rstrip('/')))[0]
    
    # Создаем директорию с исходным именем (для файловой системы)
    bot_dir = os.path.join(cfg.BOTS_DIR, bot_name)
    if os.path.exists(bot_dir):
        raise ValueError('Каталог бота уже существует')

    # Но для Docker используем нормализованные имена
    docker_bot_name = normalize_docker_name(bot_name)
    docker_image_tag = f'bot-{docker_bot_name}'

    tmp_dir = tempfile.mkdtemp()
    try:
        Repo.clone_from(git_url, tmp_dir, depth=cfg.GIT_CLONE_DEPTH, branch=branch)
        shutil.copytree(tmp_dir, bot_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    dockerfile_path = os.path.join(bot_dir, 'Dockerfile')
    cli = get_client()
    
    if os.path.exists(dockerfile_path):
        cli.images.build(path=bot_dir, tag=docker_image_tag)
    else:
        base_bot_dockerfile = os.path.join(os.path.dirname(__file__), 'Dockerfile.bot')
        cli.images.build(path=os.path.dirname(base_bot_dockerfile), dockerfile=base_bot_dockerfile, 
                        tag=docker_image_tag, buildargs={'BOT_NAME': bot_name})

    container = cli.containers.run(
        docker_image_tag,
        name=docker_bot_name,
        labels={'bot-manager': '1'},
        detach=True,
        network=cfg.DOCKER_BASE_NETWORK,
        volumes={bot_dir: {'bind': '/app', 'mode': 'rw'}},
        tty=True,
        stdin_open=True,
    )
    return container.id[:12]


def ensure_network():
    try:
        cli = get_client()
        networks = cli.networks.list(names=[cfg.DOCKER_BASE_NETWORK])
        if not networks:
            cli.networks.create(cfg.DOCKER_BASE_NETWORK, driver='bridge')
    except Exception:
        # Не валим старт приложения если docker недоступен
        pass


def create_workspace(workspace_name: str, base_image: str = None, port_mappings: Dict[str, int] = None):
    """Создать workspace для бота с базовым образом"""
    if not workspace_name:
        raise ValueError('Имя workspace обязательно')
    
    # Создаем директорию с исходным именем (для файловой системы)
    workspace_dir = os.path.join(cfg.BOTS_DIR, workspace_name)
    if os.path.exists(workspace_dir):
        raise ValueError('Каталог workspace уже существует')
    
    # Но для Docker используем нормализованное имя
    docker_workspace_name = normalize_docker_name(workspace_name)
    
    os.makedirs(workspace_dir)
    
    # Создаём базовые файлы
    with open(os.path.join(workspace_dir, 'requirements.txt'), 'w') as f:
        f.write('# Добавьте зависимости здесь\n')
    
    with open(os.path.join(workspace_dir, 'main.py'), 'w') as f:
        f.write('# Основной файл бота\nprint("Hello from bot workspace!")\n')
    
    with open(os.path.join(workspace_dir, 'README.md'), 'w') as f:
        f.write(f'# {workspace_name}\n\nОписание бота...\n')
    
    # Создаём контейнер
    cli = get_client()
    image_name = base_image or cfg.BOT_DEFAULT_IMAGE
    
    ports = {}
    if port_mappings:
        for internal_port, external_port in port_mappings.items():
            ports[f'{internal_port}/tcp'] = external_port
    
    container = cli.containers.run(
        image_name,
        name=docker_workspace_name,
        labels={'bot-manager': '1', 'workspace': '1'},
        detach=True,
        network=cfg.DOCKER_BASE_NETWORK,
        volumes={workspace_dir: {'bind': '/workspace', 'mode': 'rw'}},
        ports=ports,
        tty=True,
        stdin_open=True,
        working_dir='/workspace',
        command='sleep infinity'  # Держим контейнер живым
    )
    
    return container.id[:12]


def list_workspaces() -> List[Dict]:
    """Получить список workspace'ов"""
    try:
        containers = get_client().containers.list(all=True)
    except Exception as e:
        return [{'id': '-', 'name': 'ERROR', 'status': f'docker err: {e}', 'image': '-', 'created': '-'}]
    
    data = []
    for c in containers:
        workspace_dir = os.path.join(cfg.BOTS_DIR, c.name)
        has_files = os.path.exists(workspace_dir)
        data.append({
            'id': c.id[:12],
            'name': c.name,
            'status': c.status,
            'image': c.image.tags[0] if c.image.tags else c.image.short_id,
            'created': c.attrs.get('Created'),
            'has_workspace': has_files,
            'workspace_path': workspace_dir if has_files else None
        })
    return data


def get_available_images() -> List[str]:
    """Получить список доступных Docker образов"""
    try:
        cli = get_client()
        images = cli.images.list()
        image_names = []
        for img in images:
            if img.tags:
                image_names.extend(img.tags)
            else:
                image_names.append(img.short_id)
        
        # Добавляем популярные образы
        popular_images = [
            # Python окружения
            'python:3.11-slim',
            'python:3.12-slim', 
            'python:3.13-slim',
            'python:3.11-alpine',
            'jupyter/base-notebook',
            'jupyter/scipy-notebook',
            
            # Node.js окружения
            'node:18-alpine',
            'node:20-alpine',
            'node:22-alpine',
            'node:18-slim',
            
            # Веб-разработка
            'nginx:alpine',
            'nginx:latest',
            'httpd:alpine',
            'php:8.2-apache',
            'php:8.3-fpm-alpine',
            
            # Базовые системы
            'ubuntu:22.04',
            'ubuntu:24.04', 
            'debian:bookworm-slim',
            'alpine:latest',
            'centos:stream9',
            
            # Базы данных
            'postgres:15-alpine',
            'postgres:16-alpine',
            'mysql:8.0',
            'redis:alpine',
            'mongodb:latest',
            
            # DevOps и инструменты
            'golang:1.21-alpine',
            'golang:1.22-alpine',
            'rust:alpine',
            'openjdk:17-alpine',
            'openjdk:21-alpine',
            
            # Data Science
            'tensorflow/tensorflow:latest',
            'pytorch/pytorch:latest',
            'continuumio/miniconda3'
        ]
        
        return list(set(image_names + popular_images))
    except Exception:
        return ['python:3.11-slim', 'ubuntu:22.04', 'alpine:latest']


def get_workspace_templates():
    """Получить список шаблонов workspace с предустановками"""
    return {
        'python-bot': {
            'name': 'Python Bot Development',
            'image': 'python:3.12-slim',
            'description': 'Готовое окружение для разработки ботов на Python',
            'packages': ['pip install flask flask-socketio requests python-telegram-bot discord.py'],
            'setup_commands': [
                'apt-get update && apt-get install -y git curl nano vim',
                'mkdir -p /workspace/src /workspace/logs /workspace/config',
                'echo "# Bot Development Workspace" > /workspace/README.md'
            ]
        },
        'web-fullstack': {
            'name': 'Full-Stack Web Development',
            'image': 'node:20-alpine',
            'description': 'Node.js + Python + базы данных',
            'packages': ['npm install -g express react vue @angular/cli'],
            'setup_commands': [
                'apk add --no-cache python3 py3-pip git curl nano',
                'mkdir -p /workspace/{frontend,backend,database}',
                'npm init -y'
            ]
        },
        'data-science': {
            'name': 'Data Science & ML',
            'image': 'jupyter/scipy-notebook',
            'description': 'Jupyter + pandas + sklearn + tensorflow',
            'packages': ['pip install pandas numpy matplotlib seaborn scikit-learn tensorflow'],
            'setup_commands': [
                'mkdir -p /workspace/{data,notebooks,models,scripts}',
                'jupyter notebook --generate-config'
            ]
        },
        'devops': {
            'name': 'DevOps Tools',
            'image': 'alpine:latest',
            'description': 'Docker + git + инструменты CI/CD',
            'packages': [],
            'setup_commands': [
                'apk add --no-cache git curl wget bash vim nano docker-cli',
                'mkdir -p /workspace/{scripts,configs,deployments}',
                'echo "DevOps Workspace ready" > /workspace/status.txt'
            ]
        }
    }


def create_workspace_from_template(template_key: str, workspace_name: str, port_mappings=None):
    """Создать workspace из шаблона с предустановками"""
    templates = get_workspace_templates()
    if template_key not in templates:
        raise ValueError(f"Неизвестный шаблон: {template_key}")
    
    template = templates[template_key]
    
    # Создаем базовый workspace
    container_id = create_workspace(
        workspace_name=workspace_name,
        base_image=template['image'],
        port_mappings=port_mappings
    )
    
    try:
        cli = get_client()
        container = cli.containers.get(container_id)
        
        # Выполняем команды настройки
        for cmd in template['setup_commands']:
            try:
                result = container.exec_run(cmd, workdir='/workspace')
                print(f"Setup command result: {result.output.decode()}")
            except Exception as e:
                print(f"Setup command failed: {e}")
        
        # Устанавливаем пакеты
        for package_cmd in template['packages']:
            try:
                result = container.exec_run(package_cmd, workdir='/workspace')
                print(f"Package install result: {result.output.decode()}")
            except Exception as e:
                print(f"Package install failed: {e}")
                
        return container_id
        
    except Exception as e:
        print(f"Template setup failed: {e}")
        return container_id  # Возвращаем базовый workspace


def exec_command(container_name: str, cmd: str):
    container = get_client().containers.get(container_name)
    exec_id = get_client().api.exec_create(container.id, cmd, tty=True, stdin=True)
    return exec_id['Id']


def get_bot_logs(name: str, tail: int = 100) -> str:
    """Получить логи контейнера"""
    try:
        container = get_client().containers.get(name)
        logs = container.logs(tail=tail, timestamps=True)
        return logs.decode('utf-8', errors='replace')
    except Exception as e:
        return f"Ошибка получения логов: {str(e)}"


def get_bot_info(name: str) -> Dict:
    """Получить детальную информацию о контейнере"""
    try:
        container = get_client().containers.get(name)
        attrs = container.attrs
        
        info = {
            'id': container.id,
            'name': container.name,
            'status': container.status,
            'image': container.image.tags[0] if container.image.tags else container.image.short_id,
            'created': attrs.get('Created'),
            'ports': attrs.get('NetworkSettings', {}).get('Ports', {}),
            'volumes': attrs.get('Mounts', []),
            'labels': attrs.get('Config', {}).get('Labels', {}),
            'command': attrs.get('Config', {}).get('Cmd'),
            'working_dir': attrs.get('Config', {}).get('WorkingDir'),
            'env_vars': len(attrs.get('Config', {}).get('Env', [])),
            'restart_policy': attrs.get('HostConfig', {}).get('RestartPolicy', {}).get('Name'),
            'network_mode': attrs.get('HostConfig', {}).get('NetworkMode'),
        }
        
        # Добавляем статистику использования ресурсов
        try:
            stats = container.stats(stream=False)
            if stats:
                cpu_stats = stats.get('cpu_stats', {})
                precpu_stats = stats.get('precpu_stats', {})
                memory_stats = stats.get('memory_stats', {})
                
                if cpu_stats and precpu_stats:
                    cpu_delta = cpu_stats.get('cpu_usage', {}).get('total_usage', 0) - precpu_stats.get('cpu_usage', {}).get('total_usage', 0)
                    system_delta = cpu_stats.get('system_cpu_usage', 0) - precpu_stats.get('system_cpu_usage', 0)
                    if system_delta > 0:
                        info['cpu_percent'] = round((cpu_delta / system_delta) * 100, 2)
                
                if memory_stats:
                    info['memory_usage'] = memory_stats.get('usage', 0)
                    info['memory_limit'] = memory_stats.get('limit', 0)
                    if info['memory_limit'] > 0:
                        info['memory_percent'] = round((info['memory_usage'] / info['memory_limit']) * 100, 2)
        except:
            pass
        
        return info
    except Exception as e:
        return {'error': str(e)}
