import os
import random
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
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        body { background-color: #0b141a; color: #e9edef; height: 100vh; display: flex; justify-content: center; align-items: center; }
        
        /* Modal Autenticación */
        .auth-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: #0b141a; display: flex; justify-content: center; align-items: center; z-index: 1000; }
        .auth-box { background: #111b21; padding: 30px; border-radius: 12px; width: 90%; max-width: 400px; text-align: center; border: 1px solid #222d34; }
        .auth-box h2 { margin-bottom: 20px; color: #00a884; }
        .auth-box input { width: 100%; padding: 12px; margin: 8px 0; background: #2a3942; border: 1px solid transparent; border-radius: 6px; color: white; outline: none; }
        .auth-box input.input-error { border: 2px solid #ea4335 !important; background-color: #3b2224 !important; }
        .file-label { display: block; text-align: left; font-size: 0.8rem; color: #8696a0; margin-top: 10px; margin-bottom: 4px; }
        .auth-box button { width: 100%; padding: 12px; background: #00a884; border: none; border-radius: 6px; color: white; font-weight: bold; cursor: pointer; margin-top: 15px; }
        .auth-box button:hover { background: #029071; }
        .auth-toggle { margin-top: 15px; font-size: 0.85rem; color: #8696a0; cursor: pointer; }
        .auth-toggle span { color: #00a884; text-decoration: underline; }
        .error-msg { color: #ea4335; font-size: 0.85rem; margin-top: 8px; display: none; }

        /* Contenedor Principal */
        .app-container { width: 100%; height: 100vh; display: flex; background: #111b21; display: none; }
        
        /* Sidebar Izquierdo */
        .sidebar { width: 350px; border-right: 1px solid #222d34; display: flex; flex-direction: column; background: #111b21; }
        .sidebar-header { background: #202c33; padding: 10px 16px; display: flex; justify-content: space-between; align-items: center; }
        .user-avatar { width: 40px; height: 40px; border-radius: 50%; background: #6b7c85; display: flex; justify-content: center; align-items: center; font-weight: bold; font-size: 1.2rem; color: white; object-fit: cover; }
        .add-btn { background: #00a884; border: none; color: white; width: 35px; height: 35px; border-radius: 50%; font-size: 1.4rem; cursor: pointer; display: flex; justify-content: center; align-items: center; }
        .contacts-list { flex: 1; overflow-y: auto; }
        .contact-item { display: flex; align-items: center; padding: 12px 16px; border-bottom: 1px solid #222d34; cursor: pointer; gap: 15px; }
        .contact-item:hover { background: #202c33; }
        .contact-info { display: flex; flex-direction: column; }
        .contact-name { font-weight: bold; font-size: 1rem; }
        .contact-id { font-size: 0.8rem; color: #8696a0; }

        /* Panel Central */
        .chat-area { flex: 1; display: flex; flex-direction: column; background: #0b141a; }
        
        /* Pantalla Vacía sin contactos */
        .empty-state { flex: 1; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; color: #8696a0; padding: 20px; }
        .empty-state h3 { color: #e9edef; margin-bottom: 10px; font-size: 1.5rem; }
        
        /* Contenedor de Chat Activo */
        .active-chat-container { flex: 1; display: none; flex-direction: column; height: 100%; }
        .chat-header { background: #202c33; padding: 10px 16px; display: flex; align-items: center; gap: 15px; border-bottom: 1px solid #222d34; }
        .chat-header-status { font-size: 0.8rem; color: #8696a0; }
        .chat-messages { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
        .message { max-width: 65%; padding: 8px 12px; border-radius: 8px; font-size: 0.95rem; line-height: 1.4; word-wrap: break-word; }
        .message.received { background: #202c33; align-self: flex-start; border-top-left-radius: 0; }
        .message.sent { background: #005c4b; align-self: flex-end; border-top-right-radius: 0; }
        .chat-input-area { background: #202c33; padding: 10px 16px; display: flex; gap: 10px; align-items: center; }
        .chat-input-area input { flex: 1; padding: 12px; background: #2a3942; border: none; border-radius: 8px; color: white; outline: none; }
        .chat-input-area button { background: #00a884; border: none; padding: 12px 20px; border-radius: 8px; color: white; font-weight: bold; cursor: pointer; }
    </style>
</head>
<body>

    <!-- Modal Autenticación -->
    <div class="auth-overlay" id="authModal">
        <div class="auth-box">
            <h2 id="authTitle">Iniciar Sesión</h2>
            <input type="text" id="authName" placeholder="Tu nombre / usuario">
            <input type="password" id="authPass" placeholder="Contraseña">
            <input type="password" id="authPassConfirm" placeholder="Confirmar contraseña" style="display:none;">
            
            <div id="fotoContainer" style="display:none;">
                <label class="file-label">Foto de perfil (Opcional):</label>
                <input type="file" id="authFoto" accept="image/*">
            </div>

            <div class="error-msg" id="errorMsg">Las contraseñas no coinciden</div>

            <button onclick="procesarAuth()" id="authBtn">Entrar</button>
            <div class="auth-toggle" onclick="toggleAuthMode()">
                <span id="toggleText">¿Aún no tienes cuenta? Regístrate</span>
            </div>
        </div>
    </div>

    <!-- Interfaz Principal -->
    <div class="app-container" id="appContainer">
        <!-- Sidebar Izquierdo -->
        <div class="sidebar">
            <div class="sidebar-header">
                <div class="user-avatar" id="myAvatar">U</div>
                <div>
                    <div id="myName" style="font-weight:bold;">Usuario</div>
                    <div id="myID" style="font-size:0.75rem; color:#00a884;">ID: --------</div>
                </div>
                <button class="add-btn" onclick="agregarContacto()" title="Añadir contacto">+</button>
            </div>
            <div class="contacts-list" id="contactsList">
                <!-- Se añaden contactos aquí -->
            </div>
        </div>

        <!-- Panel Central -->
        <div class="chat-area">
            <!-- Estado sin contacto seleccionado -->
            <div class="empty-state" id="emptyState">
                <h3>Arxechat para Web</h3>
                <p>Aún no tienes contactos o no has seleccionado ninguno.<br>Pulsa el botón <b>+</b> arriba a la izquierda e introduce su ID de 8 dígitos para chatear.</p>
            </div>

            <!-- Chat Activo -->
            <div class="active-chat-container" id="activeChatContainer">
                <div class="chat-header">
                    <div class="user-avatar" id="activeAvatar">?</div>
                    <div>
                        <div id="activeName" class="contact-name">Contacto</div>
                        <div id="activeStatus" class="chat-header-status">En línea</div>
                    </div>
                </div>
                <div class="chat-messages" id="messages"></div>
                <div class="chat-input-area">
                    <input type="text" id="messageInput" placeholder="Escribe un mensaje..." autocomplete="off">
                    <button onclick="sendMessage()">Enviar</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        const socket = io();
        let isRegister = false;
        let usuariosGuardados = JSON.parse(localStorage.getItem('arxechat_users') || '{}');
        let miUsuario = null;
        let contactoActivo = null;

        function toggleAuthMode() {
            isRegister = !isRegister;
            limpiarErrores();
            document.getElementById('authTitle').innerText = isRegister ? 'Registrarse' : 'Iniciar Sesión';
            document.getElementById('authBtn').innerText = isRegister ? 'Crear Cuenta' : 'Entrar';
            document.getElementById('authPassConfirm').style.display = isRegister ? 'block' : 'none';
            document.getElementById('fotoContainer').style.display = isRegister ? 'block' : 'none';
            document.getElementById('toggleText').innerText = isRegister ? '¿Ya tienes cuenta? Inicia sesión' : '¿Aún no tienes cuenta? Regístrate';
        }

        function limpiarErrores() {
            document.getElementById('authPass').classList.remove('input-error');
            document.getElementById('authPassConfirm').classList.remove('input-error');
            document.getElementById('errorMsg').style.display = 'none';
        }

        function procesarAuth() {
            limpiarErrores();
            const nombre = document.getElementById('authName').value.trim();
            const pass = document.getElementById('authPass').value;
            
            if(!nombre || !pass) return alert("Por favor, rellena todos los campos");

            if(isRegister) {
                const pass2 = document.getElementById('authPassConfirm').value;
                if(pass !== pass2) {
                    document.getElementById('authPass').classList.add('input-error');
                    document.getElementById('authPassConfirm').classList.add('input-error');
                    document.getElementById('errorMsg').innerText = "Las contraseñas no coinciden";
                    document.getElementById('errorMsg').style.display = 'block';
                    return;
                }
                
                // Generar ID de 8 dígitos
                const nuevoID = Math.floor(10000000 + Math.random() * 90000000).toString();
                miUsuario = { id: nuevoID, nombre: nombre, pass: pass };
                
                // Guardar usuario
                usuariosGuardados[nombre] = miUsuario;
                localStorage.setItem('arxechat_users', JSON.stringify(usuariosGuardados));

                alert("¡Cuenta creada con éxito! Tu ID personal de 8 dígitos es: " + nuevoID);
            } else {
                // Validación al Iniciar Sesión
                if(!usuariosGuardados[nombre] || usuariosGuardados[nombre].pass !== pass) {
                    alert("La cuenta no existe o la contraseña es incorrecta. Por favor, regístrate si no tienes cuenta.");
                    return;
                }
                miUsuario = usuariosGuardados[nombre];
            }

            // Entrar a la app
            document.getElementById('authModal').style.display = 'none';
            document.getElementById('appContainer').style.display = 'flex';
            
            document.getElementById('myName').innerText = miUsuario.nombre;
            document.getElementById('myID').innerText = "ID: " + miUsuario.id;
            document.getElementById('myAvatar').innerText = miUsuario.nombre.charAt(0).toUpperCase();

            solicitarNotificaciones();
        }

        function solicitarNotificaciones() {
            if ("Notification" in window) {
                Notification.requestPermission();
            }
        }

        function agregarContacto() {
            const idContacto = prompt("Introduce el ID de 8 dígitos de la persona:");
            if(idContacto && idContacto.length === 8) {
                const lista = document.getElementById('contactsList');
                const item = document.createElement('div');
                item.className = 'contact-item';
                item.onclick = () => seleccionarContacto(idContacto, "Usuario " + idContacto);
                item.innerHTML = `
                    <div class="user-avatar">${idContacto.charAt(0)}</div>
                    <div class="contact-info">
                        <div class="contact-name">Usuario ${idContacto}</div>
                        <div class="contact-id">ID: ${idContacto}</div>
                    </div>
                `;
                lista.appendChild(item);
                seleccionarContacto(idContacto, "Usuario " + idContacto);
            } else if(idContacto) {
                alert("El ID debe tener exactamente 8 dígitos.");
            }
        }

        function seleccionarContacto(id, nombre) {
            contactoActivo = { id, nombre };
            document.getElementById('emptyState').style.display = 'none';
            document.getElementById('activeChatContainer').style.display = 'flex';
            document.getElementById('activeName').innerText = nombre;
            document.getElementById('activeAvatar').innerText = nombre.charAt(0);
        }

        socket.on('recibir_mensaje', (data) => {
            const messagesDiv = document.getElementById('messages');
            const msgElement = document.createElement('div');
            msgElement.classList.add('message');
            msgElement.classList.add(data.id === socket.id ? 'sent' : 'received');
            msgElement.textContent = data.texto;
            messagesDiv.appendChild(msgElement);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;

            if (document.hidden && Notification.permission === "granted") {
                new Notification("Mensaje de Arxechat", {
                    body: data.texto
                });
            }
        });

        function sendMessage() {
            const input = document.getElementById('messageInput');
            const texto = input.value.trim();
            if (texto !== '' && contactoActivo) {
                socket.emit('mensaje_enviado', { texto: texto, id: socket.id });
                input.value = '';
            }
        }

        document.getElementById('messageInput').addEventListener('keypress', (e) => {
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
    emit('recibir_mensaje', data, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
