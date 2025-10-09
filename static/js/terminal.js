function initTerminal(containerName) {
    const termEl = document.getElementById('terminal');
    const inputEl = document.getElementById('termInput');
    const promptEl = document.getElementById('terminalPrompt');

    if (!termEl || !inputEl) {
        console.error('[terminal] elements not found');
        return;
    }

    if (!window.socket) {
        console.log('[terminal] creating new socket connection...');
        window.socket = io({transports:['websocket','polling']});
    } else {
        console.log('[terminal] reusing existing socket id=', window.socket.id);
    }
    const socket = window.socket;

    // Подписки СОЗДАЕМ раньше, чем отправляем terminal_start
    socket.off('terminal_output');
    socket.off('terminal_status');
    socket.off('terminal_command_started');
    socket.off('terminal_command_result');
    socket.off('terminal_history_full');

    socket.on('connect', ()=>{
        console.log('[terminal] socket connected id=', socket.id);
    });
    socket.on('disconnect', ()=>console.log('[terminal] socket disconnected'));
    socket.on('connect_error', (err)=>console.error('[terminal] socket connect_error', err));
    
    let commandHistory = [];
    let historyIndex = -1;
    let currentPath = '~';
    let currentUser = 'root';
    
    console.log('Initializing terminal for:', containerName);
    
    socket.on('terminal_output', (data) => {
        console.log('[terminal] output event:', data);
        if (data && data.data) {
            appendOutput(data.data);
        }
    });

    socket.on('terminal_status', (data) => {
        console.log('[terminal] status event:', data);
        const dockerLine = document.getElementById('dockerStatusLine');
        const containerLine = document.getElementById('containerStatusLine');
        if (dockerLine && data) {
            dockerLine.textContent = `Docker: ${data.docker}` + (data.error?` (error: ${data.error})`:'' );
        }
        if (containerLine && data) {
            if (data.container === 'present') {
                containerLine.textContent = `Container: ${data.container_running ? 'running' : 'stopped'}${data.image? ' image=' + data.image: ''}`;
                containerLine.style.color = data.container_running ? '#4ec9b0' : '#ffab70';
            } else if (data.container === 'missing') {
                containerLine.textContent = 'Container: missing';
                containerLine.style.color = '#f44747';
            } else {
                containerLine.textContent = 'Container: unknown';
                containerLine.style.color = '#aaa';
            }
        }
    });

    socket.on('terminal_command_started', (data) => {
        console.log('[terminal] command started', data);
    });
    socket.on('terminal_command_result', (data) => {
        console.log('[terminal] command result', data);
    });
    socket.on('terminal_history_full', (data) => {
        console.log('[terminal] history full', data);
    });

    // Теперь инициируем подключение сессии
    appendOutput('=== Подключение к ' + containerName + ' ===\n', 'cmd-success');
    socket.emit('terminal_start', {container_id: containerName});
    
    socket.on('connect_error', (error) => {
        appendOutput('\n[Ошибка подключения: ' + error + ']\n', 'cmd-error');
    });
    socket.on('disconnect', () => {
        appendOutput('\n[Соединение разорвано. Обновите страницу]\n', 'cmd-error');
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
        // Debug лог
        if (e.key === 'Enter') {
            console.log('[terminal] keydown Enter detected, input value=', inputEl.value);
        }
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
                    console.log('[terminal] emitting command via Enter:', command, ' socket connected=', socket.connected);
                    if (socket.connected) {
                        socket.emit('terminal_input', {data: command});
                    } else {
                        console.warn('[terminal] socket not connected, cannot send');
                    }
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

// Функция для отправки команды через кнопку
function sendCommand() {
    const inputEl = document.getElementById('termInput');
    const command = inputEl.value.trim();
    
    if (command) {
        console.log('Sending command via button:', command);
        if (window.socket && window.socket.connected) {
            window.socket.emit('terminal_input', {data: command});
            // Отобразим локально чтобы пользователь видел немедленно
            const containerName = document.getElementById('terminalPrompt').textContent.split('@')[1].split(':')[0];
            const currentUser = 'root';
            const currentPath = '~';
            const termEl = document.getElementById('terminal');
            const span = document.createElement('span');
            span.className = 'cmd-prompt';
            span.textContent = `${currentUser}@${containerName}:${currentPath}$ ${command}\n`;
            termEl.appendChild(span);
            termEl.scrollTop = termEl.scrollHeight;
        }
    }
    
    inputEl.focus();
}
