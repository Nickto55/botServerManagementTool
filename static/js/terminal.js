function initTerminal(containerName) {
    const termEl = document.getElementById('terminal');
    const inputEl = document.getElementById('termInput');
    const promptEl = document.getElementById('terminalPrompt');
    const socket = io();
    
    let commandHistory = [];
    let historyIndex = -1;
    let currentPath = '~';
    let currentUser = 'root';
    
    // Подключение к серверу
    socket.on('connect', () => {
        socket.emit('terminal_start', {container: containerName});
        appendOutput('Connected to ' + containerName + '\n', 'cmd-success');
        appendOutput('Type "help" for available commands or start typing...\n\n', 'cmd-info');
    });
    
    // Получение вывода
    socket.on('terminal_output', (data) => {
        appendOutput(data.data);
    });
    
    // Обработка отключения
    socket.on('disconnect', () => {
        appendOutput('\n[Connection lost. Refresh page to reconnect]\n', 'cmd-error');
    });
    
    // Функция для добавления вывода с цветовым кодированием
    function appendOutput(text, className = 'cmd-output') {
        const span = document.createElement('span');
        span.className = className;
        
        // Обработка ANSI escape последовательностей (базовая)
        text = text.replace(/\x1b\[[0-9;]*m/g, '');
        
        // Определение типа вывода по содержимому
        if (!className || className === 'cmd-output') {
            if (text.includes('error') || text.includes('Error') || text.includes('ERROR')) {
                span.className = 'cmd-error';
            } else if (text.includes('warning') || text.includes('Warning') || text.includes('WARN')) {
                span.className = 'cmd-warning';
            } else if (text.includes('success') || text.includes('Success') || text.includes('✓')) {
                span.className = 'cmd-success';
            } else if (text.match(/^[\w-]+@[\w-]+:/)) {
                span.className = 'cmd-prompt';
            }
        }
        
        span.textContent = text;
        termEl.appendChild(span);
        termEl.scrollTop = termEl.scrollHeight;
    }
    
    // Обработка ввода команд
    inputEl.addEventListener('keydown', (e) => {
        switch(e.key) {
            case 'Enter':
                e.preventDefault();
                const command = inputEl.value.trim();
                
                if (command) {
                    // Добавляем в историю
                    commandHistory.unshift(command);
                    if (commandHistory.length > 100) {
                        commandHistory.pop();
                    }
                    historyIndex = -1;
                    
                    // Показываем команду в терминале
                    appendOutput(`${currentUser}@${containerName}:${currentPath}$ ${command}\n`, 'cmd-prompt');
                    
                    // Отправляем команду
                    socket.emit('terminal_input', {data: command + '\n'});
                }
                
                inputEl.value = '';
                break;
                
            case 'ArrowUp':
                e.preventDefault();
                if (historyIndex < commandHistory.length - 1) {
                    historyIndex++;
                    inputEl.value = commandHistory[historyIndex] || '';
                }
                break;
                
            case 'ArrowDown':
                e.preventDefault();
                if (historyIndex > 0) {
                    historyIndex--;
                    inputEl.value = commandHistory[historyIndex] || '';
                } else {
                    historyIndex = -1;
                    inputEl.value = '';
                }
                break;
                
            case 'Tab':
                e.preventDefault();
                // Простая автокомплетация для базовых команд
                const currentValue = inputEl.value;
                const basicCommands = ['ls', 'cd', 'pwd', 'cat', 'nano', 'vim', 'mkdir', 'rmdir', 'rm', 'cp', 'mv', 'chmod', 'chown', 'ps', 'top', 'htop', 'df', 'du', 'free', 'uname', 'whoami', 'date', 'history', 'clear', 'exit', 'help'];
                const matches = basicCommands.filter(cmd => cmd.startsWith(currentValue));
                
                if (matches.length === 1) {
                    inputEl.value = matches[0] + ' ';
                } else if (matches.length > 1) {
                    appendOutput('\nAvailable commands: ' + matches.join(', ') + '\n', 'cmd-info');
                    appendOutput(`${currentUser}@${containerName}:${currentPath}$ ${currentValue}`, 'cmd-prompt');
                    inputEl.value = currentValue;
                }
                break;
                
            case 'l':
                if (e.ctrlKey) {
                    e.preventDefault();
                    clearTerminal();
                }
                break;
        }
    });
    
    // Функция очистки терминала
    function clearTerminal() {
        termEl.innerHTML = '';
        appendOutput('Terminal cleared\n\n', 'cmd-info');
    }
    
    // Фокус на поле ввода
    inputEl.focus();
    
    // Возвращаем фокус на поле ввода при клике в терминал
    termEl.addEventListener('click', () => {
        inputEl.focus();
    });
    
    // Обработка вставки из буфера обмена
    inputEl.addEventListener('paste', (e) => {
        // Даем обработать вставку, затем фокусируемся
        setTimeout(() => inputEl.focus(), 10);
    });
}
