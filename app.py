import os
import random
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'arxechat_clave_secreta_123'

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', max_http_buffer_size=10 * 1024 * 1024)

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    if not DATABASE_URL:
        print("ADVERTENCIA: No se ha configurado DATABASE_URL.")
        return
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id TEXT PRIMARY KEY,
            nombre TEXT UNIQUE,
            pass TEXT,
            foto TEXT,
            fondoChat TEXT,
            tema TEXT DEFAULT 'dark',
            brilloFondo INTEGER DEFAULT 100,
            color_sent TEXT DEFAULT 'default',
            color_recv TEXT DEFAULT 'default'
        )
    ''')

    # Asegurar que existan las columnas nuevas si la tabla fue creada anteriormente
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS color_sent TEXT DEFAULT 'default'")
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS color_recv TEXT DEFAULT 'default'")

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
            leido INTEGER DEFAULT 0,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    cursor.close()
    conn.close()

if DATABASE_URL:
    init_db()

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
        .contact-item { display: flex; align-items: center; padding: 14px 16px; border-bottom: 1px solid var(--border-color); cursor: pointer; gap: 12px; background: transparent; width: 100%; border-left: none; border-right: none; border-top: none; text-align: left; color: var(--text-main); }
        .contact-item:hover, .contact-item:active { background: var(--bg-header); }
        .contact-info { display: flex; flex-direction: column; flex: 1; overflow: hidden; }
        .contact-name { font-weight: bold; font-size: 1rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .contact-id { font-size: 0.8rem; color: var(--text-sub); }
        .unread-badge { background: var(--accent); color: white; border-radius: 50%; padding: 2px 8px; font-size: 0.75rem; font-weight: bold; margin-left: 8px; flex-shrink: 0; }

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
        .attach-btn { background: var(--bg-input); border: none; color: var(--text-main); width: 42px; height: 42px; border-radius: 50%; font-size: 1.5rem; cursor: pointer; display: flex; justify-content: center; align-items: center; flex-shrink: 0; }
        .attach-btn:hover { background: var(--border-color); }
        .chat-input-area input[type="text"] { flex: 1; padding: 12px; background: var(--bg-input); border: none; border-radius: 8px; color: var(--text-main); outline: none; font-size: 1rem; }
        .chat-input-area button.send-btn { background: var(--accent); border: none; padding: 12px 20px; border-radius: 8px; color: white; font-weight: bold; cursor: pointer; font-size: 1rem; }
        
        @media (max-width: 768px) {
            .sidebar { width: 100%; }
            .chat-area { display: none; }
            .chat-area.active-mobile { display: flex; position: fixed; top:0; left:0; width:100%; height:100%; z-index:500; }
        }
    </style>
</head>
<body>

    <div class="modal-overlay" id="authModal" style="display:none;">
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
            <input type="text" id="personIdInput" placeholder="ID de 8 dígitos de la persona">
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
            <input type="text" id="groupMembersInput" placeholder="IDs de miembros (separados por comas)">
            <button type="button" class="btn-action" id="btnCrearGrupo" onclick="confirmarCrearGrupo()">Crear Grupo</button>
        </div>
    </div>

    <div class="modal-overlay" id="groupSettingsModal" style="display:none;">
        <div class="modal-box">
            <span class="close-btn" onclick="cerrarAjustesGrupo()">&times;</span>
            <h2>Opciones del Grupo</h2>
            
            <input type="text" id="editGroupName" placeholder="Nombre del grupo">
            <label class="file-label">Cambiar foto del grupo:</label>
            <input type="file" id="editGroupFoto" accept="image/*">
            <button type="button" class="btn-action" onclick="guardarInfoGrupo()">Guardar Nombre/Foto</button>
            
            <hr style="margin: 15px 0; border-color: var(--border-color);">
            <h3 style="font-size: 1rem; color: var(--accent); margin-bottom: 10px;">Miembros del Grupo</h3>
            <div id="groupMembersList"></div>

            <hr style="margin: 15px 0; border-color: var(--border-color);">
            <button type="button" class="btn-action btn-danger" onclick="eliminarChat()">Salir del Grupo</button>
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
            <div style="display:flex; gap:8px; align-items:center;">
                <input type="file" id="editFoto" accept="image/*" style="flex:1;">
                <button type="button" class="btn-action" style="width:auto; margin-top:0; padding:10px 14px; background:var(--bg-header); border:1px solid var(--accent); color:var(--accent);" onclick="abrirEditorImagen('foto')">Editar</button>
            </div>
            <div id="fotoEditedTag" style="font-size:0.75rem; color:var(--accent); display:none; text-align:left; margin-top:2px;">✓ Foto editada lista para guardar</div>

            <label class="file-label">Cambiar fondo de chat:</label>
            <div style="display:flex; gap:8px; align-items:center;">
                <input type="file" id="editFondoChat" accept="image/*" style="flex:1;">
                <button type="button" class="btn-action" style="width:auto; margin-top:0; padding:10px 14px; background:var(--bg-header); border:1px solid var(--accent); color:var(--accent);" onclick="abrirEditorImagen('fondo')">Editar</button>
            </div>
            <div id="fondoEditedTag" style="font-size:0.75rem; color:var(--accent); display:none; text-align:left; margin-top:2px;">✓ Fondo editado listo para guardar</div>

            <label class="file-label">Brillo / Intensidad del Fondo (<span id="brilloVal">100</span>%):</label>
            <div class="slider-container">
                <input type="range" id="editBrillo" min="10" max="100" value="100" oninput="document.getElementById('brilloVal').innerText = this.value">
            </div>

            <hr style="margin: 15px 0; border-color: var(--border-color);">
            <h3 style="font-size: 0.95rem; color: var(--accent); margin-bottom: 8px; text-align: left;">Color de mensajes</h3>

            <div style="text-align: left; margin-bottom: 10px;">
                <label class="file-label" style="margin-top:0;">Mis mensajes (Enviados):</label>
                <select id="editColorSentSelect" onchange="toggleColorInput('sent')">
                    <option value="default">Predeterminado (según tema)</option>
                    <option value="custom">Personalizado</option>
                </select>
                <input type="color" id="editColorSentInput" value="#005c4b" style="display:none; width:100%; height:38px; margin-top:5px; border:none; background:transparent; cursor:pointer;">
            </div>

            <div style="text-align: left; margin-bottom: 10px;">
                <label class="file-label" style="margin-top:0;">Mensajes recibidos:</label>
                <select id="editColorRecvSelect" onchange="toggleColorInput('recv')">
                    <option value="default">Predeterminado (según tema)</option>
                    <option value="custom">Personalizado</option>
                </select>
                <input type="color" id="editColorRecvInput" value="#202c33" style="display:none; width:100%; height:38px; margin-top:5px; border:none; background:transparent; cursor:pointer;">
            </div>

            <button type="button" class="btn-action" id="btnGuardarAjustes" onclick="guardarAjustes()">Guardar Cambios</button>
            <button type="button" class="btn-action btn-danger" onclick="cerrarSesion()">Cerrar Sesión</button>
        </div>
    </div>

    <!-- Modal Editor de Imagen (Estilo Canva / WhatsApp) -->
    <div class="modal-overlay" id="imageEditorModal" style="display:none;">
        <div class="modal-box" style="max-width:440px;">
            <span class="close-btn" onclick="cerrarEditorImagen()">&times;</span>
            <h2 id="editorTitle">Editar Imagen</h2>
            <div style="position:relative; width:300px; height:300px; margin:10px auto; background:#000; border-radius:8px; overflow:hidden; touch-action:none;" id="canvasContainer">
                <canvas id="editorCanvas" width="300" height="300" style="width:100%; height:100%; cursor:grab;"></canvas>
            </div>
            
            <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; margin-top:10px;">
                <div style="flex:1; text-align:left;">
                    <label style="font-size:0.8rem; color:var(--text-sub);">Zoom:</label>
                    <input type="range" id="editorZoomSlider" min="0.2" max="3" step="0.05" value="1" style="width:100%; accent-color:var(--accent);" oninput="onZoomSliderChange(this.value)">
                </div>
                <button type="button" id="rotateHoldBtn" title="Mantén pulsado para rotar" style="background:var(--bg-header); border:1px solid var(--accent); color:var(--accent); font-size:1.4rem; width:45px; height:45px; border-radius:50%; cursor:pointer; display:flex; justify-content:center; align-items:center; flex-shrink:0;">↻</button>
            </div>

            <button type="button" class="btn-action" onclick="confirmarEdicionImagen()">Aplicar Cambios</button>
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
                    <button type="button" class="attach-btn" onclick="document.getElementById('fileAttachmentInput').click()" title="Adjuntar archivo">+</button>
                    <input type="file" id="fileAttachmentInput" style="display:none;" onchange="manejarAdjunto(this)">
                    <input type="text" id="messageInput" placeholder="Escribe un mensaje..." autocomplete="off">
                    <button type="button" class="send-btn" onclick="sendMessage()">Enviar</button>
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

        // Variables del Editor de Imagen
        let editorTargetType = null; // 'foto' o 'fondo'
        let editorImg = new Image();
        let imgX = 150, imgY = 150;
        let imgScale = 1.0;
        let imgAngle = 0;
        let isDragging = false;
        let activeHandle = null;
        let dragStartX = 0, dragStartY = 0;
        let dragStartImgX = 0, dragStartImgY = 0;
        let rotateInterval = null;
        let editedFotoBase64 = null;
        let editedFondoBase64 = null;
        let cornerPoints = [];

        window.onload = () => {
            const sesionGuardada = localStorage.getItem('arxechat_sesion');
            if (sesionGuardada) {
                // Entrada directa inmediata sin pantalla de login
                document.getElementById('authModal').style.display = 'none';
                miUsuario = JSON.parse(sesionGuardada);
                iniciarApp();
                socket.emit('login_usuario', { nombre: miUsuario.nombre, pass: miUsuario.pass });
            } else {
                document.getElementById('authModal').style.display = 'flex';
            }
        };

        function aplicarTema() {
            if (miUsuario && miUsuario.tema === 'light') {
                document.body.classList.add('light-theme');
            } else {
                document.body.classList.remove('light-theme');
            }

            // Aplicar colores personalizados de mensajes
            if (miUsuario && miUsuario.color_sent && miUsuario.color_sent !== 'default') {
                document.documentElement.style.setProperty('--msg-sent', miUsuario.color_sent);
            } else {
                document.documentElement.style.removeProperty('--msg-sent');
            }

            if (miUsuario && miUsuario.color_recv && miUsuario.color_recv !== 'default') {
                document.documentElement.style.setProperty('--msg-recv', miUsuario.color_recv);
            } else {
                document.documentElement.style.removeProperty('--msg-recv');
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

        function solicitarPermisoNotificaciones() {
            if ("Notification" in window && Notification.permission === "default") {
                Notification.requestPermission();
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
        function abrirModalPersona() { cerrarModalChoice(); document.getElementById('addPersonModal').style.display = 'flex'; }
        function cerrarModalPersona() { document.getElementById('addPersonModal').style.display = 'none'; }
        function abrirModalGrupo() { cerrarModalChoice(); document.getElementById('addGroupModal').style.display = 'flex'; }
        function cerrarModalGrupo() { document.getElementById('addGroupModal').style.display = 'none'; }

        function confirmarAgregarPersona() {
            const idContacto = document.getElementById('personIdInput').value.trim();
            if(idContacto && idContacto.length === 8) {
                if(idContacto === miUsuario.id) return alert("No puedes añadirte a ti mismo.");
                socket.emit('guardar_contacto', { mi_id: miUsuario.id, contacto_id: idContacto });
                cerrarModalPersona();
                document.getElementById('personIdInput').value = '';
            } else {
                alert("El ID debe tener exactamente 8 dígitos.");
            }
        }

        async function confirmarCrearGrupo() {
            const nombre = document.getElementById('groupNameInput').value.trim();
            const rawMembers = document.getElementById('groupMembersInput').value.trim();
            if(!nombre) return alert("Introduce un nombre para el grupo.");
            
            const btn = document.getElementById('btnCrearGrupo');
            btn.innerText = "Creando...";
            btn.disabled = true;

            let fotoBase64 = null;
            const fileInput = document.getElementById('groupFotoInput');
            if(fileInput.files.length > 0) {
                fotoBase64 = await convertAndCompressBase64(fileInput.files[0]);
            }

            const miembros = rawMembers.split(',').map(m => m.trim()).filter(m => m.length === 8);
            miembros.push(miUsuario.id);

            socket.emit('crear_grupo', {
                nombre: nombre,
                foto: fotoBase64,
                creador_id: miUsuario.id,
                miembros: miembros
            });
        }

        socket.on('grupo_creado_resultado', (res) => {
            const btn = document.getElementById('btnCrearGrupo');
            btn.innerText = "Crear Grupo";
            btn.disabled = false;

            if(res.exito) {
                alert("¡Grupo creado con éxito!");
                cerrarModalGrupo();
                document.getElementById('groupNameInput').value = '';
                document.getElementById('groupMembersInput').value = '';
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
            seleccionarContacto({ id: id, nombre: nombre, foto: null, esGuardado: true, esGrupo: false, sinLeer: 0 });
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

        function toggleColorInput(type) {
            const select = document.getElementById(type === 'sent' ? 'editColorSentSelect' : 'editColorRecvSelect');
            const input = document.getElementById(type === 'sent' ? 'editColorSentInput' : 'editColorRecvInput');
            input.style.display = (select.value === 'custom') ? 'block' : 'none';
        }

        function abrirAjustes() {
            document.getElementById('editName').value = miUsuario.nombre;
            document.getElementById('editTheme').value = miUsuario.tema || 'dark';
            const brillo = miUsuario.brilloFondo !== undefined ? miUsuario.brilloFondo : 100;
            document.getElementById('editBrillo').value = brillo;
            document.getElementById('brilloVal').innerText = brillo;

            // Configurar selects de color de mensaje
            const cSent = miUsuario.color_sent || 'default';
            if (cSent !== 'default') {
                document.getElementById('editColorSentSelect').value = 'custom';
                document.getElementById('editColorSentInput').style.display = 'block';
                document.getElementById('editColorSentInput').value = cSent;
            } else {
                document.getElementById('editColorSentSelect').value = 'default';
                document.getElementById('editColorSentInput').style.display = 'none';
            }

            const cRecv = miUsuario.color_recv || 'default';
            if (cRecv !== 'default') {
                document.getElementById('editColorRecvSelect').value = 'custom';
                document.getElementById('editColorRecvInput').style.display = 'block';
                document.getElementById('editColorRecvInput').value = cRecv;
            } else {
                document.getElementById('editColorRecvSelect').value = 'default';
                document.getElementById('editColorRecvInput').style.display = 'none';
            }

            editedFotoBase64 = null;
            editedFondoBase64 = null;
            document.getElementById('fotoEditedTag').style.display = 'none';
            document.getElementById('fondoEditedTag').style.display = 'none';

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
            
            // Colores de mensaje
            let colorSent = 'default';
            if (document.getElementById('editColorSentSelect').value === 'custom') {
                colorSent = document.getElementById('editColorSentInput').value;
            }

            let colorRecv = 'default';
            if (document.getElementById('editColorRecvSelect').value === 'custom') {
                colorRecv = document.getElementById('editColorRecvInput').value;
            }

            // Foto de perfil
            const fileFoto = document.getElementById('editFoto');
            let nuevaFoto = miUsuario.foto;
            if (editedFotoBase64) {
                nuevaFoto = editedFotoBase64;
            } else if (fileFoto.files.length > 0) {
                nuevaFoto = await convertAndCompressBase64(fileFoto.files[0]);
            }

            // Fondo de chat
            const fileFondo = document.getElementById('editFondoChat');
            let nuevoFondo = miUsuario.fondoChat;
            if (editedFondoBase64) {
                nuevoFondo = editedFondoBase64;
            } else if (fileFondo.files.length > 0) {
                nuevoFondo = await convertAndCompressBase64(fileFondo.files[0]);
            }

            socket.emit('actualizar_perfil', { 
                id: miUsuario.id, 
                nombre: nuevoNombre, 
                pass: nuevaPass, 
                foto: nuevaFoto,
                fondoChat: nuevoFondo,
                tema: nuevoTema,
                brilloFondo: nuevoBrillo,
                color_sent: colorSent,
                color_recv: colorRecv
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

        /* --- LÓGICA DEL EDITOR DE IMAGEN --- */
        function abrirEditorImagen(tipo) {
            editorTargetType = tipo;
            const inputId = tipo === 'foto' ? 'editFoto' : 'editFondoChat';
            const fileInput = document.getElementById(inputId);

            document.getElementById('editorTitle').innerText = tipo === 'foto' ? 'Editar Foto de Perfil' : 'Editar Fondo de Chat';

            if (fileInput.files.length > 0) {
                const reader = new FileReader();
                reader.onload = (e) => cargarImagenEnEditor(e.target.result);
                reader.readAsDataURL(fileInput.files[0]);
            } else {
                const srcActual = tipo === 'foto' ? miUsuario.foto : miUsuario.fondoChat;
                if (srcActual) {
                    cargarImagenEnEditor(srcActual);
                } else {
                    alert("Selecciona un archivo primero o añade una imagen.");
                }
            }
        }

        function cargarImagenEnEditor(src) {
            editorImg = new Image();
            editorImg.crossOrigin = "anonymous";
            editorImg.onload = () => {
                imgX = 150;
                imgY = 150;
                imgScale = 1.0;
                imgAngle = 0;
                document.getElementById('editorZoomSlider').value = 1.0;
                document.getElementById('imageEditorModal').style.display = 'flex';
                initCanvasEvents();
                renderEditorCanvas();
            };
            editorImg.src = src;
        }

        function cerrarEditorImagen() {
            document.getElementById('imageEditorModal').style.display = 'none';
            if (rotateInterval) clearInterval(rotateInterval);
        }

        function onZoomSliderChange(val) {
            imgScale = parseFloat(val);
            renderEditorCanvas();
        }

        function initCanvasEvents() {
            const canvas = document.getElementById('editorCanvas');
            
            canvas.onmousedown = (e) => handleStart(e.clientX, e.clientY);
            canvas.onmousemove = (e) => handleMove(e.clientX, e.clientY);
            canvas.onmouseup = canvas.onmouseleave = () => handleEnd();

            canvas.ontouchstart = (e) => {
                if (e.touches.length === 1) {
                    handleStart(e.touches[0].clientX, e.touches[0].clientY);
                }
            };
            canvas.ontouchmove = (e) => {
                if (e.touches.length === 1) {
                    handleMove(e.touches[0].clientX, e.touches[0].clientY);
                }
            };
            canvas.ontouchend = () => handleEnd();

            // Configurar botón de rotación continua
            const rotateBtn = document.getElementById('rotateHoldBtn');
            
            const startRotate = () => {
                if (rotateInterval) clearInterval(rotateInterval);
                rotateInterval = setInterval(() => {
                    imgAngle = (imgAngle + 3) % 360;
                    renderEditorCanvas();
                }, 30);
            };

            const stopRotate = () => {
                if (rotateInterval) {
                    clearInterval(rotateInterval);
                    rotateInterval = null;
                }
            };

            rotateBtn.onmousedown = startRotate;
            rotateBtn.onmouseup = rotateBtn.onmouseleave = stopRotate;
            rotateBtn.ontouchstart = (e) => { e.preventDefault(); startRotate(); };
            rotateBtn.ontouchend = stopRotate;
        }

        function getCanvasPoint(clientX, clientY) {
            const canvas = document.getElementById('editorCanvas');
            const rect = canvas.getBoundingClientRect();
            return {
                x: (clientX - rect.left) * (300 / rect.width),
                y: (clientY - rect.top) * (300 / rect.height)
            };
        }

        function handleStart(clientX, clientY) {
            const pt = getCanvasPoint(clientX, clientY);
            
            // Comprobar si se hace clic en alguna esquina de las 4 para escalar
            activeHandle = null;
            for (let i = 0; i < cornerPoints.length; i++) {
                const dist = Math.hypot(pt.x - cornerPoints[i].x, pt.y - cornerPoints[i].y);
                if (dist < 20) {
                    activeHandle = i;
                    break;
                }
            }

            if (activeHandle !== null) {
                dragStartX = clientX;
                dragStartY = clientY;
            } else {
                isDragging = true;
                dragStartX = clientX;
                dragStartY = clientY;
                dragStartImgX = imgX;
                dragStartImgY = imgY;
            }
        }

        function handleMove(clientX, clientY) {
            if (activeHandle !== null) {
                const pt = getCanvasPoint(clientX, clientY);
                const distCenter = Math.hypot(pt.x - imgX, pt.y - imgY);
                const baseRadius = Math.hypot(editorImg.width / 2, editorImg.height / 2);
                if (baseRadius > 0) {
                    imgScale = Math.max(0.1, Math.min(4.0, distCenter / baseRadius));
                    document.getElementById('editorZoomSlider').value = imgScale;
                    renderEditorCanvas();
                }
            } else if (isDragging) {
                const pt = getCanvasPoint(clientX, clientY);
                const ptStart = getCanvasPoint(dragStartX, dragStartY);
                imgX = dragStartImgX + (pt.x - ptStart.x);
                imgY = dragStartImgY + (pt.y - ptStart.y);
                renderEditorCanvas();
            }
        }

        function handleEnd() {
            isDragging = false;
            activeHandle = null;
        }

        function renderEditorCanvas() {
            const canvas = document.getElementById('editorCanvas');
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, 300, 300);

            // Dibujar imagen con transformación
            ctx.save();
            ctx.translate(imgX, imgY);
            ctx.rotate((imgAngle * Math.PI) / 180);
            ctx.scale(imgScale, imgScale);
            ctx.drawImage(editorImg, -editorImg.width / 2, -editorImg.height / 2);
            ctx.restore();

            // Dibujar capa oscura con agujero (máscara)
            ctx.save();
            ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
            ctx.fillRect(0, 0, 300, 300);

            ctx.globalCompositeOperation = 'destination-out';
            ctx.beginPath();
            if (editorTargetType === 'foto') {
                ctx.arc(150, 150, 110, 0, Math.PI * 2);
            } else {
                ctx.rect(20, 20, 260, 260);
            }
            ctx.fill();
            ctx.restore();

            // Dibujar borde guía y los 4 puntos/asideros en las esquinas de la imagen
            ctx.save();
            ctx.strokeStyle = '#00a884';
            ctx.lineWidth = 2;
            ctx.beginPath();
            if (editorTargetType === 'foto') {
                ctx.arc(150, 150, 110, 0, Math.PI * 2);
            } else {
                ctx.rect(20, 20, 260, 260);
            }
            ctx.stroke();

            // Calcular las 4 esquinas transformadas
            const w = (editorImg.width * imgScale) / 2;
            const h = (editorImg.height * imgScale) / 2;
            const rad = (imgAngle * Math.PI) / 180;
            const cos = Math.cos(rad);
            const sin = Math.sin(rad);

            cornerPoints = [
                { x: imgX + (-w * cos - -h * sin), y: imgY + (-w * sin + -h * cos) },
                { x: imgX + (w * cos - -h * sin), y: imgY + (w * sin + -h * cos) },
                { x: imgX + (w * cos - h * sin), y: imgY + (w * sin + h * cos) },
                { x: imgX + (-w * cos - h * sin), y: imgY + (-w * sin + h * cos) }
            ];

            // Dibujar asideros en las 4 esquinas
            cornerPoints.forEach(pt => {
                ctx.beginPath();
                ctx.arc(pt.x, pt.y, 8, 0, Math.PI * 2);
                ctx.fillStyle = '#00a884';
                ctx.fill();
                ctx.strokeStyle = '#ffffff';
                ctx.lineWidth = 2;
                ctx.stroke();
            });
            ctx.restore();
        }

        function confirmarEdicionImagen() {
            const offCanvas = document.createElement('canvas');
            const size = editorTargetType === 'foto' ? 220 : 500;
            offCanvas.width = size;
            offCanvas.height = size;
            const ctx = offCanvas.getContext('2d');

            if (editorTargetType === 'foto') {
                ctx.beginPath();
                ctx.arc(size / 2, size / 2, size / 2, 0, Math.PI * 2);
                ctx.clip();
                
                const factor = size / 220; // relación del marco de 220px
                const offsetX = (imgX - 40) * factor;
                const offsetY = (imgY - 40) * factor;

                ctx.translate(offsetX, offsetY);
                ctx.rotate((imgAngle * Math.PI) / 180);
                ctx.scale(imgScale * factor, imgScale * factor);
                ctx.drawImage(editorImg, -editorImg.width / 2, -editorImg.height / 2);
            } else {
                const factor = size / 260;
                const offsetX = (imgX - 20) * factor;
                const offsetY = (imgY - 20) * factor;

                ctx.translate(offsetX, offsetY);
                ctx.rotate((imgAngle * Math.PI) / 180);
                ctx.scale(imgScale * factor, imgScale * factor);
                ctx.drawImage(editorImg, -editorImg.width / 2, -editorImg.height / 2);
            }

            const editedData = offCanvas.toDataURL('image/jpeg', 0.85);

            if (editorTargetType === 'foto') {
                editedFotoBase64 = editedData;
                document.getElementById('fotoEditedTag').style.display = 'block';
            } else {
                editedFondoBase64 = editedData;
                document.getElementById('fondoEditedTag').style.display = 'block';
            }

            cerrarEditorImagen();
        }

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
            
            misContactos.sort((a, b) => (b.sinLeer || 0) - (a.sinLeer || 0));

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

                const badgeHtml = (c.sinLeer && c.sinLeer > 0) ? `<span class="unread-badge">${c.sinLeer}</span>` : '';

                btn.innerHTML = `
                    ${avatarHtml}
                    <div class="contact-info">
                        <div class="contact-name">${c.nombre} ${etiqueta}</div>
                        <div class="contact-id">${c.esGrupo ? 'Grupo' : 'ID: ' + c.id}</div>
                    </div>
                    ${badgeHtml}
                `;
                listaDiv.appendChild(btn);
            });
        }

        function seleccionarContacto(c) {
            contactoActivo = c;
            c.sinLeer = 0;
            renderizarContactos();

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

        function eliminarChat() {
            if(contactoActivo && confirm(contactoActivo.esGrupo ? "¿Quieres salir de este grupo?" : "¿Quieres borrar este contacto y su conversación?")) {
                if(contactoActivo.esGrupo) {
                    socket.emit('salir_grupo', { usuario_id: miUsuario.id, grupo_id: contactoActivo.id });
                } else {
                    socket.emit('eliminar_contacto', { mi_id: miUsuario.id, contacto_id: contactoActivo.id });
                }
                document.getElementById('messages').innerHTML = '';
                document.getElementById('activeChatContainer').style.display = 'none';
                document.getElementById('emptyState').style.display = 'flex';
                if(window.innerWidth <= 768) {
                    document.getElementById('chatArea').classList.remove('active-mobile');
                }
            }
        }

        function formatearTextoConLinks(texto) {
            if (texto.startsWith('<img') || texto.startsWith('📁 <a')) {
                return texto;
            }
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
                avatarHtml = msg.fotoemisor || msg.fotoEmisor 
                    ? `<img src="${msg.fotoemisor || msg.fotoEmisor}" class="msg-avatar">`
                    : `<div class="msg-avatar">${(msg.nombreemisor || msg.nombreEmisor || '?').charAt(0).toUpperCase()}</div>`;
            }

            const msgElement = document.createElement('div');
            msgElement.className = `message ${esMio ? 'sent' : 'received'}`;

            let senderHeader = '';
            if(!esMio && contactoActivo.esGrupo) {
                senderHeader = `<span class="sender-name">${msg.nombreemisor || msg.nombreEmisor || 'Usuario'}</span>`;
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
            const esDelChatActivo = contactoActivo && (
                (contactoActivo.esGrupo && data.receptor === contactoActivo.id) ||
                (!contactoActivo.esGrupo && (data.emisor === contactoActivo.id || (data.emisor === miUsuario.id && data.receptor === contactoActivo.id)))
            );

            if (esDelChatActivo) {
                renderizarMensaje(data);
                if (data.emisor !== miUsuario.id) {
                    socket.emit('marcar_leido', { emisor: miUsuario.id, receptor: contactoActivo.id, esGrupo: contactoActivo.esGrupo });
                }
            } else {
                socket.emit('obtener_contactos', { id: miUsuario.id });
            }

            if (data.emisor !== miUsuario.id && Notification.permission === "granted") {
                let prevText = data.texto;
                if(prevText.startsWith('<img')) prevText = '📷 Foto adjunta';
                else if(prevText.startsWith('📁 <a')) prevText = '📁 Archivo adjunto';
                new Notification("Mensaje de " + (data.nombreEmisor || data.nombreemisor), { body: prevText });
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
                    esGrupo: contactoActivo.esGrupo ? 1 : 0,
                    texto: texto
                });
                input.value = '';
            }
        }

        async function manejarAdjunto(input) {
            if (!input.files || input.files.length === 0 || !contactoActivo) return;
            const file = input.files[0];
            
            if (file.size > 8 * 1024 * 1024) {
                alert("El archivo supera el límite de 8 MB.");
                input.value = '';
                return;
            }

            let mensajeContenido = '';

            if (file.type.startsWith('image/')) {
                const imgBase64 = await convertAndCompressBase64(file);
                mensajeContenido = `<img src="${imgBase64}" style="max-width: 100%; border-radius: 8px; margin-top: 5px; display: block;">`;
            } else {
                const reader = new FileReader();
                reader.readAsDataURL(file);
                reader.onload = () => {
                    const base64Data = reader.result;
                    mensajeContenido = `📁 <a href="${base64Data}" download="${file.name}" style="color:var(--link-color); text-decoration:underline; font-weight:bold;">${file.name}</a>`;
                    enviarMensajeAdjunto(mensajeContenido);
                    input.value = '';
                };
                return;
            }

            enviarMensajeAdjunto(mensajeContenido);
            input.value = '';
        }

        function enviarMensajeAdjunto(texto) {
            if (contactoActivo) {
                socket.emit('mensaje_enviado', {
                    emisor: miUsuario.id,
                    nombreEmisor: miUsuario.nombre,
                    fotoEmisor: miUsuario.foto,
                    receptor: contactoActivo.id,
                    esGrupo: contactoActivo.esGrupo ? 1 : 0,
                    texto: texto
                });
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
    from flask_socketio import join_room
    join_room(data['id'])
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT grupo_id FROM miembros_grupo WHERE usuario_id = %s", (data['id'],))
    for r in cursor.fetchall():
        join_room(r['grupo_id'])
    cursor.close()
    conn.close()

@socketio.on('registrar_usuario')
def registrar(data):
    nombre = data['nombre']
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM usuarios WHERE nombre = %s", (nombre,))
    row = cursor.fetchone()
    
    if row:
        nuevo_id = row['id']
        cursor.execute("UPDATE usuarios SET pass = %s, foto = %s WHERE id = %s", (data['pass'], data.get('foto'), nuevo_id))
    else:
        nuevo_id = str(random.randint(10000000, 99999999))
        cursor.execute(
            "INSERT INTO usuarios (id, nombre, pass, foto, fondoChat, tema, brilloFondo, color_sent, color_recv) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (nuevo_id, nombre, data['pass'], data.get('foto'), None, 'dark', 100, 'default', 'default')
        )
    conn.commit()
    
    cursor.execute("SELECT * FROM usuarios WHERE id = %s", (nuevo_id,))
    nuevo_usuario = dict(cursor.fetchone())
    cursor.close()
    conn.close()

    emit('auth_resultado', {'exito': True, 'usuario': nuevo_usuario})

@socketio.on('login_usuario')
def login(data):
    nombre = data['nombre']
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE nombre = %s", (nombre,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if row and row['pass'] == data['pass']:
        usuario = dict(row)
        emit('auth_resultado', {'exito': True, 'usuario': usuario})
    else:
        emit('auth_resultado', {'exito': False, 'mensaje': 'Cuenta o contraseña incorrecta.'})

@socketio.on('actualizar_perfil')
def actualizar_perfil(data):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = %s", (data['id'],))
    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        emit('perfil_actualizado', {'exito': False, 'mensaje': 'Usuario no encontrado.'})
        return

    nuevo_nombre = data['nombre']
    nueva_pass = data['pass'] if data['pass'] else row['pass']
    nueva_foto = data['foto']
    nuevo_fondo = data.get('fondoChat')
    nuevo_tema = data.get('tema', 'dark')
    nuevo_brillo = data.get('brilloFondo', 100)
    nuevo_color_sent = data.get('color_sent', 'default')
    nuevo_color_recv = data.get('color_recv', 'default')

    cursor.execute("""
        UPDATE usuarios 
        SET nombre = %s, pass = %s, foto = %s, fondoChat = %s, tema = %s, brilloFondo = %s, color_sent = %s, color_recv = %s 
        WHERE id = %s
    """, (nuevo_nombre, nueva_pass, nueva_foto, nuevo_fondo, nuevo_tema, nuevo_brillo, nuevo_color_sent, nuevo_color_recv, data['id']))
    conn.commit()

    cursor.execute("SELECT * FROM usuarios WHERE id = %s", (data['id'],))
    u_updated = dict(cursor.fetchone())
    cursor.close()
    conn.close()
    
    emit('perfil_actualizado', {'exito': True, 'usuario': u_updated})

@socketio.on('crear_grupo')
def crear_grupo(data):
    from flask_socketio import join_room
    grupo_id = "GRP_" + str(random.randint(10000000, 99999999))
    nombre = data['nombre']
    foto = data.get('foto')
    creador_id = data['creador_id']
    miembros = list(set(data.get('miembros', [])))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO grupos (id, nombre, foto, creador_id) VALUES (%s, %s, %s, %s)",
                   (grupo_id, nombre, foto, creador_id))
    
    for m_id in miembros:
        cursor.execute("SELECT id FROM usuarios WHERE id = %s", (m_id,))
        if cursor.fetchone():
            aceptado = 1 if m_id == creador_id else 0
            cursor.execute("INSERT INTO miembros_grupo (grupo_id, usuario_id, aceptado) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                           (grupo_id, m_id, aceptado))
    conn.commit()
    cursor.close()
    conn.close()

    join_room(grupo_id)
    emit('grupo_creado_resultado', {'exito': True, 'grupo_id': grupo_id})

@socketio.on('obtener_detalles_grupo')
def obtener_detalles_grupo(data):
    grupo_id = data['grupo_id']
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.nombre, u.foto 
        FROM miembros_grupo mg 
        JOIN usuarios u ON mg.usuario_id = u.id 
        WHERE mg.grupo_id = %s
    """, (grupo_id,))
    miembros = [dict(r) for r in cursor.fetchall()]
    cursor.close()
    conn.close()
    emit('detalles_grupo_cargados', {'miembros': miembros})

@socketio.on('actualizar_grupo')
def actualizar_grupo(data):
    grupo_id = data['grupo_id']
    nombre = data['nombre']
    foto = data.get('foto')
    conn = get_db()
    cursor = conn.cursor()
    if foto:
        cursor.execute("UPDATE grupos SET nombre = %s, foto = %s WHERE id = %s", (nombre, foto, grupo_id))
    else:
        cursor.execute("UPDATE grupos SET nombre = %s WHERE id = %s", (nombre, grupo_id))
    conn.commit()
    cursor.close()
    conn.close()
    emit('grupo_actualizado', {'exito': True})

@socketio.on('aceptar_grupo')
def aceptar_grupo(data):
    from flask_socketio import join_room
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE miembros_grupo SET aceptado = 1 WHERE grupo_id = %s AND usuario_id = %s",
                   (data['grupo_id'], data['usuario_id']))
    conn.commit()
    cursor.close()
    conn.close()
    join_room(data['grupo_id'])
    emit('grupo_aceptado', {'grupo_id': data['grupo_id']})

@socketio.on('salir_grupo')
def salir_grupo(data):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM miembros_grupo WHERE grupo_id = %s AND usuario_id = %s",
                   (data['grupo_id'], data['usuario_id']))
    conn.commit()
    cursor.close()
    conn.close()
    obtener_contactos({'id': data['usuario_id']})

@socketio.on('obtener_contactos')
def obtener_contactos(data):
    mi_id = data['id']
    lista = []
    ids_agregados = set()

    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT u.id, u.nombre, u.foto 
        FROM contactos c 
        JOIN usuarios u ON c.contacto_id = u.id 
        WHERE c.mi_id = %s
    """, (mi_id,))
    for r in cursor.fetchall():
        clave = "_".join(sorted([mi_id, r['id']]))
        cursor.execute("SELECT COUNT(*) as unread FROM mensajes WHERE clave_chat = %s AND emisor != %s AND leido = 0", (clave, mi_id))
        unread = cursor.fetchone()['unread']
        lista.append({'id': r['id'], 'nombre': r['nombre'], 'foto': r['foto'], 'esGuardado': True, 'esGrupo': False, 'sinLeer': unread})
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
                clave = "_".join(sorted([mi_id, u['id']]))
                cursor.execute("SELECT COUNT(*) as unread FROM mensajes WHERE clave_chat = %s AND emisor != %s AND leido = 0", (clave, mi_id))
                unread = cursor.fetchone()['unread']
                lista.append({'id': u['id'], 'nombre': u['nombre'], 'foto': u['foto'], 'esGuardado': False, 'esGrupo': False, 'sinLeer': unread})
                ids_agregados.add(u['id'])

    cursor.execute("""
        SELECT g.id, g.nombre, g.foto, mg.aceptado 
        FROM miembros_grupo mg 
        JOIN grupos g ON mg.grupo_id = g.id 
        WHERE mg.usuario_id = %s
    """, (mi_id,))
    for r in cursor.fetchall():
        cursor.execute("SELECT COUNT(*) as unread FROM mensajes WHERE clave_chat = %s AND emisor != %s AND leido = 0", (r['id'], mi_id))
        unread = cursor.fetchone()['unread']
        lista.append({'id': r['id'], 'nombre': r['nombre'], 'foto': r['foto'], 'esGuardado': bool(r['aceptado']), 'esGrupo': True, 'sinLeer': unread})

    cursor.close()
    conn.close()
    emit('contactos_cargados', lista)

@socketio.on('guardar_contacto')
def guardar_contacto(data):
    mi_id = data['mi_id']
    contacto_id = data['contacto_id']

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM usuarios WHERE id = %s", (contacto_id,))
    if not cursor.fetchone():
        cursor.close()
        conn.close()
        emit('contacto_resultado', {'exito': False, 'mensaje': 'El ID introducido no existe.'})
        return

    cursor.execute("INSERT INTO contactos (mi_id, contacto_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (mi_id, contacto_id))
    conn.commit()
    cursor.close()
    conn.close()

    emit('contacto_resultado', {'exito': True, 'mensaje': 'Contacto añadido.'})

@socketio.on('eliminar_contacto')
def eliminar_contacto(data):
    mi_id = data['mi_id']
    contacto_id = data['contacto_id']

    clave_chat = "_".join(sorted([mi_id, contacto_id]))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM contactos WHERE mi_id = %s AND contacto_id = %s", (mi_id, contacto_id))
    cursor.execute("DELETE FROM mensajes WHERE clave_chat = %s AND es_grupo = 0", (clave_chat,))
    conn.commit()
    cursor.close()
    conn.close()

    obtener_contactos({'id': mi_id})

@socketio.on('cargar_historial')
def cargar_historial(data):
    es_grupo = data.get('esGrupo', False)
    clave_chat = data['receptor'] if es_grupo else "_".join(sorted([data['emisor'], data['receptor']]))
    mi_id = data['emisor']
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE mensajes SET leido = 1 WHERE clave_chat = %s AND emisor != %s", (clave_chat, mi_id))
    conn.commit()
    
    cursor.execute("SELECT emisor, receptor, texto, nombreEmisor, fotoEmisor FROM mensajes WHERE clave_chat = %s ORDER BY fecha ASC", (clave_chat,))
    historial = [dict(r) for r in cursor.fetchall()]
    cursor.close()
    conn.close()

    emit('historial_cargado', historial)
    obtener_contactos({'id': mi_id})

@socketio.on('marcar_leido')
def marcar_leido(data):
    es_grupo = data.get('esGrupo', False)
    clave_chat = data['receptor'] if es_grupo else "_".join(sorted([data['emisor'], data['receptor']]))
    mi_id = data['emisor']
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE mensajes SET leido = 1 WHERE clave_chat = %s AND emisor != %s", (clave_chat, mi_id))
    conn.commit()
    cursor.close()
    conn.close()
    obtener_contactos({'id': mi_id})

@socketio.on('mensaje_enviado')
def manejar_mensaje(data):
    es_grupo = data.get('esGrupo', 0)
    clave_chat = data['receptor'] if es_grupo else "_".join(sorted([data['emisor'], data['receptor']]))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO mensajes (clave_chat, emisor, receptor, texto, nombreEmisor, fotoEmisor, es_grupo, leido)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 0)
    """, (clave_chat, data['emisor'], data['receptor'], data['texto'], data['nombreEmisor'], data.get('fotoEmisor'), es_grupo))
    conn.commit()
    cursor.close()
    conn.close()

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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
