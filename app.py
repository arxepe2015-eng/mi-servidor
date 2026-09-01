import os
from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'arxechat_clave_secreta_123'

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

HTML_LAYOUT = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Arxechat</title>
    <script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: Segoe UI, Tahoma, Geneva, Verdana, sans-serif; }
        body { background-color: #0b141a; color: #e9edef; height: 100vh; display: flex; justify-content: center; align-items: center; }
        .chat-container { width: 100%; max-width: 600px; height: 100vh; display: flex; flex-direction: column; background-color: #111b21; }
        .chat-header { background-color: #202c33; padding: 15px; text-align: center; font-size: 1.2rem; font-weight: bold; border-bottom: 1px solid #222d34; }
        .chat-messages { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
        .message { max-width: 75%; padding: 8px 12px; border-radius: 8px; font-size: 0.95rem; line-height: 1.4; word-wrap: break-word; }
        .message.received { background-color: #202c33; align-self: flex-start; border-top-left-radius: 0; }
        .message.sent { background-color: #005c4b; align-self: flex-end; border-top-right-radius: 0; }
        .chat-input-area { display: flex; padding: 10px; background-color: #202c33; gap: 10px; }
        .chat-input-area input { flex: 1; padding: 12px; border: none; border-radius: 8px; background-color: #2a3942; color: #fff; outline: none; }
        .chat-input-area button { padding: 12px 20px; border: none; border-radius: 8px; background-color: #00a884; color: #fff; font-weight: bold; cursor: pointer; }
        .chat-input-area button:hover { background-color: #029071; }
    </style>
</head>
<body>
    <div class="chat-container">
        <div class="chat-header">Arxechat</div>
        <div class="chat-messages" id="messages"></div>
        <div class="chat-input-area">
            <input type="text" id="messageInput" placeholder="Escribe un mensaje..." autocomplete="off">
            <button onclick="sendMessage()">Enviar</button>
        </div>
    </div>
    <script>
        const socket = io();
        const messagesDiv = document.getElementById('messages');
        const messageInput = document.getElementById('messageInput');

        socket.on('recibir_mensaje', (data) => {
            const msgElement = document.createElement('div');
            msgElement.classList.add('message');
            msgElement.classList.add(data.id === socket.id ? 'sent' : 'received');
            msgElement.textContent = data.texto;
            messagesDiv.appendChild(msgElement);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        });

        function sendMessage() {
            const texto = messageInput.value.trim();
            if (texto !== '') {
                socket.emit('mensaje_enviado', { texto: texto, id: socket.id });
                messageInput.value = '';
            }
        }

        messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_LAYOUT)

@socketio.on('mensaje_enviado')
def manejar_mensaje(data):
    print("Mensaje recibido:", data)
    emit('recibir_mensaje', data, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
