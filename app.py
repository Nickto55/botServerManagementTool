from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify, session, flash
from flask_socketio import SocketIO, emit, emit
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import logging
from werkzeug.utils import secure_filename
import validators

from config import cfg
from auth import bp_auth, login_required, init_db, ensure_admin, get_bot_commands, save_bot_commands, BotCommands

app = Flask(__name__)
app.config.from_object('config.Config')
app.register_blueprint(bp_auth)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Импортируем Docker API с обработкой ошибок
try:
    from docker_api import list_bots, start_bot, stop_bot, restart_bot, remove_bot, create_bot_from_repo, ensure_network, create_workspace, list_workspaces, get_available_images, get_bot_logs, get_bot_info, get_client
    DOCKER_AVAILABLE = True
except Exception as e:
    logger.warning(f'Docker API недоступно: {e}')
    DOCKER_AVAILABLE = False
    # Создаем заглушки для Docker функций
    def list_bots(): return [{'id': '-', 'name': 'Docker недоступен', 'status': 'error', 'image': '-', 'created': '-'}]
    def start_bot(name): raise RuntimeError("Docker недоступен")
    def stop_bot(name): raise RuntimeError("Docker недоступен")
    def restart_bot(name): raise RuntimeError("Docker недоступен")
    def remove_bot(name, force=False): raise RuntimeError("Docker недоступен")
    def create_bot_from_repo(*args, **kwargs): raise RuntimeError("Docker недоступен")
    def ensure_network(): pass  # Не падаем, просто пропускаем
    def create_workspace(*args, **kwargs): raise RuntimeError("Docker недоступен")
    def list_workspaces(): return []
    def get_available_images(): return []
    def get_bot_logs(name, tail=100): return "Docker недоступен"
    def get_bot_info(name): return {'error': 'Docker недоступен'}
    def get_client(): raise RuntimeError("Docker недоступен")

try:
    from terminal_manager import start_terminal_session, handle_terminal_input, close_session, start_server_console_session, handle_server_console_input, close_server_console_session
    TERMINAL_AVAILABLE = True
except Exception as e:
    logger.warning(f'Terminal manager недоступен: {e}')
    TERMINAL_AVAILABLE = False
    def start_terminal_session(*args): pass
    def handle_terminal_input(*args): pass
    def close_session(*args): pass
    def start_server_console_session(*args): pass
    def handle_server_console_input(*args): pass
    def close_server_console_session(*args): pass

# Rate limiting
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per hour"]
)
limiter.init_app(app)

socketio = SocketIO(app, async_mode='eventlet')

ALLOWED_FRONTEND_EXT = {'.html', '.css', '.js'}

# Глобальная переменная для отслеживания успешности инициализации
startup_success = False


def startup():
    """Инициализация приложения с обработкой ошибок"""
    errors = []
    
    try:
        logger.info("Инициализация базы данных...")
        init_db()
        logger.info("База данных инициализирована успешно")
    except Exception as e:
        error_msg = f'Ошибка инициализации БД: {e}'
        logger.error(error_msg)
        errors.append(error_msg)
    
    try:
        logger.info("Проверка/создание администратора...")
        ensure_admin()
        logger.info("Администратор настроен успешно")
    except Exception as e:
        error_msg = f'Ошибка настройки администратора: {e}'
        logger.error(error_msg)
        errors.append(error_msg)
    
    try:
        logger.info("Проверка Docker сети...")
        ensure_network()
        logger.info("Docker сеть настроена успешно")
    except Exception as e:
        error_msg = f'Ошибка Docker сети: {e}'
        logger.warning(error_msg)  # Warning, а не Error, так как Docker может быть недоступен
        errors.append(error_msg)
    
    if errors:
        logger.warning(f'Startup завершен с ошибками: {len(errors)} проблем')
        for error in errors:
            logger.warning(f'  - {error}')
    else:
        logger.info('Startup завершен успешно')
    
    return len(errors) == 0


# Вызываем startup при инициализации
startup_success = False
try:
    with app.app_context():
        startup_success = startup()
except Exception as e:
    logger.critical(f'Критическая ошибка при инициализации: {e}')
    # Продолжаем работу, но отмечаем проблему


# Глобальная проверка авторизации
@app.before_request
def require_login():
    """Требовать авторизацию для всех страниц кроме разрешенных"""
    # Список разрешенных endpoints без авторизации
    allowed_endpoints = [
        'login', 'static', 'health'
    ]
    
    # Список разрешенных путей без авторизации
    allowed_paths = [
        '/login', '/static/', '/health', '/socket.io/'
    ]
    
    # Проверяем, нужна ли авторизация
    if request.endpoint in allowed_endpoints:
        return None
        
    for path in allowed_paths:
        if request.path.startswith(path):
            return None
    
    # Если пользователь не авторизован - редирект на логин
    if 'user_id' not in session:
        if request.method == 'POST' or request.is_json:
            # Для API запросов возвращаем JSON ошибку
            return jsonify({
                'status': 'error', 
                'error': 'Требуется авторизация',
                'redirect': url_for('auth.login')
            }), 401
        else:
            # Для обычных запросов - редирект
            return redirect(url_for('auth.login'))


@app.route('/')
def dashboard():
    bots = list_bots()
    workspaces = list_workspaces()
    return render_template('dashboard.html', bots=bots, workspaces=workspaces)


@app.route('/bots/create', methods=['POST'])
@limiter.limit("5 per minute")
def create_bot():
    try:
        data = request.form or request.json or {}
        git_url = data.get('git_url', '').strip()
        bot_name = data.get('bot_name', '').strip()
        branch = data.get('branch', '').strip()
        
        # Валидация входных данных
        if not git_url:
            return jsonify({'status': 'error', 'error': 'Git URL обязателен'}), 400
        
        if not validators.url(git_url) and not git_url.startswith('git@'):
            return jsonify({'status': 'error', 'error': 'Некорректный Git URL'}), 400
        
        if bot_name and len(bot_name) > 50:
            return jsonify({'status': 'error', 'error': 'Имя бота слишком длинное'}), 400
        
        logger.info(f"Создание бота из {git_url}, имя: {bot_name}, ветка: {branch}")
        cid = create_bot_from_repo(git_url, bot_name=bot_name, branch=branch)
        logger.info(f"Бот создан успешно, container_id: {cid}")
        return jsonify({'status': 'ok', 'container_id': cid})
        
    except Exception as e:
        error_msg = f"Ошибка создания бота: {str(e)}"
        logger.error(error_msg)
        return jsonify({'status': 'error', 'error': str(e)}), 400


@app.route('/workspace/create', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def create_workspace_page():
    if request.method == 'POST':
        try:
            data = request.form or request.json or {}
            workspace_name = data.get('workspace_name', '').strip()
            base_image = data.get('base_image', '').strip()
            
            # Валидация входных данных
            if not workspace_name:
                error_msg = 'Имя workspace обязательно'
                if request.content_type and 'application/json' in request.content_type:
                    return jsonify({'status': 'error', 'error': error_msg}), 400
                else:
                    return render_template('create_workspace.html', 
                                         error=error_msg,
                                         available_images=get_available_images())
            
            if len(workspace_name) > 50:
                error_msg = 'Имя workspace слишком длинное'
                if request.content_type and 'application/json' in request.content_type:
                    return jsonify({'status': 'error', 'error': error_msg}), 400
                else:
                    return render_template('create_workspace.html', 
                                         error=error_msg,
                                         available_images=get_available_images())
            
            # Порты (optional)
            port_mappings = {}
            if data.get('port_internal') and data.get('port_external'):
                try:
                    internal_port = int(data.get('port_internal'))
                    external_port = int(data.get('port_external'))
                    if 1 <= internal_port <= 65535 and 1024 <= external_port <= 65535:
                        port_mappings[str(internal_port)] = external_port
                    else:
                        raise ValueError("Неверный диапазон портов")
                except (ValueError, TypeError) as e:
                    error_msg = f'Ошибка настройки портов: {str(e)}'
                    if request.content_type and 'application/json' in request.content_type:
                        return jsonify({'status': 'error', 'error': error_msg}), 400
                    else:
                        return render_template('create_workspace.html', 
                                             error=error_msg,
                                             available_images=get_available_images())
            
            logger.info(f"Создание workspace: {workspace_name}, образ: {base_image}")
            container_id = create_workspace(
                workspace_name=workspace_name,
                base_image=base_image if base_image else None,
                port_mappings=port_mappings if port_mappings else None
            )
            logger.info(f"Workspace создан успешно, container_id: {container_id}")
            
            if request.content_type and 'application/json' in request.content_type:
                return jsonify({'status': 'ok', 'container_id': container_id})
            else:
                return redirect(url_for('dashboard'))
                
        except Exception as e:
            error_msg = f"Ошибка создания workspace: {str(e)}"
            logger.error(error_msg)
            if request.content_type and 'application/json' in request.content_type:
                return jsonify({'status': 'error', 'error': str(e)}), 400
            else:
                return render_template('create_workspace.html', 
                                     error=str(e),
                                     available_images=get_available_images())
    
    return render_template('create_workspace.html', available_images=get_available_images())


@app.route('/bots/<name>/<action>', methods=['POST'])
def bot_action(name, action):
    try:
        result = None
        command_info = None
        
        if action == 'start':
            result = start_bot(name)
        elif action == 'stop':
            result = stop_bot(name)
        elif action == 'restart':
            result = restart_bot(name)
        elif action == 'remove':
            result = remove_bot(name, force=True)
        else:
            return jsonify({'status': 'error', 'error': 'Unknown action'}), 400
        
        response = {'status': 'ok'}
        
        # Если result - это строка с информацией о команде, добавляем её в ответ
        if isinstance(result, str) and 'Выполнена команда:' in result:
            parts = result.split('\nВывод: ', 1)
            command_part = parts[0].replace('Выполнена команда: ', '')
            response['command'] = command_part
            if len(parts) > 1:
                response['output'] = parts[1]
        
        return jsonify(response)
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 400


@app.route('/workspace/<name>/info', methods=['GET'])
def workspace_info(name):
    """Получить информацию о workspace"""
    try:
        from docker_api import get_workspace_info
        info = get_workspace_info(name)
        return jsonify({'status': 'ok', 'info': info})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 400


@app.route('/workspace/<name>/delete', methods=['POST'])
def delete_workspace(name):
    """Удалить workspace"""
    try:
        from docker_api import remove_workspace
        data = request.get_json() or {}
        delete_files = data.get('delete_files', False)
        
        message = remove_workspace(name, delete_files=delete_files)
        return jsonify({'status': 'ok', 'message': message})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 400


@app.route('/terminal/<name>')
def terminal_view(name):
    return render_template('terminal.html', container=name)


@app.route('/server-console')
@login_required
def server_console():
    """Консоль основного сервера для выполнения команд на хост-системе"""
    return render_template('server_console.html')


@app.route('/bot/<name>/commands', methods=['GET', 'POST'])
@login_required
def bot_commands_config(name):
    """Настройка команд для бота"""
    if request.method == 'POST':
        launch_cmd = request.form.get('launch_command', '').strip() or None
        start_cmd = request.form.get('start_command', '').strip() or None
        stop_cmd = request.form.get('stop_command', '').strip() or None 
        restart_cmd = request.form.get('restart_command', '').strip() or None
        
        save_bot_commands(name, start_cmd, stop_cmd, restart_cmd, launch_cmd)
        flash(f'Команды для "{name}" успешно сохранены!', 'success')
        return redirect(url_for('bot_commands_config', name=name))
    
    # Получаем текущие команды и статус контейнера
    commands = get_bot_commands(name)
    container_status = 'unknown'
    
    try:
        from docker_api import get_client
        container = get_client().containers.get(name)
        container_status = container.status
    except Exception:
        pass
    
    return render_template('bot_commands.html', 
                         container_name=name,
                         container_status=container_status,
                         commands=commands or type('obj', (object,), {'launch_command': None, 'start_command': None, 'stop_command': None, 'restart_command': None})())


@app.route('/bot/<name>/reset-commands', methods=['POST'])
@login_required
def reset_bot_commands(name):
    """Сбросить команды бота к стандартным значениям"""
    try:
        commands = BotCommands.get_or_create(name)
        commands.update_commands(start_cmd=None, stop_cmd=None, restart_cmd=None, launch_cmd=None)
        flash(f'Команды для "{name}" сброшены к стандартным значениям!', 'success')
        return redirect(url_for('bot_commands_config', name=name))
    except Exception as e:
        flash(f'Ошибка сброса команд: {str(e)}', 'danger')
        return redirect(url_for('bot_commands_config', name=name))


@app.route('/bots')
@login_required
def bots_management():
    """Страница управления ботами"""
    return render_template('bots.html')


@app.route('/api/bots')
@login_required
def api_bots_list():
    """API для получения списка всех ботов"""
    try:
        # Получаем все контейнеры
        containers = get_client().containers.list(all=True)
        
        all_containers = []
        for c in containers:
            # Определяем тип контейнера по labels
            labels = c.attrs.get('Config', {}).get('Labels', {})
            is_workspace = labels.get('workspace') == '1'
            is_bot_manager = labels.get('bot-manager') == '1'
            
            # Пропускаем контейнеры, не созданные нашим менеджером
            if not is_bot_manager:
                continue
            
            # Определяем тип
            container_type = 'workspace' if is_workspace else 'bot'
            
            # Проверяем наличие файлов для workspace
            has_workspace_files = False
            if is_workspace:
                workspace_dir = os.path.join(cfg.BOTS_DIR, c.name)
                has_workspace_files = os.path.exists(workspace_dir)
            
            container_info = {
                'id': c.id[:12],
                'name': c.name,
                'status': c.status,
                'image': c.image.tags[0] if c.image.tags else c.image.short_id,
                'created': c.attrs.get('Created'),
                'type': container_type,
                'has_workspace': has_workspace_files if is_workspace else False
            }
            
            # Добавляем статистику ресурсов если контейнер запущен
            if c.status == 'running':
                try:
                    stats = c.stats(stream=False)
                    if stats:
                        cpu_stats = stats.get('cpu_stats', {})
                        precpu_stats = stats.get('precpu_stats', {})
                        memory_stats = stats.get('memory_stats', {})
                        
                        if cpu_stats and precpu_stats:
                            cpu_delta = cpu_stats.get('cpu_usage', {}).get('total_usage', 0) - precpu_stats.get('cpu_usage', {}).get('total_usage', 0)
                            system_delta = cpu_stats.get('system_cpu_usage', 0) - precpu_stats.get('system_cpu_usage', 0)
                            if system_delta > 0:
                                container_info['cpu_percent'] = round((cpu_delta / system_delta) * 100, 2)
                        
                        if memory_stats:
                            container_info['memory_usage'] = memory_stats.get('usage', 0)
                            container_info['memory_limit'] = memory_stats.get('limit', 0)
                            if container_info['memory_limit'] > 0:
                                container_info['memory_percent'] = round((container_info['memory_usage'] / container_info['memory_limit']) * 100, 2)
                except:
                    pass
            
            all_containers.append(container_info)
        
        return jsonify({
            'status': 'ok',
            'containers': all_containers
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@app.route('/api/bot/<name>/logs')
@login_required
def api_bot_logs(name):
    """API для получения логов бота"""
    try:
        tail = request.args.get('tail', 100, type=int)
        logs = get_bot_logs(name, tail=tail)
        return jsonify({
            'status': 'ok',
            'logs': logs
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@app.route('/api/bot/<name>/info')
@login_required
def api_bot_info(name):
    """API для получения информации о боте"""
    try:
        info = get_bot_info(name)
        return jsonify({
            'status': 'ok',
            'info': info
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@app.route('/api/bot/<name>/exec', methods=['POST'])
@login_required
def api_bot_exec(name):
    """API для выполнения команды в контейнере"""
    try:
        data = request.get_json()
        command = data.get('command', '').strip()
        
        if not command:
            return jsonify({'status': 'error', 'error': 'Команда не задана'}), 400
        
        # Выполняем команду через exec_backend
        from exec_backend import get_backend
        backend = get_backend()
        
        # Используем docker exec для выполнения команды внутри контейнера
        full_command = f"docker exec {name} {command}"
        stdout, stderr, exit_code = backend.run(full_command)
        
        return jsonify({
            'status': 'ok',
            'exit_code': exit_code,
            'output': stdout,
            'error': stderr
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


# Frontend override upload
@app.route('/upload/frontend', methods=['GET', 'POST'])
def upload_frontend():
    if request.method == 'POST':
        if 'file' not in request.files:
            return 'No file', 400
        f = request.files['file']
        if not f.filename:
            return 'No file selected', 400
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_FRONTEND_EXT:
            return 'Недопустимое расширение', 400
        filename = secure_filename(f.filename)
        dest = os.path.join(cfg.UPLOADS_DIR, filename)
        f.save(dest)
        return redirect(url_for('dashboard'))
    return render_template('upload.html')


# Serve overridden frontend files first
@app.route('/override/<path:filename>')
def overridden_static(filename):
    return send_from_directory(cfg.UPLOADS_DIR, filename)


# SocketIO events
@socketio.on('connect')
def on_connect():
    pass


@socketio.on('terminal_start')
def on_terminal_start(data):
    # Проверяем авторизацию для WebSocket
    if 'user_id' not in session:
        emit('terminal_output', {'data': 'Ошибка: требуется авторизация\n'})
        return
        
    # Поддержка старого и нового ключа
    container = data.get('container') or data.get('container_id')
    print(f"Terminal start requested for container: {container}")
    emit('terminal_output', {'data': f'Подключение к {container}...\n'})
    start_terminal_session(request.sid, container)


@socketio.on('server_console_start')
def on_server_console_start():
    # Проверяем авторизацию для WebSocket
    if 'user_id' not in session:
        emit('server_console_output', {'data': 'Ошибка: требуется авторизация\n'})
        return

    print("Server console start requested")
    start_server_console_session(request.sid)


@socketio.on('terminal_input')
def on_terminal_input(data):
    # Проверяем авторизацию для WebSocket
    if 'user_id' not in session:
        emit('terminal_output', {'data': 'Ошибка: требуется авторизация\n'})
        return
        
    # data может быть строкой или dict
    if isinstance(data, str):
        command = data
    elif isinstance(data, dict):
        command = data.get('data', '')
    else:
        command = ''
    print(f"Terminal input: {repr(command)}")
    handle_terminal_input(request.sid, command)


@socketio.on('server_console_input')
def on_server_console_input(data):
    # Проверяем авторизацию для WebSocket
    if 'user_id' not in session:
        emit('server_console_output', {'data': 'Ошибка: требуется авторизация\n'})
        return

    # data может быть строкой или dict
    if isinstance(data, str):
        command = data
    elif isinstance(data, dict):
        command = data.get('data', '')
    else:
        command = ''
    print(f"Server console input: {repr(command)}")
    handle_server_console_input(request.sid, command)


@socketio.on('disconnect')
def on_disconnect():
    close_session(request.sid)
    close_server_console_session(request.sid)


@app.route('/health')
def health():
    status = {
        'status': 'ok' if startup_success else 'warning',
        'startup_success': startup_success,
        'timestamp': os.path.getmtime(__file__) if os.path.exists(__file__) else None
    }
    
    # Проверяем основные компоненты
    try:
        from docker_api import list_bots
        list_bots()
        status['docker'] = 'ok'
    except Exception as e:
        status['docker'] = f'error: {str(e)}'
    
    try:
        from auth import SessionLocal
        db = SessionLocal()
        db.close()
        status['database'] = 'ok'
    except Exception as e:
        status['database'] = f'error: {str(e)}'
    
    return jsonify(status), 200


# Обработчики ошибок
@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', 
                          error_code=404, 
                          error_message='Страница не найдена'), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f'Внутренняя ошибка сервера: {error}')
    return render_template('error.html', 
                          error_code=500, 
                          error_message='Внутренняя ошибка сервера'), 500

@app.errorhandler(429)
def ratelimit_handler(e):
    logger.warning(f'Rate limit exceeded: {request.remote_addr}')
    return jsonify({'error': 'Превышен лимит запросов'}), 429


if __name__ == '__main__':
    # Создаем необходимые папки
    try:
        os.makedirs('logs', exist_ok=True)
        os.makedirs('bots', exist_ok=True)
        os.makedirs('uploads', exist_ok=True)
    except Exception as e:
        print(f'Ошибка создания папок: {e}')
    
    logger.info('Starting Bot Manager on 0.0.0.0:5000')
    if not startup_success:
        logger.warning('Приложение запускается с ошибками инициализации')
    
    try:
        socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    except Exception as e:
        logger.critical(f'FATAL ERROR: {e}')
        import traceback
        traceback.print_exc()
        exit(1)
