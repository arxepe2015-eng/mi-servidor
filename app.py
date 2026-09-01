import os
import json
import random
import psycopg2
import psycopg2.extras
from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from pywebpush import webpush, WebPushException

app = Flask(__name__)
# La SECRET_KEY se lee de una variable de entorno en producción (Render).
# Si no existe (p.ej. en local), se usa un valor de repuesto solo para pruebas.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'arxechat_clave_secreta_123_dev')

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', max_http_buffer_size=10 * 1024 * 1024)

# --- BASE DE DATOS PERSISTENTE (PostgreSQL) ---
# En Render (plan gratuito) el disco es efímero: cualquier archivo local
# (como un .db de SQLite) se borra en cada reinicio/despliegue.
# Por eso los datos se guardan ahora en una base de datos PostgreSQL externa,
# indicada mediante la variable de entorno DATABASE_URL (p.ej. de Neon, Supabase o Render Postgres).
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError(
        "Falta la variable de entorno DATABASE_URL. Añádela en Render con la cadena de "
        "conexión de tu base de datos PostgreSQL (ver instrucciones adjuntas)."
    )

# Render Postgres / algunos proveedores dan la URL como postgres:// en vez de postgresql://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

# --- CLAVES VAPID PARA NOTIFICACIONES PUSH ---
VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '')
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
VAPID_CLAIMS_EMAIL = os.environ.get('VAPID_CLAIMS_EMAIL', 'mailto:admin@example.com')


def get_db():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require', cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id TEXT PRIMARY KEY,
                nombre TEXT UNIQUE,
                pass TEXT,
                foto TEXT,
                fondoChat TEXT,
                tema TEXT DEFAULT 'dark',
                brilloFondo INTEGER DEFAULT 100
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contactos (
                mi_id TEXT,
                contacto_id TEXT,
                PRIMARY KEY (mi_id, contacto_id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS grupos (
                id TEXT PRIMARY KEY,
                nombre TEXT,
                foto TEXT,
                creador_id TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS miembros_grupo (
                grupo_id TEXT,
                usuario_id TEXT,
                aceptado INTEGER DEFAULT 0,
                PRIMARY KEY (grupo_id, usuario_id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mensajes (
                id SERIAL PRIMARY KEY,
                clave_chat TEXT,
                emisor TEXT,
                receptor TEXT,
                texto TEXT,
                nombreEmisor TEXT,
                fotoEmisor TEXT,
                es_grupo INTEGER DEFAULT 0,
                fecha TIMESTAMP DEFAULT NOW()
            )
        ''')
        # Suscripciones de notificaciones push (una fila por dispositivo/navegador)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id SERIAL PRIMARY KEY,
                usuario_id TEXT,
                endpoint TEXT UNIQUE,
                p256dh TEXT,
                auth TEXT
            )
        ''')
        conn.commit()

init_db()


def enviar_push_a_usuario(usuario_id, emisor_id, titulo, cuerpo, url='/'):
    """Envía una notificación push real (llega aunque la pestaña esté cerrada)
    a todos los dispositivos guardados de un usuario, salvo que sea el propio emisor."""
    if usuario_id == emisor_id:
        return
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        return  # Push no configurado (faltan las claves VAPID en las variables de entorno)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, endpoint, p256dh, auth FROM push_subscriptions WHERE usuario_id = %s", (usuario_id,))
        subs = cursor.fetchall()

        payload = json.dumps({'title': titulo, 'body': cuerpo, 'url': url})

        for s in subs:
            try:
                webpush(
                    subscription_info={
                        "endpoint": s['endpoint'],
                        "keys": {"p256dh": s['p256dh'], "auth": s['auth']}
                    },
                    data=payload,
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": VAPID_CLAIMS_EMAIL}
                )
            except WebPushException as ex:
                status = getattr(ex.response, 'status_code', None)
                if status in (404, 410):
                    # La suscripción ya no es válida (navegador desinstalado, permiso revocado, etc.)
                    cursor.execute("DELETE FROM push_subscriptions WHERE id = %s", (s['id'],))
        conn.commit()

HTML_LAYOUT = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Arxechat</title>
    <script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
    <style>
        :root {
            --bg-body: #0b141a;
            --bg-card: #111b21;
            --bg-header: #202c33;
            --bg-input: #2a3942;
            --text-main: #e9edef;
            --text-sub: #8696a0;
            --accent: #00a884;
            --msg-sent: #005c4b;
            --msg-recv: #202c33;
            --border-color: #222d34;
            --link-color: #53bdeb;
        }

        body.light-theme {
            --bg-body: #e9edef;
            --bg-card: #ffffff;
            --bg-header: #f0f2f5;
            --bg-input: #f0f2f5;
            --text-main: #111b21;
            --text-sub: #667781;
            --accent: #008069;
            --msg-sent: #d9fdd3;
            --msg-recv: #ffffff;
            --border-color: #e9edef;
            --link-color: #027eb5;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; -webkit-tap-highlight-color: transparent; }
        body { background-color: var(--bg-body); color: var(--text-main); height: 100vh; display: flex; justify-content: center; align-items: center; overflow: hidden; transition: background 0.3s, color 0.3s; }
        
        .modal-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); display: flex; justify-content: center; align-items: center; z-index: 1000; }
        .modal-box { background: var(--bg-card); padding: 25px; border-radius: 12px; width: 90%; max-width: 420px; text-align: center; border: 1px solid var(--border-color); position: relative; max-height: 90vh; overflow-y: auto; }
        .modal-box h2 { margin-bottom: 15px; color: var(--accent); }
        .modal-box input, .modal-box select { width: 100%; padding: 12px; margin: 8px 0; background: var(--bg-input); border: 1px solid transparent; border-radius: 6px; color: var(--text-main); outline: none; font-size: 1rem; }
        .file-label { display: block; text-align: left; font-size: 0.85rem; color: var(--text-sub); margin-top: 10px; }
        .modal-box button, .btn-action { width: 100%; padding: 12px; background: var(--accent); border: none; border-radius: 6px; color: white; font-weight: bold; cursor: pointer; margin-top: 10px; font-size: 1rem; }
        .btn-copy { background: var(--bg-header); border: 1px solid var(--accent); color: var(--accent); }
        .btn-danger { background: #ea4335 !important; }
        .auth-toggle { margin-top: 15px; font-size: 0.9rem; color: var(--text-sub); cursor: pointer; padding: 5px; }
        .auth-toggle span { color: var(--accent); text-decoration: underline; }
        .error-msg { color: #ea4335; font-size: 0.85rem; margin-top: 5px; display: none; }
        .close-btn { position: absolute; top: 10px; right: 15px; color: var(--text-sub); font-size: 1.8rem; cursor: pointer; }

        .slider-container { display: flex; align-items: center; gap: 10px; margin-top: 5px; }
        .slider-container input[type="range"] { flex: 1; accent-color: var(--accent); cursor: pointer; }

        .member-item { display: flex; align-items: center; justify-content: space-between; padding: 10px; border-bottom: 1px solid var(--border-color); text-align: left; }
        .member-info { display: flex; align-items: center; gap: 10px; }
        .member-btn { background: var(--accent); border: none; color: white; padding: 6px 10px; border-radius: 6px; cursor: pointer; font-size: 0.8rem; }

        .app-container { width: 100%; height: 100vh; display: flex; background: var(--bg-card); display: none; }
        
        .sidebar { width: 350px; border-right: 1px solid var(--border-color); display: flex; flex-direction: column; background: var(--bg-card); }
        .sidebar-header { background: var(--bg-header); padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; }
        .user-info-btn { display: flex; align-items: center; gap: 10px; cursor: pointer; background: none; border: none; text-align: left; color: var(--text-main); }
        .user-avatar { width: 42px; height: 42px; border-radius: 50%; background: #6b7c85; display: flex; justify-content: center; align-items: center; font-weight: bold; font-size: 1.2rem; color: white; object-fit: cover; flex-shrink: 0; }
        .add-btn { background: var(--accent); border: none; color: white; width: 40px; height: 40px; border-radius: 50%; font-size: 1.5rem; cursor: pointer; display: flex; justify-content: center; align-items: center; }
        .contacts-list { flex: 1; overflow-y: auto; }
        .contact-item { display: flex; align-items: center; padding: 14px 16px; border-bottom: 1px solid var(--border-color); cursor: pointer; gap: 15px; background: transparent; width: 100%; border-left: none; border-right: none; border-top: none; text-align: left; color: var(--text-main); }
        .contact-item:hover, .contact-item:active { background: var(--bg-header); }
        .contact-info { display: flex; flex-direction: column; flex: 1; }
        .contact-name { font-weight: bold; font-size: 1rem; }
        .contact-id { font-size: 0.8rem; color: var(--text-sub); }

        .chat-area { flex: 1; display: flex; flex-direction: column; background: var(--bg-body); position: relative; }
        .empty-state { flex: 1; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; color: var(--text-sub); padding: 20px; }
        .empty-state h3 { color: var(--text-main); margin-bottom: 10px; font-size: 1.5rem; }
        
        .active-chat-container { flex: 1; display: none; flex-direction: column; height: 100%; position: relative; z-index: 1; }
        .chat-header { background: var(--bg-header); padding: 10px 16px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); }
        .chat-header-user { display: flex; align-items: center; gap: 12px; }
        .add-contact-banner { background: var(--accent); color: white; border: none; padding: 6px 12px; border-radius: 6px; font-size: 0.85rem; font-weight: bold; cursor: pointer; margin-left: 10px; }
        .chat-menu-btn { background: none; border: none; color: var(--text-sub); font-size: 1.8rem; cursor: pointer; padding: 5px 10px; }
        
        .chat-messages-wrapper { flex: 1; position: relative; overflow: hidden; display: flex; flex-direction: column; }
        .chat-bg-overlay { position: absolute; top:0; left:0; width:100%; height:100%; background-size: cover; background-position: center; z-index: 0; pointer-events: none; }
        .chat-messages { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; position: relative; z-index: 1; }
        
        .msg-row { display: flex; align-items: flex-end; gap: 8px; max-width: 75%; }
        .msg-row.sent { align-self: flex-end; flex-direction: row-reverse; }
        .msg-row.received { align-self: flex-start; }
        
        .msg-avatar { width: 28px; height: 28px; border-radius: 50%; object-fit: cover; flex-shrink: 0; background: #6b7c85; display: flex; justify-content: center; align-items: center; font-size: 0.75rem; color: white; font-weight: bold; }
        
        .message { padding: 8px 12px; border-radius: 8px; font-size: 0.95rem; line-height: 1.4; word-wrap: break-word; color: var(--text-main); position: relative; width: 100%; }
        .message.received { background: var(--msg-recv); border-top-left-radius: 0; }
        .message.sent { background: var(--msg-sent); border-top-right-radius: 0; }
        .message .sender-name { font-size: 0.75rem; font-weight: bold; color: var(--accent); margin-bottom: 3px; display: block; }
        .message a { color: var(--link-color); text-decoration: underline; word-break: break-all; }

        .chat-input-area { background: var(--bg-header); padding: 12px 16px; display: flex; gap: 10px; align-items: center; z-index: 2; }
        .chat-input-area input { flex: 1; padding: 12px; background: var(--bg-input); border: none; border-radius: 8px; color: var(--text-main); outline: none; font-size: 1rem; }
        .chat-input-area button { background: var(--accent); border: none; padding: 12px 20px; border-radius: 8px; color: white; font-weight: bold; cursor: pointer; font-size: 1rem; }
        
        /* Sugerencias de autocompletado */
        .suggestions-box { background: var(--bg-input); border: 1px solid var(--border-color); border-radius: 6px; max-height: 140px; overflow-y: auto; margin-top: 4px; text-align: left; display: none; }
        .suggestion-item { display: flex; align-items: center; gap: 10px; padding: 8px 12px; cursor: pointer; border-bottom: 1px solid var(--border-color); }
        .suggestion-item:hover { background: var(--bg-header); }
        .suggestion-item img, .suggestion-avatar { width: 26px; height: 26px; border-radius: 50%; object-fit: cover; background: #6b7c85; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; color: white; }

        @media (max-width: 768px) {
            .sidebar { width: 100%; }
            .chat-area { display: none; }
            .chat-area.active-mobile { display: flex; position: fixed; top:0; left:0; width:100%; height:100%; z-index:500; }
        }
    </style>
</head>
<body>

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

    <div class="modal-overlay" id="addChoiceModal" style="display:none;">
        <div class="modal-box">
            <span class="close-btn" onclick="cerrarModalChoice()">&times;</span>
            <h2>¿Qué deseas añadir?</h2>
            <button type="button" class="btn-action" onclick="abrirModalPersona()">Añadir Persona</button>
            <button type="button" class="btn-action" style="background: #202c33; border: 1px solid var(--accent); color: var(--accent);" onclick="abrirModalGrupo()">Crear Grupo</button>
        </div>
    </div>

    <div class="modal-overlay" id="addPersonModal" style="display:none;">
        <div class="modal-box">
            <span class="close-btn" onclick="cerrarModalPersona()">&times;</span>
            <h2>Añadir Persona</h2>
            <input type="text" id="personIdInput" placeholder="ID o nombre de tu contacto" oninput="filtrarSugerencias(this, 'personSuggestions')">
            <div class="suggestions-box" id="personSuggestions"></div>
            <button type="button" class="btn-action" onclick="confirmarAgregarPersona()">Añadir Contacto</button>
        </div>
    </div>

    <div class="modal-overlay" id="addGroupModal" style="display:none;">
        <div class="modal-box">
            <span class="close-btn" onclick="cerrarModalGrupo()">&times;</span>
            <h2>Crear Grupo</h2>
            <input type="text" id="groupNameInput" placeholder="Nombre del grupo">
            <label class="file-label">Foto del grupo (Opcional):</label>
            <input type="file" id="groupFotoInput" accept="image/*">
            <input type="text" id="groupMembersInput" placeholder="Añadir miembro (ID o nombre)" oninput="filtrarSugerencias(this, 'groupSuggestions')">
            <div class="suggestions-box" id="groupSuggestions"></div>
            <div id="selectedGroupMembers" style="text-align: left; margin-top: 5px; font-size: 0.85rem; color: var(--accent);"></div>
            <button type="button" class="btn-action" id="btnCrearGrupo" onclick="confirmarCrearGrupo()">Crear Grupo</button>
        </div>
    </div>

    <!-- MODAL PARA AÑADIR MIEMBROS A UN GRUPO EXISTENTE -->
    <div class="modal-overlay" id="addMemberModal" style="display:none;">
        <div class="modal-box">
            <span class="close-btn" onclick="cerrarModalAddMember()">&times;</span>
            <h2>Añadir al Grupo</h2>
            <input type="text" id="addMemberInput" placeholder="ID o nombre de tu contacto" oninput="filtrarSugerencias(this, 'addMemberSuggestions')">
            <div class="suggestions-box" id="addMemberSuggestions"></div>
            <button type="button" class="btn-action" onclick="confirmarAgregarMiembro()">Añadir</button>
        </div>
    </div>

    <!-- MODAL DE AJUSTES DEL GRUPO -->
    <div class="modal-overlay" id="groupSettingsModal" style="display:none;">
        <div class="modal-box">
            <span class="close-btn" onclick="cerrarAjustesGrupo()">&times;</span>
            <h2>Opciones del Grupo</h2>
            
            <input type="text" id="editGroupName" placeholder="Nombre del grupo">
            <label class="file-label">Cambiar foto del grupo:</label>
            <input type="file" id="editGroupFoto" accept="image/*">
            <button type="button" class="btn-action" onclick="guardarInfoGrupo()">Guardar Nombre/Foto</button>
            
            <hr style="margin: 15px 0; border-color: var(--border-color);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <h3 style="font-size: 1rem; color: var(--accent);">Miembros del Grupo</h3>
                <button type="button" style="width: auto; padding: 6px 12px; margin: 0; font-size: 0.85rem;" onclick="abrirModalAddMember()">+ Añadir</button>
            </div>
            <div id="groupMembersList"></div>

            <hr style="margin: 15px 0; border-color: var(--border-color);">
            <button type="button" class="btn-action btn-danger" style="margin-bottom: 8px;" onclick="eliminarGrupoTotalmente()">Eliminar Grupo</button>
            <button type="button" class="btn-action btn-danger" style="background: #a8251a !important;" onclick="eliminarChat()">Salir del Grupo</button>
        </div>
    </div>

    <div class="modal-overlay" id="settingsModal" style="display:none;">
        <div class="modal-box">
            <span class="close-btn" onclick="cerrarAjustes()">&times;</span>
            <h2>Ajustes de Perfil</h2>
            <div style="margin-bottom: 10px;">
                <span id="modalMyID" style="color: var(--accent); font-weight: bold;">ID: --------</span>
                <button type="button" class="btn-action btn-copy" onclick="copiarMiID()">Copiar mi ID</button>
            </div>
            
            <input type="text" id="editName" placeholder="Nuevo nombre de usuario">
            <input type="password" id="editPass" placeholder="Nueva contraseña (opcional)">
            
            <label class="file-label">Tema visual:</label>
            <select id="editTheme">
                <option value="dark">Oscuro (Negro)</option>
                <option value="light">Claro (Blanco)</option>
            </select>

            <label class="file-label">Cambiar foto de perfil:</label>
            <input type="file" id="editFoto" accept="image/*">

            <label class="file-label">Cambiar fondo de chat:</label>
            <input type="file" id="editFondoChat" accept="image/*">

            <label class="file-label">Brillo / Intensidad del Fondo (<span id="brilloVal">100</span>%):</label>
            <div class="slider-container">
                <input type="range" id="editBrillo" min="10" max="100" value="100" oninput="document.getElementById('brilloVal').innerText = this.value">
            </div>

            <button type="button" class="btn-action" id="btnGuardarAjustes" onclick="guardarAjustes()">Guardar Cambios</button>
            <button type="button" class="btn-action btn-danger" onclick="cerrarSesion()">Cerrar Sesión</button>
        </div>
    </div>

    <div class="app-container" id="appContainer">
        <div class="sidebar">
            <div class="sidebar-header">
                <button type="button" class="user-info-btn" onclick="abrirAjustes()" title="Ajustes de Perfil">
                    <img id="myAvatarImg" class="user-avatar" style="display:none;">
                    <div id="myAvatarText" class="user-avatar">U</div>
                    <div>
                        <div id="myName" style="font-weight:bold;">Usuario</div>
                        <div id="myID" style="font-size:0.75rem; color: var(--accent);">ID: --------</div>
                    </div>
                </button>
                <button type="button" class="add-btn" onclick="abrirModalChoice()" title="Añadir algo">+</button>
            </div>
            <div class="contacts-list" id="contactsList"></div>
        </div>

        <div class="chat-area" id="chatArea">
            <div class="empty-state" id="emptyState">
                <h3>Arxechat para Web</h3>
                <p>Aún no tienes chats o no has seleccionado ninguno.<br>Pulsa el botón <b>+</b> arriba a la izquierda para añadir personas o crear grupos.</p>
            </div>

            <div class="active-chat-container" id="activeChatContainer">
                <div class="chat-header">
                    <div class="chat-header-user">
                        <img id="activeAvatarImg" class="user-avatar" style="display:none;">
                        <div id="activeAvatarText" class="user-avatar">?</div>
                        <div>
                            <div id="activeName" class="contact-name">Contacto / Grupo</div>
                            <div id="activeStatus" style="font-size:0.8rem; color: var(--text-sub);">En línea</div>
                        </div>
                        <button type="button" id="btnAddContactBanner" class="add-contact-banner" style="display:none;" onclick="guardarContactoOAceptarGrupo()"></button>
                    </div>
                    <button type="button" class="chat-menu-btn" onclick="abrirOpcionesMenu()" title="Opciones">&#8285;</button>
                </div>
                
                <div class="chat-messages-wrapper">
                    <div class="chat-bg-overlay" id="chatBgOverlay"></div>
                    <div class="chat-messages" id="messages"></div>
                </div>

                <div class="chat-input-area">
                    <input type="text" id="messageInput" placeholder="Escribe un mensaje..." autocomplete="off">
                    <button type="button" onclick="sendMessage()">Enviar</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        const socket = io();
        const VAPID_PUBLIC_KEY = "{{ vapid_public_key }}";
        let isRegister = false;
        let miUsuario = null;
        let contactoActivo = null;
        let misContactos = [];
        let miembrosCrearGrupo = [];

        window.onload = () => {
            const sesionGuardada = localStorage.getItem('arxechat_sesion');
            if (sesionGuardada) {
                miUsuario = JSON.parse(sesionGuardada);
                socket.emit('login_usuario', { nombre: miUsuario.nombre, pass: miUsuario.pass });
            }
        };

        function aplicarTema() {
            if (miUsuario && miUsuario.tema === 'light') {
                document.body.classList.add('light-theme');
            } else {
                document.body.classList.remove('light-theme');
            }

            const bgOverlay = document.getElementById('chatBgOverlay');
            if (miUsuario && miUsuario.fondoChat) {
                bgOverlay.style.backgroundImage = `url('${miUsuario.fondoChat}')`;
                const opacidad = (miUsuario.brilloFondo !== undefined ? miUsuario.brilloFondo : 100) / 100;
                bgOverlay.style.opacity = opacidad;
            } else {
                bgOverlay.style.backgroundImage = 'none';
            }
        }

        function toggleAuthMode() {
            isRegister = !isRegister;
            limpiarErrores();
            document.getElementById('authTitle').innerText = isRegister ? 'Registrarse' : 'Iniciar Sesión';
            document.getElementById('authBtn').innerText = isRegister ? 'Crear Cuenta' : 'Entrar';
            document.getElementById('authPassConfirm').style.display = isRegister ? 'block' : 'none';
            document.getElementById('fotoContainer').style.display = isRegister ? 'block' : 'none';
            document.getElementById('toggleText').innerText = isRegister ? '¿Ya tienes cuenta? Inicia sesión' : '¿Aún no tienes cuenta? Regístrate';
        }

        function limpiarErrores() { document.getElementById('errorMsg').style.display = 'none'; }

        function convertAndCompressBase64(file) {
            return new Promise((resolve) => {
                const reader = new FileReader();
                reader.readAsDataURL(file);
                reader.onload = (e) => {
                    const img = new Image();
                    img.src = e.target.result;
                    img.onload = () => {
                        const canvas = document.createElement('canvas');
                        let width = img.width;
                        let height = img.height;
                        const maxDim = 800;
                        if (width > maxDim || height > maxDim) {
                            if (width > height) {
                                height = Math.round((height * maxDim) / width);
                                width = maxDim;
                            } else {
                                width = Math.round((width * maxDim) / height);
                                height = maxDim;
                            }
                        }
                        canvas.width = width;
                        canvas.height = height;
                        const ctx = canvas.getContext('2d');
                        ctx.drawImage(img, 0, 0, width, height);
                        resolve(canvas.toDataURL('image/jpeg', 0.7));
                    };
                };
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
                    document.getElementById('errorMsg').style.display = 'block';
                    return;
                }
                
                let fotoBase64 = null;
                const fileInput = document.getElementById('authFoto');
                if(fileInput.files.length > 0) {
                    fotoBase64 = await convertAndCompressBase64(fileInput.files[0]);
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
                if(isRegister) alert("¡Cuenta creada! Tu ID es: " + miUsuario.id);
                iniciarApp();
            } else {
                alert(res.mensaje);
                localStorage.removeItem('arxechat_sesion');
                document.getElementById('authModal').style.display = 'flex';
                document.getElementById('appContainer').style.display = 'none';
            }
        });

        function urlBase64ToUint8Array(base64String) {
            const padding = '='.repeat((4 - base64String.length % 4) % 4);
            const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
            const rawData = window.atob(base64);
            const outputArray = new Uint8Array(rawData.length);
            for (let i = 0; i < rawData.length; ++i) {
                outputArray[i] = rawData.charCodeAt(i);
            }
            return outputArray;
        }

        // Registra el Service Worker y activa notificaciones push reales:
        // llegan aunque la pestaña o el navegador estén cerrados (mientras el
        // sistema operativo no cierre por completo el navegador en segundo plano).
        async function solicitarPermisoNotificaciones() {
            if (!('serviceWorker' in navigator) || !('PushManager' in window) || !VAPID_PUBLIC_KEY) {
                return;
            }
            try {
                const registration = await navigator.serviceWorker.register('/service-worker.js');
                const permiso = await Notification.requestPermission();
                if (permiso !== 'granted') return;

                let subscription = await registration.pushManager.getSubscription();
                if (!subscription) {
                    subscription = await registration.pushManager.subscribe({
                        userVisibleOnly: true,
                        applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY)
                    });
                }
                socket.emit('guardar_subscripcion_push', {
                    usuario_id: miUsuario.id,
                    subscription: subscription.toJSON()
                });
            } catch (err) {
                console.warn('No se pudieron activar las notificaciones push:', err);
            }
        }

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
                document.getElementById('myAvatarImg').style.display = 'none';
                document.getElementById('myAvatarText').style.display = 'flex';
                document.getElementById('myAvatarText').innerText = miUsuario.nombre.charAt(0).toUpperCase();
            }

            aplicarTema();
            solicitarPermisoNotificaciones();
            
            socket.emit('conectar_usuario', { id: miUsuario.id });
            socket.emit('obtener_contactos', { id: miUsuario.id });
        }

        function copiarMiID() {
            navigator.clipboard.writeText(miUsuario.id);
            alert("¡ID copiado al portapapeles!: " + miUsuario.id);
        }

        function abrirModalChoice() { document.getElementById('addChoiceModal').style.display = 'flex'; }
        function cerrarModalChoice() { document.getElementById('addChoiceModal').style.display = 'none'; }
        
        function abrirModalPersona() { 
            cerrarModalChoice(); 
            document.getElementById('personIdInput').value = '';
            document.getElementById('personSuggestions').style.display = 'none';
            document.getElementById('addPersonModal').style.display = 'flex'; 
        }
        function cerrarModalPersona() { document.getElementById('addPersonModal').style.display = 'none'; }
        
        function abrirModalGrupo() { 
            cerrarModalChoice(); 
            miembrosCrearGrupo = [];
            document.getElementById('groupNameInput').value = '';
            document.getElementById('groupMembersInput').value = '';
            document.getElementById('groupSuggestions').style.display = 'none';
            document.getElementById('selectedGroupMembers').innerText = '';
            document.getElementById('addGroupModal').style.display = 'flex'; 
        }
        function cerrarModalGrupo() { document.getElementById('addGroupModal').style.display = 'none'; }

        function abrirModalAddMember() {
            // Se oculta primero el modal de "Opciones del Grupo" para que no quede
            // apilado debajo (eso era lo que dejaba el fondo en negro).
            document.getElementById('groupSettingsModal').style.display = 'none';
            document.getElementById('addMemberInput').value = '';
            document.getElementById('addMemberSuggestions').style.display = 'none';
            document.getElementById('addMemberModal').style.display = 'flex';
        }
        function cerrarModalAddMember() {
            document.getElementById('addMemberModal').style.display = 'none';
            // Al cerrar (con la X o tras añadir), se vuelve a mostrar "Opciones del Grupo".
            document.getElementById('groupSettingsModal').style.display = 'flex';
        }

        /* Filtrado y sugerencias de contactos */
        function filtrarSugerencias(inputElem, suggestionsContainerId) {
            const query = inputElem.value.trim().toLowerCase();
            const container = document.getElementById(suggestionsContainerId);
            container.innerHTML = '';

            if(!query) {
                container.style.display = 'none';
                return;
            }

            const coincidencias = misContactos.filter(c => !c.esGrupo && (c.nombre.toLowerCase().includes(query) || c.id.includes(query)));

            if(coincidencias.length === 0) {
                container.style.display = 'none';
                return;
            }

            coincidencias.forEach(c => {
                const div = document.createElement('div');
                div.className = 'suggestion-item';
                
                const avatar = c.foto ? `<img src="${c.foto}">` : `<div class="suggestion-avatar">${c.nombre.charAt(0).toUpperCase()}</div>`;
                div.innerHTML = `${avatar} <div><strong>${c.nombre}</strong> <br><small style="color:var(--text-sub)">${c.id}</small></div>`;
                
                div.onclick = () => {
                    inputElem.value = c.id;
                    container.style.display = 'none';
                    if(suggestionsContainerId === 'groupSuggestions') {
                        if(!miembrosCrearGrupo.includes(c.id)) {
                            miembrosCrearGrupo.push(c.id);
                            document.getElementById('selectedGroupMembers').innerText = "Añadidos: " + miembrosCrearGrupo.join(', ');
                        }
                        inputElem.value = '';
                    }
                };
                container.appendChild(div);
            });
            container.style.display = 'block';
        }

        function confirmarAgregarPersona() {
            const idContacto = document.getElementById('personIdInput').value.trim();
            if(idContacto && idContacto.length === 8) {
                if(idContacto === miUsuario.id) return alert("No puedes añadirte a ti mismo.");
                socket.emit('guardar_contacto', { mi_id: miUsuario.id, contacto_id: idContacto });
                cerrarModalPersona();
            } else {
                alert("El ID debe tener exactamente 8 dígitos.");
            }
        }

        async function confirmarCrearGrupo() {
            const nombre = document.getElementById('groupNameInput').value.trim();
            const rawInput = document.getElementById('groupMembersInput').value.trim();
            
            if(!nombre) return alert("Introduce un nombre para el grupo.");
            
            if(rawInput && rawInput.length === 8 && !miembrosCrearGrupo.includes(rawInput)) {
                miembrosCrearGrupo.push(rawInput);
            }

            const btn = document.getElementById('btnCrearGrupo');
            btn.innerText = "Creando...";
            btn.disabled = true;

            let fotoBase64 = null;
            const fileInput = document.getElementById('groupFotoInput');
            if(fileInput.files.length > 0) {
                fotoBase64 = await convertAndCompressBase64(fileInput.files[0]);
            }

            miembrosCrearGrupo.push(miUsuario.id);

            socket.emit('crear_grupo', {
                nombre: nombre,
                foto: fotoBase64,
                creador_id: miUsuario.id,
                miembros: miembrosCrearGrupo
            });
        }

        function confirmarAgregarMiembro() {
            const nuevoId = document.getElementById('addMemberInput').value.trim();
            if(nuevoId && nuevoId.length === 8) {
                socket.emit('anadir_miembro_grupo', { grupo_id: contactoActivo.id, usuario_id: nuevoId });
                cerrarModalAddMember();
            } else {
                alert("El ID debe tener 8 dígitos.");
            }
        }

        socket.on('miembro_anadido_resultado', (res) => {
            if(res.exito) {
                alert("Miembro añadido al grupo.");
                socket.emit('obtener_detalles_grupo', { grupo_id: contactoActivo.id });
            } else {
                alert(res.mensaje);
            }
        });

        socket.on('grupo_creado_resultado', (res) => {
            const btn = document.getElementById('btnCrearGrupo');
            btn.innerText = "Crear Grupo";
            btn.disabled = false;

            if(res.exito) {
                alert("¡Grupo creado con éxito!");
                cerrarModalGrupo();
                socket.emit('obtener_contactos', { id: miUsuario.id });
            } else {
                alert(res.mensaje);
            }
        });

        function abrirOpcionesMenu() {
            if(!contactoActivo) return;
            if(contactoActivo.esGrupo) {
                document.getElementById('editGroupName').value = contactoActivo.nombre;
                socket.emit('obtener_detalles_grupo', { grupo_id: contactoActivo.id });
                document.getElementById('groupSettingsModal').style.display = 'flex';
            } else {
                eliminarChat();
            }
        }

        function cerrarAjustesGrupo() {
            document.getElementById('groupSettingsModal').style.display = 'none';
        }

        socket.on('detalles_grupo_cargados', (data) => {
            const container = document.getElementById('groupMembersList');
            container.innerHTML = '';
            data.miembros.forEach(m => {
                const item = document.createElement('div');
                item.className = 'member-item';
                
                const esYo = m.id === miUsuario.id;
                const botonPrivado = esYo ? '' : `<button class="member-btn" onclick="iniciarChatPrivado('${m.id}', '${m.nombre}')">Privado</button>`;
                
                item.innerHTML = `
                    <div class="member-info">
                        <strong>${m.nombre}</strong> <span style="font-size:0.8rem; color:var(--text-sub);">(ID: ${m.id})</span>
                    </div>
                    ${botonPrivado}
                `;
                container.appendChild(item);
            });
        });

        function iniciarChatPrivado(id, nombre) {
            cerrarAjustesGrupo();
            socket.emit('guardar_contacto', { mi_id: miUsuario.id, contacto_id: id });
            seleccionarContacto({ id: id, nombre: nombre, foto: null, esGuardado: true, esGrupo: false });
        }

        async function guardarInfoGrupo() {
            const nuevoNombre = document.getElementById('editGroupName').value.trim();
            const fileInput = document.getElementById('editGroupFoto');
            let nuevaFoto = null;

            if(fileInput.files.length > 0) {
                nuevaFoto = await convertAndCompressBase64(fileInput.files[0]);
            }

            socket.emit('actualizar_grupo', {
                grupo_id: contactoActivo.id,
                nombre: nuevoNombre,
                foto: nuevaFoto
            });
        }

        socket.on('grupo_actualizado', (res) => {
            if(res.exito) {
                alert("Grupo actualizado.");
                cerrarAjustesGrupo();
                socket.emit('obtener_contactos', { id: miUsuario.id });
            }
        });

        function abrirAjustes() {
            document.getElementById('editName').value = miUsuario.nombre;
            document.getElementById('editTheme').value = miUsuario.tema || 'dark';
            const brillo = miUsuario.brilloFondo !== undefined ? miUsuario.brilloFondo : 100;
            document.getElementById('editBrillo').value = brillo;
            document.getElementById('brilloVal').innerText = brillo;
            document.getElementById('settingsModal').style.display = 'flex';
        }

        function cerrarAjustes() { document.getElementById('settingsModal').style.display = 'none'; }

        async function guardarAjustes() {
            const btn = document.getElementById('btnGuardarAjustes');
            btn.innerText = "Guardando...";
            btn.disabled = true;

            const nuevoNombre = document.getElementById('editName').value.trim();
            const nuevaPass = document.getElementById('editPass').value;
            const nuevoTema = document.getElementById('editTheme').value;
            const nuevoBrillo = parseInt(document.getElementById('editBrillo').value);
            
            const fileFoto = document.getElementById('editFoto');
            let nuevaFoto = miUsuario.foto;
            if (fileFoto.files.length > 0) {
                nuevaFoto = await convertAndCompressBase64(fileFoto.files[0]);
            }

            const fileFondo = document.getElementById('editFondoChat');
            let nuevoFondo = miUsuario.fondoChat;
            if (fileFondo.files.length > 0) {
                nuevoFondo = await convertAndCompressBase64(fileFondo.files[0]);
            }

            socket.emit('actualizar_perfil', { 
                id: miUsuario.id, 
                nombre: nuevoNombre, 
                pass: nuevaPass, 
                foto: nuevaFoto,
                fondoChat: nuevoFondo,
                tema: nuevoTema,
                brilloFondo: nuevoBrillo
            });
        }

        socket.on('perfil_actualizado', (res) => {
            const btn = document.getElementById('btnGuardarAjustes');
            btn.innerText = "Guardar Cambios";
            btn.disabled = false;

            if(res.exito) {
                miUsuario = res.usuario;
                localStorage.setItem('arxechat_sesion', JSON.stringify(miUsuario));
                alert("¡Ajustes guardados correctamente!");
                cerrarAjustes();
                iniciarApp();
            } else {
                alert(res.mensaje);
            }
        });

        function cerrarSesion() {
            localStorage.removeItem('arxechat_sesion');
            location.reload();
        }

        socket.on('contacto_resultado', (res) => {
            if(!res.exito) {
                alert(res.mensaje);
            } else {
                socket.emit('obtener_contactos', { id: miUsuario.id });
            }
        });

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
                btn.onclick = () => seleccionarContacto(c);
                
                const avatarHtml = c.foto ? `<img src="${c.foto}" class="user-avatar">` : `<div class="user-avatar">${c.nombre.charAt(0).toUpperCase()}</div>`;
                
                let etiqueta = '';
                if (c.esGrupo) {
                    etiqueta = c.esGuardado ? '<span style="font-size:0.75rem; color:var(--accent);">(Grupo)</span>' : '<span style="font-size:0.75rem; color:#ea4335;">[Aceptar Grupo]</span>';
                } else {
                    etiqueta = c.esGuardado ? '' : '<span style="font-size:0.75rem; color:var(--accent);">(Nuevo)</span>';
                }

                btn.innerHTML = `
                    ${avatarHtml}
                    <div class="contact-info">
                        <div class="contact-name">${c.nombre} ${etiqueta}</div>
                        <div class="contact-id">${c.esGrupo ? 'Grupo' : 'ID: ' + c.id}</div>
                    </div>
                `;
                listaDiv.appendChild(btn);
            });
        }

        function seleccionarContacto(c) {
            contactoActivo = c;
            document.getElementById('emptyState').style.display = 'none';
            document.getElementById('activeChatContainer').style.display = 'flex';
            document.getElementById('activeName').innerText = c.nombre;
            document.getElementById('activeStatus').innerText = c.esGrupo ? "Grupo de chat" : "En línea";
            
            if(window.innerWidth <= 768) {
                document.getElementById('chatArea').classList.add('active-mobile');
            }

            const bannerBtn = document.getElementById('btnAddContactBanner');
            if(!c.esGuardado) {
                bannerBtn.style.display = 'inline-block';
                bannerBtn.innerText = c.esGrupo ? "Aceptar Grupo" : "+ Añadir a contactos";
            } else {
                bannerBtn.style.display = 'none';
            }

            if(c.foto) {
                document.getElementById('activeAvatarImg').src = c.foto;
                document.getElementById('activeAvatarImg').style.display = 'block';
                document.getElementById('activeAvatarText').style.display = 'none';
            } else {
                document.getElementById('activeAvatarImg').style.display = 'none';
                document.getElementById('activeAvatarText').style.display = 'flex';
                document.getElementById('activeAvatarText').innerText = c.nombre.charAt(0).toUpperCase();
            }
            
            document.getElementById('messages').innerHTML = '';
            socket.emit('cargar_historial', { emisor: miUsuario.id, receptor: c.id, esGrupo: c.esGrupo });
        }

        function guardarContactoOAceptarGrupo() {
            if(contactoActivo) {
                if(contactoActivo.esGrupo) {
                    socket.emit('aceptar_grupo', { usuario_id: miUsuario.id, grupo_id: contactoActivo.id });
                } else {
                    socket.emit('guardar_contacto', { mi_id: miUsuario.id, contacto_id: contactoActivo.id });
                }
                contactoActivo.esGuardado = true;
                document.getElementById('btnAddContactBanner').style.display = 'none';
            }
        }

        socket.on('grupo_aceptado', () => {
            alert("¡Grupo guardado en tu cuenta!");
            socket.emit('obtener_contactos', { id: miUsuario.id });
        });

        function eliminarGrupoTotalmente() {
            if(contactoActivo && contactoActivo.esGrupo && confirm("¿Estás seguro de que deseas eliminar este grupo para todos los miembros? Se borra permanentemente.")) {
                socket.emit('eliminar_grupo_completo', { grupo_id: contactoActivo.id });
            }
        }

        socket.on('grupo_eliminado', () => {
            cerrarAjustesGrupo();
            document.getElementById('messages').innerHTML = '';
            document.getElementById('activeChatContainer').style.display = 'none';
            document.getElementById('emptyState').style.display = 'flex';
            if(window.innerWidth <= 768) {
                document.getElementById('chatArea').classList.remove('active-mobile');
            }
            socket.emit('obtener_contactos', { id: miUsuario.id });
        });

        function eliminarChat() {
            if(contactoActivo && confirm(contactoActivo.esGrupo ? "¿Quieres salir de este grupo?" : "¿Quieres borrar este contacto y su conversación?")) {
                if(contactoActivo.esGrupo) {
                    socket.emit('salir_grupo', { usuario_id: miUsuario.id, grupo_id: contactoActivo.id });
                } else {
                    socket.emit('eliminar_contacto', { mi_id: miUsuario.id, contacto_id: contactoActivo.id });
                }
                cerrarAjustesGrupo();
                document.getElementById('messages').innerHTML = '';
                document.getElementById('activeChatContainer').style.display = 'none';
                document.getElementById('emptyState').style.display = 'flex';
                if(window.innerWidth <= 768) {
                    document.getElementById('chatArea').classList.remove('active-mobile');
                }
            }
        }

        function formatearTextoConLinks(texto) {
            const urlRegex = /(https?:\/\/[^\s]+)/g;
            return texto.replace(urlRegex, function(url) {
                return `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`;
            });
        }

        function renderizarMensaje(msg) {
            const messagesDiv = document.getElementById('messages');
            const esMio = msg.emisor === miUsuario.id;
            
            const rowDiv = document.createElement('div');
            rowDiv.className = `msg-row ${esMio ? 'sent' : 'received'}`;

            let avatarHtml = '';
            if(!esMio && contactoActivo.esGrupo) {
                avatarHtml = msg.fotoEmisor 
                    ? `<img src="${msg.fotoEmisor}" class="msg-avatar">`
                    : `<div class="msg-avatar">${(msg.nombreEmisor || '?').charAt(0).toUpperCase()}</div>`;
            }

            const msgElement = document.createElement('div');
            msgElement.className = `message ${esMio ? 'sent' : 'received'}`;

            let senderHeader = '';
            if(!esMio && contactoActivo.esGrupo) {
                senderHeader = `<span class="sender-name">${msg.nombreEmisor || 'Usuario'}</span>`;
            }

            msgElement.innerHTML = `${senderHeader}${formatearTextoConLinks(msg.texto)}`;
            
            rowDiv.innerHTML = avatarHtml;
            rowDiv.appendChild(msgElement);

            messagesDiv.appendChild(rowDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        socket.on('historial_cargado', (mensajes) => {
            const messagesDiv = document.getElementById('messages');
            messagesDiv.innerHTML = '';
            mensajes.forEach(msg => renderizarMensaje(msg));
        });

        socket.on('recibir_mensaje', (data) => {
            socket.emit('obtener_contactos', { id: miUsuario.id });

            if(contactoActivo && (data.clave_chat === contactoActivo.id || data.emisor === contactoActivo.id || data.receptor === miUsuario.id)) {
                renderizarMensaje(data);
            }
            // La notificación visual ahora la muestra el Service Worker (push real),
            // así llega igual aunque la pestaña esté cerrada; aquí ya no se duplica.
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
                    esGrupo: contactoActivo.esGrupo ? 1 : 0,
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

@socketio.on('conectar_usuario')
def conectar(data):
    join_room(data['id'])

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT grupo_id FROM miembros_grupo WHERE usuario_id = %s", (data['id'],))
        for r in cursor.fetchall():
            join_room(r['grupo_id'])

@socketio.on('registrar_usuario')
def registrar(data):
    nombre = data['nombre']
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM usuarios WHERE nombre = %s", (nombre,))
        row = cursor.fetchone()

        if row:
            # Corregido: antes, registrarse con un nombre ya existente sobrescribía
            # la contraseña de esa cuenta sin comprobar nada (cualquiera podía
            # "robar" una cuenta ajena solo con su nombre). Ahora se rechaza.
            emit('auth_resultado', {
                'exito': False,
                'mensaje': 'Ese nombre de usuario ya existe. Inicia sesión o elige otro nombre.'
            })
            return

        nuevo_id = str(random.randint(10000000, 99999999))
        pass_hash = generate_password_hash(data['pass'])
        cursor.execute(
            "INSERT INTO usuarios (id, nombre, pass, foto, fondoChat, tema, brilloFondo) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (nuevo_id, nombre, pass_hash, data.get('foto'), None, 'dark', 100)
        )
        conn.commit()

        cursor.execute("SELECT * FROM usuarios WHERE id = %s", (nuevo_id,))
        nuevo_usuario = dict(cursor.fetchone())
        nuevo_usuario.pop('pass', None)
        nuevo_usuario['pass'] = data['pass']  # se devuelve en texto plano solo para guardar la sesión local

        emit('auth_resultado', {'exito': True, 'usuario': nuevo_usuario})

@socketio.on('login_usuario')
def login(data):
    nombre = data['nombre']
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE nombre = %s", (nombre,))
        row = cursor.fetchone()

        if row and check_password_hash(row['pass'], data['pass']):
            usuario = dict(row)
            usuario['pass'] = data['pass']  # se devuelve en texto plano solo para guardar la sesión local
            emit('auth_resultado', {'exito': True, 'usuario': usuario})
        else:
            emit('auth_resultado', {'exito': False, 'mensaje': 'Cuenta o contraseña incorrecta.'})

@socketio.on('actualizar_perfil')
def actualizar_perfil(data):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE id = %s", (data['id'],))
        row = cursor.fetchone()
        if not row:
            emit('perfil_actualizado', {'exito': False, 'mensaje': 'Usuario no encontrado.'})
            return

        nuevo_nombre = data['nombre']
        nueva_pass_hash = generate_password_hash(data['pass']) if data['pass'] else row['pass']
        nueva_pass_plana = data['pass'] if data['pass'] else None
        nueva_foto = data['foto']
        nuevo_fondo = data.get('fondoChat')
        nuevo_tema = data.get('tema', 'dark')
        nuevo_brillo = data.get('brilloFondo', 100)

        cursor.execute("""
            UPDATE usuarios
            SET nombre = %s, pass = %s, foto = %s, fondoChat = %s, tema = %s, brilloFondo = %s
            WHERE id = %s
        """, (nuevo_nombre, nueva_pass_hash, nueva_foto, nuevo_fondo, nuevo_tema, nuevo_brillo, data['id']))
        conn.commit()

        cursor.execute("SELECT * FROM usuarios WHERE id = %s", (data['id'],))
        u_updated = dict(cursor.fetchone())
        # Para mantener la sesión local funcionando, se devuelve la contraseña en texto
        # plano solo si el usuario la acaba de cambiar; si no, se conserva la que ya tenía el cliente.
        if nueva_pass_plana:
            u_updated['pass'] = nueva_pass_plana
        else:
            u_updated['pass'] = data.get('passActual', u_updated['pass'])
        emit('perfil_actualizado', {'exito': True, 'usuario': u_updated})

@socketio.on('crear_grupo')
def crear_grupo(data):
    grupo_id = "GRP_" + str(random.randint(10000000, 99999999))
    nombre = data['nombre']
    foto = data.get('foto')
    creador_id = data['creador_id']
    miembros = list(set(data.get('miembros', [])))

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO grupos (id, nombre, foto, creador_id) VALUES (%s, %s, %s, %s)",
                       (grupo_id, nombre, foto, creador_id))

        for m_id in miembros:
            cursor.execute("SELECT id FROM usuarios WHERE id = %s", (m_id,))
            if cursor.fetchone():
                aceptado = 1 if m_id == creador_id else 0
                cursor.execute(
                    "INSERT INTO miembros_grupo (grupo_id, usuario_id, aceptado) VALUES (%s, %s, %s) "
                    "ON CONFLICT (grupo_id, usuario_id) DO NOTHING",
                    (grupo_id, m_id, aceptado))
        conn.commit()

    join_room(grupo_id)
    emit('grupo_creado_resultado', {'exito': True, 'grupo_id': grupo_id})

@socketio.on('anadir_miembro_grupo')
def anadir_miembro_grupo(data):
    grupo_id = data['grupo_id']
    u_id = data['usuario_id']

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM usuarios WHERE id = %s", (u_id,))
        if not cursor.fetchone():
            emit('miembro_anadido_resultado', {'exito': False, 'mensaje': 'El usuario no existe.'})
            return

        cursor.execute(
            "INSERT INTO miembros_grupo (grupo_id, usuario_id, aceptado) VALUES (%s, %s, 0) "
            "ON CONFLICT (grupo_id, usuario_id) DO NOTHING",
            (grupo_id, u_id))
        conn.commit()

    emit('miembro_anadido_resultado', {'exito': True})

@socketio.on('obtener_detalles_grupo')
def obtener_detalles_grupo(data):
    grupo_id = data['grupo_id']
    miembros = []
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.nombre, u.foto
            FROM miembros_grupo mg
            JOIN usuarios u ON mg.usuario_id = u.id
            WHERE mg.grupo_id = %s
        """, (grupo_id,))
        miembros = [dict(r) for r in cursor.fetchall()]
    emit('detalles_grupo_cargados', {'miembros': miembros})

@socketio.on('actualizar_grupo')
def actualizar_grupo(data):
    grupo_id = data['grupo_id']
    nombre = data['nombre']
    foto = data.get('foto')
    with get_db() as conn:
        cursor = conn.cursor()
        if foto:
            cursor.execute("UPDATE grupos SET nombre = %s, foto = %s WHERE id = %s", (nombre, foto, grupo_id))
        else:
            cursor.execute("UPDATE grupos SET nombre = %s WHERE id = %s", (nombre, grupo_id))
        conn.commit()
    emit('grupo_actualizado', {'exito': True})

@socketio.on('aceptar_grupo')
def aceptar_grupo(data):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE miembros_grupo SET aceptado = 1 WHERE grupo_id = %s AND usuario_id = %s",
                       (data['grupo_id'], data['usuario_id']))
        conn.commit()
    join_room(data['grupo_id'])
    emit('grupo_aceptado', {'grupo_id': data['grupo_id']})

@socketio.on('salir_grupo')
def salir_grupo(data):
    grupo_id = data['grupo_id']
    usuario_id = data['usuario_id']
    leave_room(grupo_id)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM miembros_grupo WHERE grupo_id = %s AND usuario_id = %s",
                       (grupo_id, usuario_id))

        cursor.execute("SELECT COUNT(*) as total FROM miembros_grupo WHERE grupo_id = %s", (grupo_id,))
        count = cursor.fetchone()['total']

        if count == 0:
            cursor.execute("DELETE FROM grupos WHERE id = %s", (grupo_id,))
            cursor.execute("DELETE FROM mensajes WHERE clave_chat = %s AND es_grupo = 1", (grupo_id,))

        conn.commit()

    obtener_contactos({'id': usuario_id})

@socketio.on('eliminar_grupo_completo')
def eliminar_grupo_completo(data):
    grupo_id = data['grupo_id']
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM miembros_grupo WHERE grupo_id = %s", (grupo_id,))
        cursor.execute("DELETE FROM grupos WHERE id = %s", (grupo_id,))
        cursor.execute("DELETE FROM mensajes WHERE clave_chat = %s AND es_grupo = 1", (grupo_id,))
        conn.commit()

    emit('grupo_eliminado', room=grupo_id)

@socketio.on('obtener_contactos')
def obtener_contactos(data):
    mi_id = data['id']
    lista = []
    ids_agregados = set()

    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT u.id, u.nombre, u.foto
            FROM contactos c
            JOIN usuarios u ON c.contacto_id = u.id
            WHERE c.mi_id = %s
        """, (mi_id,))
        for r in cursor.fetchall():
            lista.append({'id': r['id'], 'nombre': r['nombre'], 'foto': r['foto'], 'esGuardado': True, 'esGrupo': False})
            ids_agregados.add(r['id'])

        cursor.execute("""
            SELECT DISTINCT emisor, receptor
            FROM mensajes
            WHERE (emisor = %s OR receptor = %s) AND es_grupo = 0
        """, (mi_id, mi_id))

        for r in cursor.fetchall():
            otro_id = r['receptor'] if r['emisor'] == mi_id else r['emisor']
            if otro_id not in ids_agregados:
                cursor.execute("SELECT id, nombre, foto FROM usuarios WHERE id = %s", (otro_id,))
                u = cursor.fetchone()
                if u:
                    lista.append({'id': u['id'], 'nombre': u['nombre'], 'foto': u['foto'], 'esGuardado': False, 'esGrupo': False})
                    ids_agregados.add(u['id'])

        cursor.execute("""
            SELECT g.id, g.nombre, g.foto, mg.aceptado
            FROM miembros_grupo mg
            JOIN grupos g ON mg.grupo_id = g.id
            WHERE mg.usuario_id = %s
        """, (mi_id,))
        for r in cursor.fetchall():
            lista.append({'id': r['id'], 'nombre': r['nombre'], 'foto': r['foto'], 'esGuardado': bool(r['aceptado']), 'esGrupo': True})

    emit('contactos_cargados', lista)

@socketio.on('guardar_contacto')
def guardar_contacto(data):
    mi_id = data['mi_id']
    contacto_id = data['contacto_id']

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM usuarios WHERE id = %s", (contacto_id,))
        if not cursor.fetchone():
            emit('contacto_resultado', {'exito': False, 'mensaje': 'El ID introducido no existe.'})
            return

        cursor.execute(
            "INSERT INTO contactos (mi_id, contacto_id) VALUES (%s, %s) ON CONFLICT (mi_id, contacto_id) DO NOTHING",
            (mi_id, contacto_id))
        conn.commit()

    emit('contacto_resultado', {'exito': True, 'mensaje': 'Contacto añadido.'})

@socketio.on('eliminar_contacto')
def eliminar_contacto(data):
    mi_id = data['mi_id']
    contacto_id = data['contacto_id']

    clave_chat = "_".join(sorted([mi_id, contacto_id]))

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM contactos WHERE mi_id = %s AND contacto_id = %s", (mi_id, contacto_id))
        cursor.execute("DELETE FROM mensajes WHERE clave_chat = %s AND es_grupo = 0", (clave_chat,))
        conn.commit()

    obtener_contactos({'id': mi_id})

@socketio.on('cargar_historial')
def cargar_historial(data):
    es_grupo = data.get('esGrupo', False)
    clave_chat = data['receptor'] if es_grupo else "_".join(sorted([data['emisor'], data['receptor']]))

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT emisor, receptor, texto, nombreEmisor, fotoEmisor FROM mensajes WHERE clave_chat = %s ORDER BY fecha ASC", (clave_chat,))
        historial = [dict(r) for r in cursor.fetchall()]

    emit('historial_cargado', historial)

@socketio.on('mensaje_enviado')
def manejar_mensaje(data):
    es_grupo = data.get('esGrupo', 0)
    clave_chat = data['receptor'] if es_grupo else "_".join(sorted([data['emisor'], data['receptor']]))

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO mensajes (clave_chat, emisor, receptor, texto, nombreEmisor, fotoEmisor, es_grupo)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (clave_chat, data['emisor'], data['receptor'], data['texto'], data['nombreEmisor'], data.get('fotoEmisor'), es_grupo))
        conn.commit()

        # Destinatarios de la notificación push: el otro usuario (chat privado)
        # o todos los miembros aceptados del grupo salvo quien envía (chat de grupo)
        if es_grupo:
            cursor.execute("SELECT usuario_id FROM miembros_grupo WHERE grupo_id = %s AND aceptado = 1", (data['receptor'],))
            destinatarios = [r['usuario_id'] for r in cursor.fetchall()]
        else:
            destinatarios = [data['receptor']]

    nuevo_msg = {
        'clave_chat': clave_chat,
        'emisor': data['emisor'],
        'receptor': data['receptor'],
        'texto': data['texto'],
        'nombreEmisor': data['nombreEmisor'],
        'fotoEmisor': data.get('fotoEmisor'),
        'esGrupo': es_grupo
    }

    if es_grupo:
        emit('recibir_mensaje', nuevo_msg, room=data['receptor'])
    else:
        emit('recibir_mensaje', nuevo_msg, room=data['emisor'])
        emit('recibir_mensaje', nuevo_msg, room=data['receptor'])

    # Notificación push real: llega aunque el destinatario tenga la pestaña
    # cerrada (siempre que el navegador la haya permitido y el SO no la bloquee).
    for dest_id in destinatarios:
        enviar_push_a_usuario(
            dest_id,
            data['emisor'],
            titulo=data['nombreEmisor'],
            cuerpo=data['texto'],
            url='/'
        )

@socketio.on('guardar_subscripcion_push')
def guardar_subscripcion_push(data):
    """El navegador envía aquí la suscripción push (endpoint + claves) tras
    pedir permiso de notificaciones, para poder avisar al usuario aunque
    tenga la pestaña cerrada."""
    usuario_id = data.get('usuario_id')
    sub = data.get('subscription')
    if not usuario_id or not sub:
        return

    endpoint = sub.get('endpoint')
    keys = sub.get('keys', {})
    p256dh = keys.get('p256dh')
    auth = keys.get('auth')
    if not endpoint or not p256dh or not auth:
        return

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO push_subscriptions (usuario_id, endpoint, p256dh, auth)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (endpoint) DO UPDATE
            SET usuario_id = EXCLUDED.usuario_id, p256dh = EXCLUDED.p256dh, auth = EXCLUDED.auth
        """, (usuario_id, endpoint, p256dh, auth))
        conn.commit()


@app.route('/service-worker.js')
def service_worker():
    js = """
self.addEventListener('push', function(event) {
    let data = {};
    try { data = event.data ? event.data.json() : {}; } catch (e) { data = {}; }
    const title = data.title || 'Arxechat';
    const options = {
        body: data.body || '',
        icon: data.icon || undefined,
        badge: data.badge || undefined,
        data: { url: data.url || '/' }
    };
    event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    const targetUrl = (event.notification.data && event.notification.data.url) || '/';
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
            for (const client of clientList) {
                if ('focus' in client) return client.focus();
            }
            if (clients.openWindow) return clients.openWindow(targetUrl);
        })
    );
});
"""
    return app.response_class(js, mimetype='application/javascript')


@app.route('/')
def home():
    return render_template_string(HTML_LAYOUT, vapid_public_key=VAPID_PUBLIC_KEY)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
