from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify
from flask_socketio import SocketIO
import os
from werkzeug.utils import secure_filename

from config import cfg
from auth import bp_auth, login_required, init_db, ensure_admin
from docker_api import list_bots, start_bot, stop_bot, restart_bot, remove_bot, create_bot_from_repo, ensure_network, create_workspace, list_workspaces, get_available_images
from terminal_manager import start_terminal_session, handle_terminal_input, close_session

app = Flask(__name__)
app.config.from_object('config.Config')
app.register_blueprint(bp_auth)

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
def create_bot():
    data = request.form or request.json or {}
    git_url = data.get('git_url')
    bot_name = data.get('bot_name')
    branch = data.get('branch')
    try:
        cid = create_bot_from_repo(git_url, bot_name=bot_name, branch=branch)
        return jsonify({'status': 'ok', 'container_id': cid})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 400


@app.route('/workspace/create', methods=['GET', 'POST'])
@login_required
def create_workspace_page():
    if request.method == 'POST':
        data = request.form or request.json or {}
        workspace_name = data.get('workspace_name', '').strip()
        base_image = data.get('base_image', '').strip()
        
        # Порты (optional)
        port_mappings = {}
        if data.get('port_internal') and data.get('port_external'):
            try:
                port_mappings[str(data.get('port_internal'))] = int(data.get('port_external'))
            except (ValueError, TypeError):
                pass
        
        try:
            container_id = create_workspace(
                workspace_name=workspace_name,
                base_image=base_image if base_image else None,
                port_mappings=port_mappings if port_mappings else None
            )
            if request.content_type and 'application/json' in request.content_type:
                return jsonify({'status': 'ok', 'container_id': container_id})
            else:
                return redirect(url_for('dashboard'))
        except Exception as e:
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


if __name__ == '__main__':
    print(f'Starting Bot Manager on 0.0.0.0:5000')
    try:
        socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    except Exception as e:
        print(f'FATAL ERROR: {e}')
        import traceback
        traceback.print_exc()
        exit(1)
