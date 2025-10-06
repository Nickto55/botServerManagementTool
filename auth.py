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
    
    def change_password(self, new_password: str):
        """Изменить пароль пользователя"""
        db = SessionLocal()
        try:
            salt = bcrypt.gensalt(rounds=cfg.BCRYPT_ROUNDS)
            new_hash = bcrypt.hashpw(new_password.encode(), salt).decode()
            self.password_hash = new_hash
            db.merge(self)
            db.commit()
        finally:
            db.close()
    
    def change_username(self, new_username: str):
        """Изменить имя пользователя"""
        db = SessionLocal()
        try:
            # Проверяем, что новое имя не занято
            existing = db.execute(select(User).where(User.username == new_username)).scalar_one_or_none()
            if existing and existing.id != self.id:
                raise ValueError('Пользователь с таким именем уже существует')
            
            self.username = new_username
            db.merge(self)
            db.commit()
        finally:
            db.close()


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


def get_user_by_id(user_id: int):
    db = SessionLocal()
    try:
        stmt = select(User).where(User.id == user_id)
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


@bp_auth.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user_id = session.get('user_id')
    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if not user:
            flash('Пользователь не найден', 'danger')
            return redirect(url_for('auth.logout'))
        
        if request.method == 'POST':
            action = request.form.get('action')
            
            if action == 'change_password':
                current_password = request.form.get('current_password', '')
                new_password = request.form.get('new_password', '')
                confirm_password = request.form.get('confirm_password', '')
                
                if not user.verify(current_password):
                    flash('Неверный текущий пароль', 'danger')
                elif len(new_password) < 4:
                    flash('Пароль должен содержать минимум 4 символа', 'danger')
                elif new_password != confirm_password:
                    flash('Пароли не совпадают', 'danger')
                else:
                    user.change_password(new_password)
                    flash('Пароль успешно изменён', 'success')
            
            elif action == 'change_username':
                new_username = request.form.get('new_username', '').strip()
                
                if len(new_username) < 3:
                    flash('Имя пользователя должно содержать минимум 3 символа', 'danger')
                else:
                    try:
                        user.change_username(new_username)
                        session['username'] = new_username
                        flash('Имя пользователя успешно изменено', 'success')
                    except ValueError as e:
                        flash(str(e), 'danger')
        
        # Обновляем объект user после возможных изменений
        db.refresh(user)
        return render_template('profile.html', user=user)
    
    finally:
        db.close()


# Utility to ensure an admin user exists (called from install script or startup)
def ensure_admin():
    admin_user = os.getenv('ADMIN_USER', 'admin')
    admin_pass = os.getenv('ADMIN_PASS', 'admin')
    if not get_user_by_username(admin_user):
        User.create(admin_user, admin_pass)
