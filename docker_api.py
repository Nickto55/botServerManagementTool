import os
import shutil
import tempfile
import subprocess
from datetime import datetime
from typing import List, Dict, Optional

import docker
from git import Repo

from config import cfg

client = docker.from_env()


def list_bots() -> List[Dict]:
    containers = client.containers.list(all=True, filters={'label': 'bot-manager=1'})
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
    container = client.containers.get(name)
    container.start()
    return True


def stop_bot(name: str):
    container = client.containers.get(name)
    container.stop()
    return True


def restart_bot(name: str):
    container = client.containers.get(name)
    container.restart()
    return True


def remove_bot(name: str, force: bool = False):
    container = client.containers.get(name)
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

    # Build image (if Dockerfile present) else use default image and mount source
    dockerfile_path = os.path.join(bot_dir, 'Dockerfile')
    image_tag = f'bot_{bot_name}:latest'
    if os.path.exists(dockerfile_path):
        client.images.build(path=bot_dir, tag=image_tag)
    else:
        # Build from generic bot Dockerfile template
        base_bot_dockerfile = os.path.join(os.path.dirname(__file__), 'Dockerfile.bot')
        client.images.build(path=os.path.dirname(base_bot_dockerfile), dockerfile=base_bot_dockerfile, tag=image_tag, buildargs={'BOT_NAME': bot_name})

    container = client.containers.run(
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
    networks = client.networks.list(names=[cfg.DOCKER_BASE_NETWORK])
    if not networks:
        client.networks.create(cfg.DOCKER_BASE_NETWORK, driver='bridge')


# Exec command inside container (for terminal)
def exec_command(container_name: str, cmd: str):
    container = client.containers.get(container_name)
    exec_id = client.api.exec_create(container.id, cmd, tty=True, stdin=True)
    return exec_id['Id']
