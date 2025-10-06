import os
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
ENV_PATH = os.path.join(BASE_DIR, '.env')
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'change-me')
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8  # 8 hours

    # Database (sqlite for simplicity)
    DB_PATH = os.path.join(BASE_DIR, 'app.db')
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{DB_PATH}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Docker
    DOCKER_BASE_NETWORK = os.getenv('DOCKER_BASE_NETWORK', 'bots_net')
    BOT_DEFAULT_IMAGE = os.getenv('BOT_DEFAULT_IMAGE', 'python:3.11-slim')

    # Paths
    BOTS_DIR = os.path.join(BASE_DIR, 'bots')
    UPLOADS_DIR = os.path.join(BASE_DIR, 'uploads')
    LOGS_DIR = os.path.join(BASE_DIR, 'logs')

    # Git
    GIT_CLONE_DEPTH = int(os.getenv('GIT_CLONE_DEPTH', '1'))

    # Security
    BCRYPT_ROUNDS = int(os.getenv('BCRYPT_ROUNDS', '12'))

cfg = Config()

os.makedirs(cfg.BOTS_DIR, exist_ok=True)
os.makedirs(cfg.UPLOADS_DIR, exist_ok=True)
os.makedirs(cfg.LOGS_DIR, exist_ok=True)
