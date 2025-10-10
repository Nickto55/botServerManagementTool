import subprocess
import threading
import time
from datetime import datetime
from typing import Dict, List
from flask_socketio import emit
import docker
from docker.errors import DockerException, NotFound as DockerNotFound
from exec_backend import get_backend

TERMINAL_SESSIONS: Dict[str, dict] = {}

# Максимум команд в истории (per session)
MAX_HISTORY = 200


def _now_iso():
    return datetime.utcnow().isoformat() + 'Z'


def start_terminal_session(sid: str, container_name: str):
    """Инициализация сессии терминала с хранением истории команд."""
    try:
        print(f"[terminal] start session sid={sid} container={container_name}")

        TERMINAL_SESSIONS[sid] = {
            'container': container_name,
            'active': True,
            'history': [],  # List[dict]
            'lock': threading.Lock(),
            'docker_ok': False,
            'container_status': 'unknown'
        }

        emit('terminal_output', {'data': f'=== Подключение к {container_name} ===\n'})
        emit('terminal_output', {'data': 'Проверка Docker окружения...\n'})

        # Проверка Docker
        docker_status = {
            'docker': 'down',
            'container': 'absent',
            'container_running': False,
            'image': None
        }
        try:
            cli = docker.from_env()
            cli.ping()
            docker_status['docker'] = 'up'
            try:
                container = cli.containers.get(container_name)
                docker_status['container'] = 'present'
                docker_status['container_running'] = container.status == 'running'
                docker_status['image'] = container.image.tags[0] if container.image.tags else container.image.short_id
                TERMINAL_SESSIONS[sid]['container_status'] = container.status
            except DockerNotFound:
                docker_status['container'] = 'missing'
        except DockerException as de:
            docker_status['error'] = str(de)

        if docker_status['docker'] == 'up':
            emit('terminal_output', {'data': 'Docker: OK\n'})
            TERMINAL_SESSIONS[sid]['docker_ok'] = True
        else:
            emit('terminal_output', {'data': 'Docker: НЕ ДОСТУПЕН\n'})

        if docker_status['container'] == 'present':
            if docker_status['container_running']:
                emit('terminal_output', {'data': f'Контейнер: запущен (image={docker_status["image"]})\n'})
            else:
                emit('terminal_output', {'data': 'Контейнер: найден, но НЕ запущен. Используйте :start для запуска.\n'})
        elif docker_status['container'] == 'missing':
            emit('terminal_output', {'data': 'Контейнер: не найден\n'})
        else:
            emit('terminal_output', {'data': 'Контейнер: неизвестно\n'})

        emit('terminal_status', docker_status)
        emit('terminal_output', {'data': 'Доступные спецкоманды: :history, :clear, :start (запустить контейнер если остановлен)\n'})
        emit('terminal_output', {'data': f'root@{container_name}:~$ '})
        emit('terminal_history_full', {'history': []})

    except Exception as e:
        print(f"[terminal] start error: {e}")
        emit('terminal_output', {'data': f'Ошибка запуска терминала: {e}\n'})


def _append_history(sid: str, entry: dict):
    sess = TERMINAL_SESSIONS.get(sid)
    if not sess:
        return
    with sess['lock']:
        sess['history'].append(entry)
        # Обрезаем при превышении
        if len(sess['history']) > MAX_HISTORY:
            sess['history'] = sess['history'][-MAX_HISTORY:]


def _update_history_last(sid: str, **updates):
    sess = TERMINAL_SESSIONS.get(sid)
    if not sess:
        return
    with sess['lock']:
        if not sess['history']:
            return
        sess['history'][-1].update(**updates)
        return sess['history'][-1]


def handle_terminal_input(sid: str, data: str):
    """Обработка ввода пользователя с сохранением истории команд."""
    try:
        sess = TERMINAL_SESSIONS.get(sid)
        if not sess:
            emit('terminal_output', {'data': 'Сессия не найдена. Обновите страницу.\n'})
            return

        container_name = sess['container']
        raw = data if isinstance(data, str) else (data.get('data') if isinstance(data, dict) else '')
        command = (raw or '').strip()

        if not command:
            emit('terminal_output', {'data': f'root@{container_name}:~$ '})
            return

        # Специальные локальные команды
        if command == ':history':
            hist_copy: List[dict] = []
            with sess['lock']:
                for h in sess['history']:
                    hist_copy.append({k: h.get(k) for k in ['id','command','exit_code','started_at','finished_at']})
            emit('terminal_output', {'data': '\nИстория команд (последние):\n'})
            for h in hist_copy:
                emit('terminal_output', {'data': f"[{h['id']}] {h['command']} (exit={h.get('exit_code')})\n"})
            emit('terminal_output', {'data': f'\nroot@{container_name}:~$ '})
            return
        if command == ':clear':
            emit('terminal_clear', {})
            emit('terminal_output', {'data': f'root@{container_name}:~$ '})
            return
        if command == ':start':
            # Попытка запуска контейнера если он существует и не запущен
            try:
                cli = docker.from_env()
                container = cli.containers.get(container_name)
                if container.status != 'running':
                    container.start()
                    emit('terminal_output', {'data': 'Контейнер запускается...\n'})
                    time.sleep(1)
                    container.reload()
                    emit('terminal_output', {'data': f'Статус: {container.status}\n'})
                else:
                    emit('terminal_output', {'data': 'Контейнер уже запущен\n'})
            except DockerNotFound:
                emit('terminal_output', {'data': 'Невозможно запустить: контейнер не найден\n'})
            except DockerException as de:
                emit('terminal_output', {'data': f'Ошибка Docker: {de}\n'})
            except Exception as e:
                emit('terminal_output', {'data': f'Ошибка запуска: {e}\n'})
            emit('terminal_output', {'data': f'root@{container_name}:~$ '})
            return

        cmd_id = int(time.time() * 1000)  # простой уникальный id
        entry = {
            'id': cmd_id,
            'command': command,
            'stdout': '',
            'stderr': '',
            'exit_code': None,
            'started_at': _now_iso(),
            'finished_at': None,
            'duration_ms': None
        }
        _append_history(sid, entry)

        # Сразу отправляем событие о новой команде
        emit('terminal_command_started', {'id': cmd_id, 'command': command, 'started_at': entry['started_at']})
        # Отображаем в основном выводе
        emit('terminal_output', {'data': f"{command}\n"})

        def run_command():
            started = time.time()
            try:
                backend = get_backend()
                # Если команда не начинается с docker, явно оборачиваем для exec в контейнере
                if command.startswith('docker '):
                    exec_cmd = command
                else:
                    exec_cmd = f"docker exec {container_name} bash -lc {command!r}"
                stdout, stderr, exit_code = backend.run(exec_cmd, timeout=30)
            except Exception as e:
                stdout = ''
                stderr = f'Ошибка выполнения: {e}\n'
                exit_code = 1

            finished = time.time()
            updated = _update_history_last(
                sid,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                finished_at=_now_iso(),
                duration_ms=int((finished - started) * 1000)
            )

            # Отправляем структурированный результат
            emit('terminal_command_result', {
                'id': updated['id'],
                'command': updated['command'],
                'stdout': stdout,
                'stderr': stderr,
                'exit_code': exit_code,
                'started_at': updated['started_at'],
                'finished_at': updated['finished_at'],
                'duration_ms': updated['duration_ms']
            })

            # Также выводим в обычный поток
            if stdout:
                emit('terminal_output', {'data': stdout})
            if stderr:
                emit('terminal_output', {'data': f'! {stderr}'})
            emit('terminal_output', {'data': f'root@{container_name}:~$ '})

        # Запускаем в отдельном потоке чтобы не блокировать SocketIO
        threading.Thread(target=run_command, daemon=True).start()

    except Exception as e:
        print(f"[terminal] input error: {e}")
        emit('terminal_output', {'data': f'Ошибка обработки команды: {e}\n'})
        emit('terminal_output', {'data': f'root@{container_name}:~$ '})


def close_session(sid: str):
    sess = TERMINAL_SESSIONS.pop(sid, None)
    if sess:
        print(f"[terminal] close session sid={sid} container={sess.get('container')}")


def get_session_history_for_container(container_name: str):
    """Вернуть историю для первого активного sid указанного контейнера."""
    for sid, sess in TERMINAL_SESSIONS.items():
        if sess.get('container') == container_name:
            with sess['lock']:
                return sess['history'][:]
    return []


# Глобальные переменные для консоли сервера
SERVER_CONSOLE_SESSIONS: Dict[str, dict] = {}
SERVER_CONSOLE_MAX_HISTORY = 200


def start_server_console_session(sid: str):
    """Инициализация сессии консоли сервера."""
    try:
        print(f"[server_console] start session sid={sid}")

        SERVER_CONSOLE_SESSIONS[sid] = {
            'active': True,
            'history': [],
            'lock': threading.Lock()
        }

        emit('server_console_output', {'data': '=== Консоль сервера ===\n'})
        emit('server_console_output', {'data': 'Подключение к хост-системе...\n'})
        emit('server_console_output', {'data': 'Сервер готов к выполнению команд.\n\n'})
        emit('server_console_output', {'data': 'root@server:~$ '})

    except Exception as e:
        print(f"[server_console] start error: {e}")
        emit('server_console_output', {'data': f'Ошибка запуска консоли сервера: {e}\n'})


def handle_server_console_input(sid: str, data: str):
    """Обработка ввода пользователя в консоли сервера."""
    try:
        sess = SERVER_CONSOLE_SESSIONS.get(sid)
        if not sess:
            emit('server_console_output', {'data': 'Сессия консоли сервера не найдена. Обновите страницу.\n'})
            return

        raw = data if isinstance(data, str) else (data.get('data') if isinstance(data, dict) else '')
        command = (raw or '').strip()

        if not command:
            emit('server_console_output', {'data': 'root@server:~$ '})
            return

        # Специальные команды
        if command == ':history':
            hist_copy = []
            with sess['lock']:
                for h in sess['history']:
                    hist_copy.append({k: h.get(k) for k in ['id','command','exit_code','started_at','finished_at']})
            emit('server_console_output', {'data': '\nИстория команд (последние):\n'})
            for h in hist_copy:
                emit('server_console_output', {'data': f"[{h['id']}] {h['command']} (exit={h.get('exit_code')})\n"})
            emit('server_console_output', {'data': 'root@server:~$ '})
            return
        elif command == ':clear':
            emit('server_console_clear', {})
            emit('server_console_output', {'data': 'root@server:~$ '})
            return

        cmd_id = int(time.time() * 1000)
        entry = {
            'id': cmd_id,
            'command': command,
            'stdout': '',
            'stderr': '',
            'exit_code': None,
            'started_at': _now_iso(),
            'finished_at': None,
            'duration_ms': None
        }

        with sess['lock']:
            sess['history'].append(entry)
            if len(sess['history']) > SERVER_CONSOLE_MAX_HISTORY:
                sess['history'] = sess['history'][-SERVER_CONSOLE_MAX_HISTORY:]

        emit('server_console_command_started', {'id': cmd_id, 'command': command})
        emit('server_console_output', {'data': f"{command}\n"})

        def run_server_command():
            started = time.time()
            try:
                backend = get_backend()
                stdout, stderr, exit_code = backend.run(command, timeout=30)
            except Exception as e:
                stdout = ''
                stderr = f'Ошибка выполнения: {e}\n'
                exit_code = 1

            finished = time.time()
            duration_ms = int((finished - started) * 1000)

            # Обновляем запись в истории
            with sess['lock']:
                for h in sess['history']:
                    if h['id'] == cmd_id:
                        h.update({
                            'stdout': stdout,
                            'stderr': stderr,
                            'exit_code': exit_code,
                            'finished_at': _now_iso(),
                            'duration_ms': duration_ms
                        })
                        break

            emit('server_console_command_result', {
                'id': cmd_id,
                'command': command,
                'stdout': stdout,
                'stderr': stderr,
                'exit_code': exit_code,
                'started_at': entry['started_at'],
                'finished_at': _now_iso(),
                'duration_ms': duration_ms
            })

            if stdout:
                emit('server_console_output', {'data': stdout})
            if stderr:
                emit('server_console_output', {'data': f'! {stderr}'})
            emit('server_console_output', {'data': 'root@server:~$ '})

        threading.Thread(target=run_server_command, daemon=True).start()

    except Exception as e:
        print(f"[server_console] input error: {e}")
        emit('server_console_output', {'data': f'Ошибка обработки команды: {e}\n'})
        emit('server_console_output', {'data': 'root@server:~$ '})


def close_server_console_session(sid: str):
    """Закрытие сессии консоли сервера."""
    sess = SERVER_CONSOLE_SESSIONS.pop(sid, None)
    if sess:
        print(f"[server_console] close session sid={sid}")
