import os
import bcrypt
from functools import wraps
from flask import Blueprint, request, session, redirect, url_for, render_template, flash
from sqlalchemy import Column, Integer, String, create_engine, select
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session
from config import cfg

engine = create_engine(cfg.SQLALCHEMY_DATABASE_URI, echo=False, future=True)
Base = declarative_base()
SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False))

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)

    @staticmethod
    def create(username: str, password: str):
        db = SessionLocal()
        try:
            salt = bcrypt.gensalt(rounds=cfg.BCRYPT_ROUNDS)
            password_hash = bcrypt.hashpw(password.encode(), salt).decode()
            user = User(username=username, password_hash=password_hash)
            db.add(user)
            db.commit()
            return user
        finally:
            db.close()

    def verify(self, password: str) -> bool:
        return bcrypt.checkpw(password.encode(), self.password_hash.encode())


def init_db():
    Base.metadata.create_all(bind=engine)


def get_user_by_username(username: str):
    db = SessionLocal()
    try:
        stmt = select(User).where(User.username == username)
        res = db.execute(stmt).scalar_one_or_none()
        return res
    finally:
        db.close()

# Blueprint
bp_auth = Blueprint('auth', __name__)


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return wrapper


@bp_auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = get_user_by_username(username)
        if user and user.verify(password):
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('dashboard'))
        flash('Неверные учетные данные', 'danger')
    return render_template('login.html')


@bp_auth.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))


# Utility to ensure an admin user exists (called from install script or startup)
def ensure_admin():
    admin_user = os.getenv('ADMIN_USER', 'admin')
    admin_pass = os.getenv('ADMIN_PASS', 'admin')
    if not get_user_by_username(admin_user):
        User.create(admin_user, admin_pass)
