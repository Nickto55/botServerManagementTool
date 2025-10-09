import os
import subprocess
import threading
from dataclasses import dataclass
from typing import Optional, Tuple, Protocol

try:
    import paramiko  # type: ignore
except ImportError:  # graceful degradation
    paramiko = None


class ExecError(Exception):
    pass


class IExecBackend(Protocol):
    def run(self, command: str, timeout: int = 30) -> Tuple[str, str, int]:
        ...


@dataclass
class LocalBackend:
    shell: str = '/bin/bash'

    def run(self, command: str, timeout: int = 30) -> Tuple[str, str, int]:
        try:
            result = subprocess.run(
                [self.shell, '-lc', command],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.stdout or '', result.stderr or '', result.returncode
        except subprocess.TimeoutExpired:
            return '', 'Timeout ({}s)'.format(timeout), 124
        except Exception as e:
            return '', f'Local exec error: {e}', 1


@dataclass
class SSHBackend:
    host: str
    user: str
    key_path: str
    port: int = 22

    def _get_client(self):
        if not paramiko:
            raise ExecError('Paramiko not installed')
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.host,
            username=self.user,
            key_filename=self.key_path,
            port=self.port,
            look_for_keys=False,
            allow_agent=True,
            timeout=10
        )
        return client

    def run(self, command: str, timeout: int = 30) -> Tuple[str, str, int]:
        client = None
        try:
            client = self._get_client()
            transport = client.get_transport()
            if not transport:
                return '', 'SSH transport unavailable', 1
            channel = transport.open_session()
            channel.exec_command(command)

            stdout_chunks = []
            stderr_chunks = []

            def reader(stdout=True):
                src = channel.makefile('r') if stdout else channel.makefile_stderr('r')
                target = stdout_chunks if stdout else stderr_chunks
                for line in src:
                    target.append(line)

            t_out = threading.Thread(target=reader, args=(True,), daemon=True)
            t_err = threading.Thread(target=reader, args=(False,), daemon=True)
            t_out.start(); t_err.start()
            channel.settimeout(timeout)

            channel.recv_exit_status()  # wait
            t_out.join(timeout=1)
            t_err.join(timeout=1)

            exit_code = channel.recv_exit_status()
            return ''.join(stdout_chunks), ''.join(stderr_chunks), exit_code
        except Exception as e:
            return '', f'SSH exec error: {e}', 1
        finally:
            if client:
                client.close()


_backend_singleton: Optional[IExecBackend] = None


def get_backend():
    global _backend_singleton
    if _backend_singleton:
        return _backend_singleton

    mode = os.getenv('EXEC_MODE', 'local').lower()
    if mode == 'ssh':
        host = os.getenv('SSH_HOST', '127.0.0.1')
        user = os.getenv('SSH_USER', 'botops')
        key_path = os.getenv('SSH_KEY_PATH', '/home/botops/.ssh/id_rsa')
        _backend_singleton = SSHBackend(host=host, user=user, key_path=key_path)
    else:
        _backend_singleton = LocalBackend()
    return _backend_singleton
