from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify
from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import logging
from werkzeug.utils import secure_filename
import validators

from config import cfg
from auth import bp_auth, login_required, init_db, ensure_admin
from docker_api import list_bots, start_bot, stop_bot, restart_bot, remove_bot, create_bot_from_repo, ensure_network, create_workspace, list_workspaces, get_available_images
from terminal_manager import start_terminal_session, handle_terminal_input, close_session

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

# Rate limiting
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["100 per hour"]
)

socketio = SocketIO(app, async_mode='eventlet')

ALLOWED_FRONTEND_EXT = {'.html', '.css', '.js'}


def startup():
    try:
        init_db()
        ensure_admin()
        ensure_network()
        print('Startup complete')
    except Exception as e:
        print(f'Startup error: {e}')
        # Не падаем на старте, позволяем приложению работать


# Вызываем startup при инициализации
with app.app_context():
    startup()


@app.route('/')
@login_required
def dashboard():
    bots = list_bots()
    workspaces = list_workspaces()
    return render_template('dashboard.html', bots=bots, workspaces=workspaces)


@app.route('/bots/create', methods=['POST'])
@login_required
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
@login_required
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
@login_required
def bot_action(name, action):
    try:
        if action == 'start':
            start_bot(name)
        elif action == 'stop':
            stop_bot(name)
        elif action == 'restart':
            restart_bot(name)
        elif action == 'remove':
            remove_bot(name, force=True)
        else:
            return jsonify({'status': 'error', 'error': 'Unknown action'}), 400
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 400


@app.route('/terminal/<name>')
@login_required
def terminal_view(name):
    return render_template('terminal.html', container=name)


# Frontend override upload
@app.route('/upload/frontend', methods=['GET', 'POST'])
@login_required
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
@login_required
def overridden_static(filename):
    return send_from_directory(cfg.UPLOADS_DIR, filename)


# SocketIO events
@socketio.on('connect')
def on_connect():
    pass


@socketio.on('terminal_start')
def on_terminal_start(data):
    container = data.get('container')
    start_terminal_session(request.sid, container)


@socketio.on('terminal_input')
def on_terminal_input(data):
    handle_terminal_input(request.sid, data.get('data', ''))


@socketio.on('disconnect')
def on_disconnect():
    close_session(request.sid)


@app.route('/health')
def health():
    return jsonify({'status': 'ok'}), 200


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
    # Создаем папку для логов
    os.makedirs('logs', exist_ok=True)
    
    logger.info('Starting Bot Manager on 0.0.0.0:5000')
    try:
        socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    except Exception as e:
        logger.critical(f'FATAL ERROR: {e}')
        import traceback
        traceback.print_exc()
        exit(1)
