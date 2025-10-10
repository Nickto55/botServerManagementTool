#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работы консоли сервера
"""

import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Проверка импортов"""
    print("🔍 Проверка импортов...")
    
    try:
        from terminal_manager import (
            start_server_console_session, 
            handle_server_console_input, 
            close_server_console_session
        )
        print("✅ Импорт функций консоли сервера успешен")
        return True
    except Exception as e:
        print(f"❌ Ошибка импорта: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_exec_backend():
    """Проверка exec_backend"""
    print("\n🔍 Проверка exec_backend...")
    
    try:
        from exec_backend import get_backend
        backend = get_backend()
        print("✅ Backend инициализирован")
        
        # Тестовая команда
        stdout, stderr, exit_code = backend.run("echo 'Hello from server'", timeout=5)
        print(f"📤 Команда выполнена:")
        print(f"   stdout: {stdout}")
        print(f"   stderr: {stderr}")
        print(f"   exit_code: {exit_code}")
        
        if exit_code == 0:
            print("✅ Команда выполнена успешно")
            return True
        else:
            print(f"⚠️  Команда завершилась с кодом {exit_code}")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка exec_backend: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_app_import():
    """Проверка импорта приложения"""
    print("\n🔍 Проверка импорта Flask приложения...")
    
    try:
        from app import app, socketio
        print("✅ Flask приложение импортировано")
        
        # Проверяем наличие обработчиков
        print("\n📋 Зарегистрированные SocketIO обработчики:")
        if hasattr(socketio, 'handlers'):
            for event, handlers in socketio.handlers.items():
                print(f"   - {event}: {len(handlers)} обработчиков")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка импорта приложения: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Главная функция"""
    print("=" * 60)
    print("🧪 Тестирование консоли сервера")
    print("=" * 60)
    
    results = []
    
    results.append(("Импорты", test_imports()))
    results.append(("Exec Backend", test_exec_backend()))
    results.append(("Flask App", test_app_import()))
    
    print("\n" + "=" * 60)
    print("📊 Результаты тестирования:")
    print("=" * 60)
    
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")
    
    all_passed = all(result[1] for result in results)
    
    if all_passed:
        print("\n🎉 Все тесты пройдены успешно!")
        return 0
    else:
        print("\n⚠️  Некоторые тесты провалились")
        return 1

if __name__ == "__main__":
    sys.exit(main())
