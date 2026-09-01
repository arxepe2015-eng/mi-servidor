import os
import json
import random
from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'arxechat_clave_secreta_123'

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

USUARIOS_FILE = 'usuarios.json'
CHATS_FILE = 'chats.json'

def cargar_json(archivo):
    if not os.path.exists(archivo):
        with open(archivo, 'w', encoding='utf-8') as f:
            json.dump({}, f)
        return {}
    try:
        with open(archivo, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def guardar_json(archivo, datos):
    with open(archivo, 'w', encoding='utf-8') as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

HTML_LAYOUT = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Arxechat</title>
    <script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; -webkit-tap-highlight-color: transparent; }
        body { background-color: #0b141a; color: #e9edef; height: 100vh; display: flex; justify-content: center; align-items: center; overflow: hidden; }
        
        /* Modales */
        .modal-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(11,20,26,0.95); display: flex; justify-content: center; align-items: center; z-index: 1000; }
        .modal-box { background: #111b21; padding: 25px; border-radius: 12px; width: 90%; max-width: 400px; text-align: center; border: 1px solid #222d34; position: relative; }
        .modal-box h2 { margin-bottom: 15px; color: #00a884; }
        .modal-box input { width: 100%; padding: 14px; margin: 8px 0; background: #2a3942; border: 1px solid transparent; border-radius: 6px; color: white; outline: none; font-size: 1rem; }
        .modal-box input.input-error { border: 2px solid #ea4335 !important; background-color: #3b2224 !important; }
        .file-label { display: block; text-align: left; font-size: 0.85rem; color: #8696a0; margin-top: 10px; }
        .modal-box button, .btn-action { width: 100%; padding: 14px; background: #00a884; border: none; border-radius: 6px; color: white; font-weight: bold; cursor: pointer; margin-top: 12px; font-size: 1rem; }
        .btn-copy { background: #202c33; border: 1px solid #00a884; color: #00a884; margin-top: 8px; }
        .btn-danger { background: #ea4335 !important; margin-top: 10px !important; }
        .auth-toggle { margin-top: 15px; font-size: 0.9rem; color: #8696a0; cursor: pointer; padding: 10px; }
        .auth-toggle span { color: #00a884; text-decoration: underline; }
        .error-msg { color: #ea4335; font-size: 0.85rem; margin-top: 5px; display: none; }
        .close-btn { position: absolute; top: 10px; right: 15px; color: #8696a0; font-size: 1.8rem; cursor: pointer; padding: 5px 10px; }

        /* Contenedor Principal */
        .app-container { width: 100%; height: 100vh; display: flex; background: #111b21; display: none; }
        
        /* Sidebar Izquierdo */
        .sidebar { width: 350px; border-right: 1px solid #222d34; display: flex; flex-direction: column; background: #111b21; }
        .sidebar-header { background: #202c33; padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; }
        .user-info-btn { display: flex; align-items: center; gap: 10px; cursor: pointer; background: none; border: none; text-align: left; color: white; }
        .user-avatar { width: 42px; height: 42px; border-radius: 50%; background: #6b7c85; display: flex; justify-content: center; align-items: center; font-weight: bold; font-size: 1.2rem; color: white; object-fit: cover; flex-shrink: 0; }
        .add-btn { background: #00a884; border: none; color: white; width: 40px; height: 40px; border-radius: 50%; font-size: 1.5rem; cursor: pointer; display: flex; justify-content: center; align-items: center; }
        .contacts-list { flex: 1; overflow-y: auto; }
        .contact-item { display: flex; align-items: center; padding: 14px 16px; border-bottom: 1px solid #222d34; cursor: pointer; gap: 15px; background: transparent; width: 100%; border-left: none; border-right: none; border-top: none; text-align: left; color: white; }
        .contact-item:hover, .contact-item:active { background: #202c33; }
        .contact-info { display: flex; flex-direction: column; flex: 1; }
        .contact-name { font-weight: bold; font-size: 1rem; }
        .contact-id { font-size: 0.8rem; color: #8696a0; }

        /* Panel Central */
        .chat-area { flex: 1; display: flex; flex-direction: column; background: #0b141a; }
        .empty-state { flex: 1; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; color: #8696a0; padding: 20px; }
        .empty-state h3 { color: #e9edef; margin-bottom: 10px; font-size: 1.5rem; }
        
        /* Chat Activo */
        .active-chat-container { flex: 1; display: none; flex-direction: column; height: 100%; }
        .chat-header { background: #202c33; padding: 10px 16px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #222d34; }
        .chat-header-user { display: flex; align-items: center; gap: 12px; }
        .add-contact-banner { background: #004338; color: #00a884; border: 1px solid #00a884; padding: 6px 12px; border-radius: 6px; font-size: 0.85rem; font-weight: bold; cursor: pointer; margin-left: 10px; }
        .chat-menu-btn { background: none; border: none; color: #8696a0; font-size: 1.8rem; cursor: pointer; padding: 5px 10px; }
        .chat-messages { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
        .message { max-width: 65%; padding: 8px 12px; border-radius: 8px; font-size: 0.95rem; line-height: 1.4; word-wrap: break-word; }
        .message.received { background: #202c33; align-self: flex-start; border-top-left-radius: 0; }
        .message.sent { background: #005c4b; align-self: flex-end; border-top-right-radius: 0; }
        .chat-input-area { background: #202c33; padding: 12px 16px; display: flex; gap: 10px; align-items: center; }
        .chat-input-area input { flex: 1; padding: 12px; background: #2a3942; border: none; border-radius: 8px; color: white; outline: none; font-size: 1rem; }
        .chat-input-area button { background: #00a884; border: none; padding: 12px 20px; border-radius: 8px; color: white; font-weight: bold; cursor: pointer; font-size: 1rem; }
        
        @media (max-width: 768px) {
            .sidebar { width: 100%; }
            .chat-area { display: none; }
            .chat-area.active-mobile { display: flex; position: fixed; top:0; left:0; width:100%; height:100%; z-index:500; }
        }
    </style>
</head>
<body>

    <!-- Modal Autenticación -->
    <div class="modal-overlay" id="authModal">
        <div class="modal-box">
            <h2 id="authTitle">Iniciar Sesión</h2>
            <input type="text" id="authName" placeholder="Tu nombre / usuario">
            <input type="password" id="authPass" placeholder="Contraseña">
            <input type="password" id="authPassConfirm" placeholder="Confirmar contraseña" style="display:none;">
            
            <div id="fotoContainer" style="display:none;">
                <label class="file-label">Foto de perfil (Opcional):</label>
                <input type="file" id="authFoto" accept="image/*">
            </div>

            <div class="error-msg" id="errorMsg">Las contraseñas no coinciden</div>

            <button type="button" onclick="procesarAuth()" id="authBtn">Entrar</button>
            <div class="auth-toggle" onclick="toggleAuthMode()">
                <span id="toggleText">¿Aún no tienes cuenta? Regístrate</span>
            </div>
        </div>
    </div>

    <!-- Modal Ajustes de Usuario -->
    <div class="modal-overlay" id="settingsModal" style="display:none;">
        <div class="modal-box">
            <span class="close-btn" onclick="cerrarAjustes()">&times;</span>
            <h2>Ajustes de Perfil</h2>
            <div style="margin-bottom: 10px;">
                <span id="modalMyID" style="color: #00a884; font-weight: bold;">ID: --------</span>
                <button type="button" class="btn-action btn-copy" onclick="copiarMiID()">Copiar mi ID</button>
            </div>
            <input type="text" id="editName" placeholder="Nuevo nombre de usuario">
            <input type="password" id="editPass" placeholder="Nueva contraseña (opcional)">
            <label class="file-label">Cambiar foto de perfil:</label>
            <input type="file" id="editFoto" accept="image/*">
            <button type="button" class="btn-action" onclick="guardarAjustes()">Guardar Cambios</button>
            <button type="button" class="btn-action btn-danger" onclick="cerrarSesion()">Cerrar Sesión</button>
        </div>
    </div>

    <!-- Interfaz Principal -->
    <div class="app-container" id="appContainer">
        <!-- Sidebar Izquierdo -->
        <div class="sidebar">
            <div class="sidebar-header">
                <button type="button" class="user-info-btn" onclick="abrirAjustes()" title="Ajustes de Perfil">
                    <img id="myAvatarImg" class="user-avatar" style="display:none;">
                    <div id="myAvatarText" class="user-avatar">U</div>
                    <div>
                        <div id="myName" style="font-weight:bold;">Usuario</div>
                        <div id="myID" style="font-size:0.75rem; color:#00a884;">ID: --------</div>
                    </div>
                </button>
                <button type="button" class="add-btn" onclick="agregarContacto()" title="Añadir contacto">+</button>
            </div>
            <div class="contacts-list" id="contactsList"></div>
        </div>

        <!-- Panel Central -->
        <div class="chat-area" id="chatArea">
            <div class="empty-state" id="emptyState">
                <h3>Arxechat para Web</h3>
                <p>Aún no tienes contactos o no has seleccionado ninguno.<br>Pulsa el botón <b>+</b> arriba a la izquierda e introduce su ID de 8 dígitos para chatear.</p>
            </div>

            <div class="active-chat-container" id="activeChatContainer">
                <div class="chat-header">
                    <div class="chat-header-user">
                        <img id="activeAvatarImg" class="user-avatar" style="display:none;">
                        <div id="activeAvatarText" class="user-avatar">?</div>
                        <div>
                            <div id="activeName" class="contact-name">Contacto</div>
                            <div id="activeStatus" style="font-size:0.8rem; color:#8696a0;">En línea</div>
                        </div>
                        <button type="button" id="btnAddContactBanner" class="add-contact-banner" style="display:none;" onclick="guardarContactoTemporal()">+ Añadir a contactos</button>
                    </div>
                    <button type="button" class="chat-menu-btn" onclick="eliminarChat()" title="Eliminar Chat">&#8285;</button>
                </div>
                <div class="chat-messages" id="messages"></div>
                <div class="chat-input-area">
                    <input type="text" id="messageInput" placeholder="Escribe un mensaje..." autocomplete="off">
                    <button type="button" onclick="sendMessage()">Enviar</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        const socket = io();
        let isRegister = false;
        let miUsuario = null;
        let contactoActivo = null;
        let misContactos = [];

        window.onload = () => {
            const sesionGuardada = localStorage.getItem('arxechat_sesion');
            if (sesionGuardada) {
                miUsuario = JSON.parse(sesionGuardada);
                iniciarApp();
            }
        };

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

        function convertBase64(file) {
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.readAsDataURL(file);
                reader.onload = () => resolve(reader.result);
                reader.onerror = error => reject(error);
            });
        }

        async function procesarAuth() {
            limpiarErrores();
            const nombre = document.getElementById('authName').value.trim();
            const pass = document.getElementById('authPass').value;
            
            if(!nombre || !pass) return alert("Rellena todos los campos");

            if(isRegister) {
                const pass2 = document.getElementById('authPassConfirm').value;
                if(pass !== pass2) {
                    document.getElementById('authPass').classList.add('input-error');
                    document.getElementById('authPassConfirm').classList.add('input-error');
                    document.getElementById('errorMsg').style.display = 'block';
                    return;
                }
                
                let fotoBase64 = null;
                const fileInput = document.getElementById('authFoto');
                if(fileInput.files.length > 0) {
                    fotoBase64 = await convertBase64(fileInput.files[0]);
                }

                socket.emit('registrar_usuario', { nombre, pass, foto: fotoBase64 });
            } else {
                socket.emit('login_usuario', { nombre, pass });
            }
        }

        socket.on('auth_resultado', (res) => {
            if (res.exito) {
                miUsuario = res.usuario;
                localStorage.setItem('arxechat_sesion', JSON.stringify(miUsuario));
                if(isRegister) alert("¡Cuenta creada! Tu ID personal de 8 dígitos es: " + miUsuario.id);
                iniciarApp();
            } else {
                alert(res.mensaje);
            }
        });

        function iniciarApp() {
            document.getElementById('authModal').style.display = 'none';
            document.getElementById('appContainer').style.display = 'flex';
            
            document.getElementById('myName').innerText = miUsuario.nombre;
            document.getElementById('myID').innerText = "ID: " + miUsuario.id;
            document.getElementById('modalMyID').innerText = "Tu ID: " + miUsuario.id;
            
            if (miUsuario.foto) {
                document.getElementById('myAvatarImg').src = miUsuario.foto;
                document.getElementById('myAvatarImg').style.display = 'block';
                document.getElementById('myAvatarText').style.display = 'none';
            } else {
                document.getElementById('myAvatarText').innerText = miUsuario.nombre.charAt(0).toUpperCase();
            }

            if ("Notification" in window) Notification.requestPermission();
            
            // Conectar a la sala personal
            socket.emit('conectar_usuario', { id: miUsuario.id });
            socket.emit('obtener_contactos', { id: miUsuario.id });
        }

        function copiarMiID() {
            navigator.clipboard.writeText(miUsuario.id);
            alert("¡ID copiado al portapapeles!: " + miUsuario.id);
        }

        function abrirAjustes() {
            document.getElementById('editName').value = miUsuario.nombre;
            document.getElementById('settingsModal').style.display = 'flex';
        }

        function cerrarAjustes() {
            document.getElementById('settingsModal').style.display = 'none';
        }

        async function guardarAjustes() {
            const nuevoNombre = document.getElementById('editName').value.trim();
            const nuevaPass = document.getElementById('editPass').value;
            const fileInput = document.getElementById('editFoto');
            
            let nuevaFoto = miUsuario.foto;
            if (fileInput.files.length > 0) {
                nuevaFoto = await convertBase64(fileInput.files[0]);
            }

            socket.emit('actualizar_perfil', { id: miUsuario.id, nombre: nuevoNombre, pass: nuevaPass, foto: nuevaFoto });
        }

        socket.on('perfil_actualizado', (res) => {
            if(res.exito) {
                miUsuario = res.usuario;
                localStorage.setItem('arxechat_sesion', JSON.stringify(miUsuario));
                alert("Ajustes guardados correctamente");
                location.reload();
            }
        });

        function cerrarSesion() {
            localStorage.removeItem('arxechat_sesion');
            location.reload();
        }

        function agregarContacto() {
            const idContacto = prompt("Introduce el ID de 8 dígitos de la persona:");
            if(idContacto && idContacto.length === 8) {
                if(idContacto === miUsuario.id) return alert("No puedes añadirte a ti mismo.");
                socket.emit('guardar_contacto', { mi_id: miUsuario.id, contacto_id: idContacto });
            } else if(idContacto) {
                alert("El ID debe tener exactamente 8 dígitos.");
            }
        }

        socket.on('contactos_cargados', (lista) => {
            misContactos = lista;
            renderizarContactos();
        });

        function renderizarContactos() {
            const listaDiv = document.getElementById('contactsList');
            listaDiv.innerHTML = '';
            misContactos.forEach(c => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'contact-item';
                btn.onclick = () => seleccionarContacto(c.id, c.nombre, c.foto, true);
                
                const avatarHtml = c.foto ? `<img src="${c.foto}" class="user-avatar">` : `<div class="user-avatar">${c.nombre.charAt(0).toUpperCase()}</div>`;
                btn.innerHTML = `
                    ${avatarHtml}
                    <div class="contact-info">
                        <div class="contact-name">${c.nombre}</div>
                        <div class="contact-id">ID: ${c.id}</div>
                    </div>
                `;
                listaDiv.appendChild(btn);
            });
        }

        function seleccionarContacto(id, nombre, foto, esGuardado = true) {
            contactoActivo = { id, nombre, foto, esGuardado };
            document.getElementById('emptyState').style.display = 'none';
            document.getElementById('activeChatContainer').style.display = 'flex';
            document.getElementById('activeName').innerText = nombre;
            
            if(window.innerWidth <= 768) {
                document.getElementById('chatArea').classList.add('active-mobile');
            }

            document.getElementById('btnAddContactBanner').style.display = esGuardado ? 'none' : 'inline-block';

            if(foto) {
                document.getElementById('activeAvatarImg').src = foto;
                document.getElementById('activeAvatarImg').style.display = 'block';
                document.getElementById('activeAvatarText').style.display = 'none';
            } else {
                document.getElementById('activeAvatarImg').style.display = 'none';
                document.getElementById('activeAvatarText').style.display = 'flex';
                document.getElementById('activeAvatarText').innerText = nombre.charAt(0).toUpperCase();
            }
            
            document.getElementById('messages').innerHTML = '';
            socket.emit('cargar_historial', { emisor: miUsuario.id, receptor: id });
        }

        function guardarContactoTemporal() {
            if(contactoActivo) {
                socket.emit('guardar_contacto', { mi_id: miUsuario.id, contacto_id: contactoActivo.id });
                contactoActivo.esGuardado = true;
                document.getElementById('btnAddContactBanner').style.display = 'none';
            }
        }

        function eliminarChat() {
            if(contactoActivo && confirm("¿Quieres borrar esta conversación con " + contactoActivo.nombre + "?")) {
                if(!contactoActivo.esGuardado) {
                    // Si es un contacto no guardado, lo eliminamos de la lista
                    misContactos = misContactos.filter(c => c.id !== contactoActivo.id);
                    renderizarContactos();
                }
                document.getElementById('messages').innerHTML = '';
                document.getElementById('activeChatContainer').style.display = 'none';
                document.getElementById('emptyState').style.display = 'flex';
                if(window.innerWidth <= 768) {
                    document.getElementById('chatArea').classList.remove('active-mobile');
                }
            }
        }

        socket.on('historial_cargado', (mensajes) => {
            const messagesDiv = document.getElementById('messages');
            messagesDiv.innerHTML = '';
            mensajes.forEach(msg => {
                const msgElement = document.createElement('div');
                msgElement.classList.add('message');
                msgElement.classList.add(msg.emisor === miUsuario.id ? 'sent' : 'received');
                msgElement.textContent = msg.texto;
                messagesDiv.appendChild(msgElement);
            });
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        });

        socket.on('recibir_mensaje', (data) => {
            // Si no tenemos al contacto en la lista, lo añadimos temporalmente
            const existe = misContactos.some(c => c.id === data.emisor);
            if(!existe && data.emisor !== miUsuario.id) {
                misContactos.push({ id: data.emisor, nombre: data.nombreEmisor, foto: data.fotoEmisor });
                renderizarContactos();
            }

            if(contactoActivo && (data.emisor === contactoActivo.id || data.emisor === miUsuario.id)) {
                const messagesDiv = document.getElementById('messages');
                const msgElement = document.createElement('div');
                msgElement.classList.add('message');
                msgElement.classList.add(data.emisor === miUsuario.id ? 'sent' : 'received');
                msgElement.textContent = data.texto;
                messagesDiv.appendChild(msgElement);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            }

            if (data.emisor !== miUsuario.id && document.hidden && Notification.permission === "granted") {
                new Notification("Mensaje de " + data.nombreEmisor, { body: data.texto });
            }
        });

        function sendMessage() {
            const input = document.getElementById('messageInput');
            const texto = input.value.trim();
            if (texto !== '' && contactoActivo) {
                socket.emit('mensaje_enviado', {
                    emisor: miUsuario.id,
                    nombreEmisor: miUsuario.nombre,
                    fotoEmisor: miUsuario.foto,
                    receptor: contactoActivo.id,
                    texto: texto
                });
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

@socketio.on('conectar_usuario')
def conectar(data):
    # Conecta al usuario a una sala privada con su ID
    from flask_socketio import join_room
    join_room(data['id'])

@socketio.on('registrar_usuario')
def registrar(data):
    usuarios = cargar_json(USUARIOS_FILE)
    nombre = data['nombre']
    
    if nombre in usuarios:
        emit('auth_resultado', {'exito': False, 'mensaje': 'El nombre de usuario ya existe.'})
        return

    nuevo_id = str(random.randint(10000000, 99999999))
    nuevo_usuario = {
        'id': nuevo_id,
        'nombre': nombre,
        'pass': data['pass'],
        'foto': data.get('foto'),
        'contactos': []
    }
    
    usuarios[nombre] = nuevo_usuario
    guardar_json(USUARIOS_FILE, usuarios)
    emit('auth_resultado', {'exito': True, 'usuario': nuevo_usuario})

@socketio.on('login_usuario')
def login(data):
    usuarios = cargar_json(USUARIOS_FILE)
    nombre = data['nombre']
    
    if nombre in usuarios and usuarios[nombre]['pass'] == data['pass']:
        emit('auth_resultado', {'exito': True, 'usuario': usuarios[nombre]})
    else:
        emit('auth_resultado', {'exito': False, 'mensaje': 'La cuenta no existe o la contraseña es incorrecta.'})

@socketio.on('actualizar_perfil')
def actualizar_perfil(data):
    usuarios = cargar_json(USUARIOS_FILE)
    for nombre, u in usuarios.items():
        if u['id'] == data['id']:
            u['nombre'] = data['nombre']
            if data['pass']:
                u['pass'] = data['pass']
            u['foto'] = data['foto']
            guardar_json(USUARIOS_FILE, usuarios)
            emit('perfil_actualizado', {'exito': True, 'usuario': u})
            return

@socketio.on('obtener_contactos')
def obtener_contactos(data):
    usuarios = cargar_json(USUARIOS_FILE)
    mi_u = None
    for u in usuarios.values():
        if u['id'] == data['id']:
            mi_u = u
            break
    
    lista = []
    if mi_u:
        for c_id in mi_u.get('contactos', []):
            for u in usuarios.values():
                if u['id'] == c_id:
                    lista.append({'id': u['id'], 'nombre': u['nombre'], 'foto': u['foto']})
    emit('contactos_cargados', lista)

@socketio.on('guardar_contacto')
def guardar_contacto(data):
    usuarios = cargar_json(USUARIOS_FILE)
    mi_id = data['mi_id']
    contacto_id = data['contacto_id']
    
    for u in usuarios.values():
        if u['id'] == mi_id:
            if 'contactos' not in u:
                u['contactos'] = []
            if contacto_id not in u['contactos']:
                u['contactos'].append(contacto_id)
                guardar_json(USUARIOS_FILE, usuarios)
            break
    
    # Recargar contactos
    obtener_contactos({'id': mi_id})

@socketio.on('cargar_historial')
def cargar_historial(data):
    chats = cargar_json(CHATS_FILE)
    clave = "_".join(sorted([data['emisor'], data['receptor']]))
    historial = chats.get(clave, [])
    emit('historial_cargado', historial)

@socketio.on('mensaje_enviado')
def manejar_mensaje(data):
    chats = cargar_json(CHATS_FILE)
    clave = "_".join(sorted([data['emisor'], data['receptor']]))
    
    if clave not in chats:
        chats[clave] = []
    
    nuevo_msg = {
        'emisor': data['emisor'],
        'receptor': data['receptor'],
        'texto': data['texto'],
        'nombreEmisor': data['nombreEmisor'],
        'fotoEmisor': data.get('fotoEmisor')
    }
    
    chats[clave].append(nuevo_msg)
    guardar_json(CHATS_FILE, chats)
    
    # Emitir el mensaje a la sala del emisor y a la del receptor en tiempo real
    emit('recibir_mensaje', nuevo_msg, room=data['emisor'])
    emit('recibir_mensaje', nuevo_msg, room=data['receptor'])

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
