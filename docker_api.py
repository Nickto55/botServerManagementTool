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
        containers = get_client().containers.list(all=True, filters={'label': 'bot-manager=1'})
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
    container = get_client().containers.get(name)
    container.start()
    return True


def stop_bot(name: str):
    container = get_client().containers.get(name)
    container.stop()
    return True


def restart_bot(name: str):
    container = get_client().containers.get(name)
    container.restart()
    return True


def remove_bot(name: str, force: bool = False):
    container = get_client().containers.get(name)
    container.remove(force=force)
    return True


def create_bot_from_repo(git_url: str, bot_name: Optional[str] = None, branch: Optional[str] = None):
    if not bot_name:
        bot_name = os.path.splitext(os.path.basename(git_url.rstrip('/')))[0]
    bot_dir = os.path.join(cfg.BOTS_DIR, bot_name)
    if os.path.exists(bot_dir):
        raise ValueError('Каталог бота уже существует')

    tmp_dir = tempfile.mkdtemp()
    try:
        Repo.clone_from(git_url, tmp_dir, depth=cfg.GIT_CLONE_DEPTH, branch=branch)
        shutil.copytree(tmp_dir, bot_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    dockerfile_path = os.path.join(bot_dir, 'Dockerfile')
    image_tag = f'bot_{bot_name}:latest'
    cli = get_client()
    if os.path.exists(dockerfile_path):
        cli.images.build(path=bot_dir, tag=image_tag)
    else:
        base_bot_dockerfile = os.path.join(os.path.dirname(__file__), 'Dockerfile.bot')
        cli.images.build(path=os.path.dirname(base_bot_dockerfile), dockerfile=base_bot_dockerfile, tag=image_tag, buildargs={'BOT_NAME': bot_name})

    container = cli.containers.run(
        image_tag,
        name=bot_name,
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
    
    workspace_dir = os.path.join(cfg.BOTS_DIR, workspace_name)
    if os.path.exists(workspace_dir):
        raise ValueError('Каталог workspace уже существует')
    
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
        name=workspace_name,
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
        containers = get_client().containers.list(all=True, filters={'label': ['bot-manager=1', 'workspace=1']})
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
