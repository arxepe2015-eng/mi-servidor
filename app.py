import os
from flask import Flask, render_template
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'arxechat_clave_secreta_123'

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

@app.route('/')
def home():
    return render_template('index.html')

@socketio.on('mensaje_enviado')
def manejar_mensaje(data):
    print("Mensaje recibido:", data)
    emit('recibir_mensaje', data, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
