function initTerminal(containerName){
  const termEl = document.getElementById('terminal');
  const inputEl = document.getElementById('termInput');
  const socket = io();
  socket.on('connect', ()=>{
    socket.emit('terminal_start', {container: containerName});
  });
  socket.on('terminal_output', (data)=>{
    termEl.textContent += data.data;
    termEl.scrollTop = termEl.scrollHeight;
  });
  inputEl.addEventListener('keydown', (e)=>{
    if(e.key==='Enter'){
      const val = inputEl.value + '\n';
      socket.emit('terminal_input', {data: val});
      inputEl.value='';
    }
  });
}
