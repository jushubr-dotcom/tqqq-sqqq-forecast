document.getElementById('trial').onclick = () => chrome.runtime.sendMessage({ type: 'openTrial' });
document.getElementById('login').onclick = () => chrome.runtime.sendMessage({ type: 'openLogin' });
