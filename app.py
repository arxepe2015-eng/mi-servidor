import os
from flask import Flask, render_template
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'arxechat_clave_secreta_123'

# Inicializamos Socket.IO para el tiempo real
socketio = SocketIO(app, cors_allowed_origins="*")

@app.route('/')
def home():
    return "Servidor de Arxechat activo y listo para WebSockets"

# Escuchar cuando un usuario envía un mensaje
@socketio.on('mensaje_enviado')
def manejar_mensaje(data):
    print("Mensaje recibido:", data)
    # Reenviar el mensaje a todos los usuarios conectados
    emit('recibir_mensaje', data, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
