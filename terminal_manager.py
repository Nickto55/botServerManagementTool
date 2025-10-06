import threading
import docker
import json
from typing import Dict
from flask_socketio import emit, join_room, leave_room
from docker.models.containers import Container
from docker.utils.socket import frames_iter
from docker import errors as docker_errors

from docker_api import client

TERMINAL_SESSIONS: Dict[str, dict] = {}


def open_exec_socket(container: Container, cmd: str = '/bin/bash'):
    exec_id = client.api.exec_create(container.id, cmd, tty=True, stdin=True)
    sock = client.api.exec_start(exec_id, tty=True, socket=True)
    return exec_id, sock


def start_terminal_session(sid: str, container_name: str):
    try:
        container = client.containers.get(container_name)
    except docker_errors.NotFound:
        emit('terminal_output', {'data': f'Контейнер {container_name} не найден\n'}, room=sid)
        return

    exec_id, sock = open_exec_socket(container)
    TERMINAL_SESSIONS[sid] = {'exec_id': exec_id, 'socket': sock, 'container': container}

    def reader():
        try:
            for frame in frames_iter(sock._sock):  # noqa
                if sid not in TERMINAL_SESSIONS:
                    break
                if frame:
                    emit('terminal_output', {'data': frame.decode(errors='ignore')}, room=sid)
        finally:
            sock.close()
            TERMINAL_SESSIONS.pop(sid, None)

    t = threading.Thread(target=reader, daemon=True)
    t.start()


def handle_terminal_input(sid: str, data: str):
    sess = TERMINAL_SESSIONS.get(sid)
    if not sess:
        emit('terminal_output', {'data': 'Сессия не найдена\n'}, room=sid)
        return
    try:
        sess['socket'].send(data.encode())
    except Exception as e:
        emit('terminal_output', {'data': f'Ошибка отправки: {e}\n'}, room=sid)


def close_session(sid: str):
    sess = TERMINAL_SESSIONS.pop(sid, None)
    if sess:
        try:
            sess['socket'].close()
        except Exception:
            pass
