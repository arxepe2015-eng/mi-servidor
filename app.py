import os
import json
import random
import uuid
from datetime import datetime

import psycopg2
import psycopg2.extras
from flask import Flask, render_template_string, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from pywebpush import webpush, WebPushException

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "arxechat_dev_change_me")

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    max_http_buffer_size=50 * 1024 * 1024,
)

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Falta DATABASE_URL en las variables de entorno de Render.")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_CLAIMS_EMAIL = os.environ.get("VAPID_CLAIMS_EMAIL", "mailto:admin@example.com")

MAX_FILE_BYTES = 20 * 1024 * 1024


def get_db():
    return psycopg2.connect(
        DATABASE_URL,
        sslmode="require",
        cursor_factory=psycopg2.extras.RealDictCursor,
        connect_timeout=15,
    )


def init_db():
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id TEXT PRIMARY KEY,
                nombre TEXT UNIQUE NOT NULL,
                pass TEXT NOT NULL,
                foto TEXT,
                fondoChat TEXT,
                tema TEXT DEFAULT 'dark',
                brilloFondo INTEGER DEFAULT 100
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS contactos (
                mi_id TEXT NOT NULL,
                contacto_id TEXT NOT NULL,
                PRIMARY KEY (mi_id, contacto_id)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS grupos (
                id TEXT PRIMARY KEY,
                nombre TEXT NOT NULL,
                foto TEXT,
                creador_id TEXT NOT NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS miembros_grupo (
                grupo_id TEXT NOT NULL,
                usuario_id TEXT NOT NULL,
                aceptado INTEGER DEFAULT 0,
                PRIMARY KEY (grupo_id, usuario_id)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS mensajes (
                id BIGSERIAL PRIMARY KEY,
                clave_chat TEXT NOT NULL,
                emisor TEXT NOT NULL,
                receptor TEXT NOT NULL,
                texto TEXT DEFAULT '',
                nombreEmisor TEXT,
                fotoEmisor TEXT,
                es_grupo INTEGER DEFAULT 0,
                fecha TIMESTAMP DEFAULT NOW(),
                tipo TEXT DEFAULT 'texto',
                archivo_nombre TEXT,
                archivo_tipo TEXT,
                archivo_tamano BIGINT,
                archivo_data TEXT,
                responde_a BIGINT NULL
            )
        """)

        # Migración segura de instalaciones antiguas.
        for statement in [
            "ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS tipo TEXT DEFAULT 'texto'",
            "ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS archivo_nombre TEXT",
            "ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS archivo_tipo TEXT",
            "ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS archivo_tamano BIGINT",
            "ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS archivo_data TEXT",
            "ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS responde_a BIGINT NULL",
        ]:
            cur.execute(statement)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id BIGSERIAL PRIMARY KEY,
                usuario_id TEXT NOT NULL,
                endpoint TEXT UNIQUE NOT NULL,
                p256dh TEXT NOT NULL,
                auth TEXT NOT NULL
            )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_mensajes_chat_fecha ON mensajes(clave_chat, fecha, id)")
        conn.commit()


init_db()


def safe_user(row):
    if not row:
        return None
    user = dict(row)
    user.pop("pass", None)
    return user


def message_dict(row):
    result = dict(row)
    if isinstance(result.get("fecha"), datetime):
        result["fecha"] = result["fecha"].isoformat()
    return result


def make_chat_key(a, b):
    return "_".join(sorted([str(a), str(b)]))


def notify_user(user_id, sender_id, title, body):
    if user_id == sender_id or not VAPID_PUBLIC_KEY or not VAPID_PRIVATE_KEY:
        return

    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, endpoint, p256dh, auth FROM push_subscriptions WHERE usuario_id=%s",
                (user_id,),
            )
            subs = cur.fetchall()

            payload = json.dumps({
                "title": title or "Arxechat",
                "body": body or "Nuevo mensaje",
                "url": "/",
            })

            for sub in subs:
                try:
                    webpush(
                        subscription_info={
                            "endpoint": sub["endpoint"],
                            "keys": {
                                "p256dh": sub["p256dh"],
                                "auth": sub["auth"],
                            },
                        },
                        data=payload,
                        vapid_private_key=VAPID_PRIVATE_KEY,
                        vapid_claims={"sub": VAPID_CLAIMS_EMAIL},
                    )
                except WebPushException as exc:
                    status = getattr(exc.response, "status_code", None)
                    if status in (404, 410):
                        cur.execute(
                            "DELETE FROM push_subscriptions WHERE id=%s",
                            (sub["id"],),
                        )
            conn.commit()
    except Exception as exc:
        app.logger.warning("Push no enviado: %s", exc)


HTML_LAYOUT = r"""
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#111b21">
<title>Arxechat</title>
<script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
<style>
:root{
 --bg:#0b141a;--panel:#111b21;--header:#202c33;--input:#2a3942;
 --text:#e9edef;--muted:#8696a0;--accent:#00a884;--sent:#005c4b;
 --recv:#202c33;--border:#26343d;--link:#53bdeb;
}
body.light{--bg:#e9edef;--panel:#fff;--header:#f0f2f5;--input:#fff;
 --text:#111b21;--muted:#667781;--accent:#008069;--sent:#d9fdd3;--recv:#fff;--border:#e5e7e9}
*{box-sizing:border-box}
html,body{margin:0;width:100%;height:100%;overflow:hidden}
body{font-family:Segoe UI,Tahoma,sans-serif;background:var(--bg);color:var(--text)}
button,input,select{font:inherit}
button{cursor:pointer}
.hidden{display:none!important}
.app{height:100dvh;width:100%;display:flex}
.sidebar{width:360px;min-width:280px;border-right:1px solid var(--border);background:var(--panel);display:flex;flex-direction:column}
.side-head,.chat-head{height:64px;background:var(--header);display:flex;align-items:center;padding:8px 12px;gap:10px}
.profile-btn{border:0;background:none;color:var(--text);display:flex;align-items:center;gap:9px;min-width:0;text-align:left}
.avatar{width:42px;height:42px;border-radius:50%;object-fit:cover;background:#667781;color:white;display:grid;place-items:center;font-weight:700;flex:none}
.head-actions{margin-left:auto;display:flex;gap:7px}
.circle{width:40px;height:40px;border:0;border-radius:50%;background:var(--accent);color:#fff;font-size:22px}
.contacts{flex:1;overflow:auto}
.contact{width:100%;border:0;border-bottom:1px solid var(--border);background:transparent;color:var(--text);padding:11px 13px;display:flex;gap:12px;text-align:left;align-items:center}
.contact:hover{background:var(--header)}
.contact.active{background:var(--header)}
.contact-info{min-width:0;flex:1}
.contact-name{font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.contact-sub{font-size:12px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chat{flex:1;min-width:0;display:flex;flex-direction:column;background:var(--bg)}
.chat-head{flex:none}
.back{display:none;border:0;background:none;color:var(--text);font-size:27px;padding:4px}
.chat-title{min-width:0}.chat-title b{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chat-title span{font-size:12px;color:var(--muted)}
.messages-wrap{position:relative;flex:1;min-height:0;overflow:hidden}
.bg{position:absolute;inset:0;background-size:cover;background-position:center;opacity:.2}
.messages{position:relative;height:100%;overflow:auto;padding:18px 6%;display:flex;flex-direction:column;gap:7px}
.row{display:flex;max-width:min(78%,720px);gap:6px;align-items:flex-end}
.row.me{align-self:flex-end;flex-direction:row-reverse}
.row.other{align-self:flex-start}
.bubble{background:var(--recv);padding:7px 9px;border-radius:9px;line-height:1.4;overflow:hidden;box-shadow:0 1px 1px #0002}
.me .bubble{background:var(--sent)}
.sender{font-size:12px;font-weight:700;color:var(--accent);margin-bottom:3px}
.reply-preview{border-left:3px solid var(--accent);background:#0002;padding:5px 7px;margin-bottom:5px;border-radius:4px;font-size:12px;color:var(--muted)}
.time{font-size:10px;color:var(--muted);float:right;margin:7px 0 0 10px}
.msg-text{white-space:pre-wrap;word-break:break-word}
.msg-text a{color:var(--link)}
.msg-image{display:block;max-width:360px;max-height:360px;border-radius:7px;object-fit:contain}
.file-card{display:flex;align-items:center;gap:9px;min-width:190px}
.file-icon{font-size:27px}.file-name{font-weight:700;word-break:break-word}.file-size{font-size:11px;color:var(--muted)}
.msg-tools{display:none;gap:3px;margin-top:3px}
.bubble:hover .msg-tools{display:flex}
.tool{border:0;background:transparent;color:var(--muted);font-size:12px}
.composer{background:var(--header);padding:8px max(10px,3vw) calc(8px + env(safe-area-inset-bottom));display:flex;gap:7px;align-items:flex-end}
.composer input{flex:1;min-width:0;border:0;border-radius:9px;background:var(--input);color:var(--text);padding:12px;outline:none}
.icon-btn{border:0;background:transparent;color:var(--muted);font-size:23px;padding:8px}
.send{border:0;border-radius:9px;background:var(--accent);color:white;padding:11px 16px;font-weight:700}
.reply-bar{position:absolute;bottom:0;left:0;right:0;background:var(--header);border-left:4px solid var(--accent);padding:8px 45px 8px 10px;z-index:3}
.reply-close{position:absolute;right:8px;top:8px;background:none;border:0;color:var(--muted);font-size:20px}
.file-input{display:none}
.overlay{position:fixed;inset:0;background:#0009;display:grid;place-items:center;z-index:20;padding:15px}
.modal{width:min(440px,100%);max-height:90dvh;overflow:auto;background:var(--panel);border-radius:12px;padding:20px}
.modal h2{margin:0 0 14px}.modal input,.modal select{width:100%;margin:6px 0;padding:11px;border:1px solid var(--border);border-radius:7px;background:var(--input);color:var(--text)}
.modal button.action{width:100%;margin-top:8px;padding:11px;border:0;border-radius:7px;background:var(--accent);color:#fff;font-weight:700}
.modal button.danger{background:#d33}
.close{float:right;background:none;border:0;color:var(--muted);font-size:25px}
.notice{padding:8px 12px;color:var(--muted);font-size:12px}
.auth{z-index:30}.auth .modal{text-align:center}
.error{color:#ef5350;font-size:13px;min-height:18px}
.preview{font-size:12px;color:var(--muted);padding:5px}
@media(max-width:900px){
 .sidebar{width:320px}
 .row{max-width:85%}
}
@media(max-width:700px){
 .sidebar{width:100%;min-width:0}
 .chat{display:none;position:fixed;inset:0;z-index:5}
 .chat.mobile-open{display:flex}
 .back{display:block}
 .messages{padding:12px 3%}
 .row{max-width:91%}
 .msg-image{max-width:72vw;max-height:45vh}
 .composer{padding-left:7px;padding-right:7px}
 .send{padding:11px 13px}
}
@media(min-width:701px){.mobile-only{display:none!important}}
</style>
</head>
<body>
<div id="auth" class="overlay auth">
 <div class="modal">
  <h2 id="authTitle">Iniciar sesión</h2>
  <input id="authName" placeholder="Nombre de usuario" autocomplete="username">
  <input id="authPass" type="password" placeholder="Contraseña" autocomplete="current-password">
  <input id="authPass2" type="password" placeholder="Repite la contraseña" class="hidden">
  <input id="authPhoto" type="file" accept="image/*" class="hidden">
  <div id="authError" class="error"></div>
  <button class="action" id="authButton">Entrar</button>
  <button class="action" id="authToggle" style="background:transparent;color:var(--accent)">Crear una cuenta</button>
 </div>
</div>

<div id="addModal" class="overlay hidden">
 <div class="modal">
  <button class="close" onclick="closeModal('addModal')">×</button>
  <h2>Añadir</h2>
  <input id="personInput" placeholder="ID de 8 dígitos o nombre">
  <button class="action" onclick="addPerson()">Añadir persona</button>
  <hr>
  <input id="groupName" placeholder="Nombre del grupo">
  <input id="groupMembers" placeholder="IDs separados por comas">
  <input id="groupPhoto" type="file" accept="image/*">
  <button class="action" onclick="createGroup()">Crear grupo</button>
 </div>
</div>

<div id="settingsModal" class="overlay hidden">
 <div class="modal">
  <button class="close" onclick="closeModal('settingsModal')">×</button>
  <h2>Ajustes</h2>
  <div id="myIdText" class="notice"></div>
  <input id="editName" placeholder="Nombre">
  <input id="editPass" type="password" placeholder="Nueva contraseña (opcional)">
  <select id="editTheme"><option value="dark">Oscuro</option><option value="light">Claro</option></select>
  <input id="editPhoto" type="file" accept="image/*">
  <input id="editBg" type="file" accept="image/*">
  <label>Intensidad del fondo</label>
  <input id="editBrightness" type="range" min="10" max="100" value="100">
  <button class="action" onclick="saveSettings()">Guardar</button>
  <button class="action danger" onclick="logout()">Cerrar sesión</button>
 </div>
</div>

<div id="app" class="app hidden">
 <aside class="sidebar">
  <div class="side-head">
   <button class="profile-btn" onclick="openSettings()">
    <img id="myImg" class="avatar hidden">
    <div id="myAvatar" class="avatar">U</div>
    <div style="min-width:0"><b id="myName">Usuario</b><div id="myId" style="font-size:11px;color:var(--accent)"></div></div>
   </button>
   <div class="head-actions">
    <button class="circle" onclick="openModal('addModal')">+</button>
   </div>
  </div>
  <div class="notice" id="connection">Conectando…</div>
  <div id="contacts" class="contacts"></div>
 </aside>

 <main id="chat" class="chat">
  <div class="chat-head">
   <button class="back mobile-only" onclick="closeChat()">‹</button>
   <img id="activeImg" class="avatar hidden">
   <div id="activeAvatar" class="avatar">?</div>
   <div class="chat-title"><b id="activeName">Selecciona un chat</b><span id="activeStatus"></span></div>
  </div>
  <div class="messages-wrap">
   <div id="bg" class="bg"></div>
   <div id="messages" class="messages">
    <div class="notice" style="margin:auto;text-align:center">Selecciona una conversación para empezar.</div>
   </div>
   <div id="replyBar" class="reply-bar hidden">
    <button class="reply-close" onclick="cancelReply()">×</button>
    <b>Respondiendo a <span id="replyName"></span></b>
    <div id="replyText" class="preview"></div>
   </div>
  </div>
  <div class="composer">
   <button class="icon-btn" title="Adjuntar" onclick="document.getElementById('fileInput').click()">📎</button>
   <input id="fileInput" type="file" class="file-input" accept="image/*,.pdf,.txt,.doc,.docx,.xls,.xlsx,.zip,.rar" onchange="prepareFile()">
   <input id="messageInput" placeholder="Escribe un mensaje…" autocomplete="off">
   <button class="send" onclick="sendMessage()">Enviar</button>
  </div>
 </main>
</div>

<script>
const socket = io({transports:['websocket','polling'],reconnection:true,reconnectionAttempts:Infinity,reconnectionDelay:500,reconnectionDelayMax:5000});
const VAPID_PUBLIC_KEY = "{{ vapid_public_key }}";
let user=null, contacts=[], active=null, replyTo=null, pendingFile=null, authRegister=false;
let renderedIds=new Set(), historyRequestToken=0;

const $=id=>document.getElementById(id);
function openModal(id){$(id).classList.remove('hidden')}
function closeModal(id){$(id).classList.add('hidden')}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]))}
function formatBytes(n){if(!n)return '';const u=['B','KB','MB','GB'];let i=0,x=n;while(x>=1024&&i<3){x/=1024;i++}return x.toFixed(i?1:0)+' '+u[i]}
function avatarHTML(c, cls='avatar'){return c.foto?`<img class="${cls}" src="${esc(c.foto)}">`:`<div class="${cls}">${esc((c.nombre||'?')[0].toUpperCase())}</div>`}

function applyTheme(){
 document.body.classList.toggle('light', user?.tema==='light');
 if(user?.fondoChat){$('bg').style.backgroundImage=`url("${user.fondoChat}")`;$('bg').style.opacity=(user.brilloFondo??100)/100}
 else $('bg').style.backgroundImage='none';
}

function imageToBase64(file,maxDim=1000,quality=.78){
 return new Promise((resolve,reject)=>{
  const r=new FileReader();r.onerror=reject;r.onload=e=>{
   if(!file.type.startsWith('image/')) return resolve(e.target.result);
   const img=new Image();img.onload=()=>{
    let w=img.width,h=img.height;
    if(Math.max(w,h)>maxDim){const k=maxDim/Math.max(w,h);w=Math.round(w*k);h=Math.round(h*k)}
    const c=document.createElement('canvas');c.width=w;c.height=h;c.getContext('2d').drawImage(img,0,0,w,h);
    resolve(c.toDataURL('image/jpeg',quality));
   };img.onerror=reject;img.src=e.target.result;
  };r.readAsDataURL(file);
 });
}

window.addEventListener('load',()=>{
 const saved=localStorage.getItem('arxechat_user');
 if(saved){try{const u=JSON.parse(saved);user=u;socket.emit('login_usuario',{nombre:u.nombre,pass:u.pass})}catch{localStorage.removeItem('arxechat_user')}}
});
$('authToggle').onclick=()=>{
 authRegister=!authRegister;$('authTitle').textContent=authRegister?'Crear cuenta':'Iniciar sesión';
 $('authButton').textContent=authRegister?'Crear cuenta':'Entrar';$('authPass2').classList.toggle('hidden',!authRegister);
 $('authPhoto').classList.toggle('hidden',!authRegister);$('authError').textContent='';
};
$('authButton').onclick=async()=>{
 const nombre=$('authName').value.trim(),pass=$('authPass').value;
 if(!nombre||!pass)return $('authError').textContent='Rellena todos los campos.';
 if(authRegister){
  if(pass!==$('authPass2').value)return $('authError').textContent='Las contraseñas no coinciden.';
  let foto=null;if($('authPhoto').files[0])foto=await imageToBase64($('authPhoto').files[0],700,.7);
  socket.emit('registrar_usuario',{nombre,pass,foto});
 }else socket.emit('login_usuario',{nombre,pass});
};

socket.on('connect',()=>{$('connection').textContent='● Conectado';$('connection').style.color='var(--accent)';if(user)socket.emit('conectar_usuario',{id:user.id})});
socket.on('disconnect',()=>{$('connection').textContent='● Reconectando…';$('connection').style.color='#e9a23b'});
socket.on('connect_error',()=>{$('connection').textContent='● Error de conexión';$('connection').style.color='#ef5350'});

socket.on('auth_resultado',res=>{
 if(!res.exito){$('authError').textContent=res.mensaje;return}
 user=res.usuario;localStorage.setItem('arxechat_user',JSON.stringify(user));startApp();
});
function startApp(){
 $('auth').classList.add('hidden');$('app').classList.remove('hidden');
 $('myName').textContent=user.nombre;$('myId').textContent='ID: '+user.id;$('myIdText').textContent='Tu ID: '+user.id;
 if(user.foto){$('myImg').src=user.foto;$('myImg').classList.remove('hidden');$('myAvatar').classList.add('hidden')}
 else{$('myImg').classList.add('hidden');$('myAvatar').classList.remove('hidden');$('myAvatar').textContent=(user.nombre||'U')[0].toUpperCase()}
 applyTheme();socket.emit('conectar_usuario',{id:user.id});socket.emit('obtener_contactos',{id:user.id});enablePush();
}
function enablePush(){if(!VAPID_PUBLIC_KEY||!('serviceWorker'in navigator)||!('PushManager'in window))return;
 navigator.serviceWorker.register('/service-worker.js').then(async reg=>{
  if(Notification.permission==='default')await Notification.requestPermission();
  if(Notification.permission!=='granted')return;
  let sub=await reg.pushManager.getSubscription();
  if(!sub)sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:base64ToUint8(VAPID_PUBLIC_KEY)});
  socket.emit('guardar_subscripcion_push',{usuario_id:user.id,subscription:sub.toJSON()});
 }).catch(()=>{});
}
function base64ToUint8(s){const p='='.repeat((4-s.length%4)%4),b=atob((s+p).replace(/-/g,'+').replace(/_/g,'/'));return Uint8Array.from(b,c=>c.charCodeAt(0))}

socket.on('contactos_cargados',list=>{contacts=list;renderContacts()});
function renderContacts(){
 const box=$('contacts');box.innerHTML='';
 contacts.forEach(c=>{
  const b=document.createElement('button');b.className='contact'+(active&&active.id===c.id?' active':'');
  b.innerHTML=avatarHTML(c)+`<div class="contact-info"><div class="contact-name">${esc(c.nombre)} ${c.esGrupo?'👥':''}</div><div class="contact-sub">${c.esGrupo?'Grupo':'ID: '+esc(c.id)}${!c.esGuardado?' · Nuevo':''}</div></div>`;
  b.onclick=()=>selectChat(c);box.appendChild(b);
 });
}
function selectChat(c){
 active=c;renderContacts();$('chat').classList.add('mobile-open');
 $('activeName').textContent=c.nombre;$('activeStatus').textContent=c.esGrupo?'Grupo':'Chat privado';
 if(c.foto){$('activeImg').src=c.foto;$('activeImg').classList.remove('hidden');$('activeAvatar').classList.add('hidden')}
 else{$('activeImg').classList.add('hidden');$('activeAvatar').classList.remove('hidden');$('activeAvatar').textContent=(c.nombre||'?')[0].toUpperCase()}
 $('messages').innerHTML='';renderedIds.clear();cancelReply();
 if(c.fondoChat)$('bg').style.backgroundImage=`url("${c.fondoChat}")`;
 const token=++historyRequestToken;
 socket.emit('cargar_historial',{emisor:user.id,receptor:c.id,esGrupo:c.esGrupo,token});
}
function closeChat(){$('chat').classList.remove('mobile-open');active=null;renderContacts()}

function textLinks(s){return esc(s).replace(/(https?:\/\/[^\s<]+)/g,'<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>')}
function renderMessage(m){
 if(m.id && renderedIds.has(String(m.id)))return; if(m.id)renderedIds.add(String(m.id));
 if(!active)return;
 const row=document.createElement('div');row.className='row '+(m.emisor===user.id?'me':'other');if(m.id)row.dataset.id=m.id;
 const bubble=document.createElement('div');bubble.className='bubble';
 let html='';
 if(active.esGrupo && m.emisor!==user.id)html+=`<div class="sender">${esc(m.nombreEmisor||'Usuario')}</div>`;
 if(m.responde_a && m.reply_text)html+=`<div class="reply-preview">${esc(m.reply_author||'Mensaje')}<br>${esc(m.reply_text)}</div>`;
 if(m.tipo==='imagen'&&m.archivo_data)html+=`<img class="msg-image" src="${esc(m.archivo_data)}" alt="${esc(m.archivo_nombre||'imagen')}">`;
 else if(m.tipo==='archivo'&&m.archivo_data)html+=`<a class="file-card" href="${esc(m.archivo_data)}" download="${esc(m.archivo_nombre||'archivo')}"><span class="file-icon">📄</span><span><span class="file-name">${esc(m.archivo_nombre||'archivo')}</span><br><span class="file-size">${formatBytes(m.archivo_tamano)}</span></span></a>`;
 if(m.texto)html+=`<div class="msg-text">${textLinks(m.texto)}</div>`;
 html+=`<span class="time">${m.fecha?new Date(m.fecha).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}):''}</span>`;
 html+=`<div class="msg-tools"><button class="tool" onclick='setReply(${JSON.stringify(m).replace(/'/g,"&#39;")})'>↩ Responder</button></div>`;
 bubble.innerHTML=html;row.appendChild(bubble);$('messages').appendChild(row);$('messages').scrollTop=$('messages').scrollHeight;
}
socket.on('historial_cargado',data=>{
 const msgs=Array.isArray(data)?data:data.mensajes||[];
 if(!active)return;$('messages').innerHTML='';renderedIds.clear();msgs.forEach(renderMessage);
});
socket.on('recibir_mensaje',m=>{
 if(m.emisor===user.id||m.receptor===user.id||active?.esGrupo){
  if(active && m.clave_chat===active.id || active && !active.esGrupo && (m.emisor===active.id||m.receptor===active.id))renderMessage(m);
 }
 socket.emit('obtener_contactos',{id:user.id});
});
socket.on('mensaje_enviado_ok',m=>{if(active&&((active.esGrupo&&m.clave_chat===active.id)||(!active.esGrupo&&(m.emisor===active.id||m.receptor===active.id))))renderMessage(m)});
socket.on('error_mensaje',r=>alert(r.mensaje||'No se pudo enviar el mensaje.'));

function setReply(m){
 replyTo=m;$('replyBar').classList.remove('hidden');$('replyName').textContent=m.nombreEmisor||'Usuario';$('replyText').textContent=m.texto||m.archivo_nombre||'Archivo';$('messageInput').focus();
}
function cancelReply(){replyTo=null;$('replyBar').classList.add('hidden')}
$('messageInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessage()}});

async function prepareFile(){
 const file=$('fileInput').files[0];if(!file)return;
 if(file.size>MAX_FILE_BYTES)return alert('El archivo supera el límite de 20 MB.');
 pendingFile=file;$('messageInput').placeholder='Archivo preparado: '+file.name;
}
const MAX_FILE_BYTES=20*1024*1024;
async function sendMessage(){
 if(!active)return;
 const input=$('messageInput'),texto=input.value.trim();
 if(!texto&&!pendingFile)return;
 let archivo=null;
 if(pendingFile){
  const data=await imageToBase64(pendingFile,1200,.75);
  archivo={data,nombre:pendingFile.name,tipo:pendingFile.type||'application/octet-stream',tamano:pendingFile.size};
 }
 socket.emit('mensaje_enviado',{
  emisor:user.id,nombreEmisor:user.nombre,fotoEmisor:user.foto,receptor:active.id,
  esGrupo:active.esGrupo?1:0,texto,tipo:archivo?(archivo.tipo.startsWith('image/')?'imagen':'archivo'):'texto',
  archivo, responde_a:replyTo?.id||null
 });
 input.value='';pendingFile=null;$('fileInput').value='';input.placeholder='Escribe un mensaje…';cancelReply();
}

function addPerson(){const q=$('personInput').value.trim();if(!q)return;socket.emit('guardar_contacto',{mi_id:user.id,contacto_id:q});closeModal('addModal')}
async function createGroup(){
 const name=$('groupName').value.trim();if(!name)return alert('Escribe un nombre.');
 const ids=$('groupMembers').value.split(',').map(x=>x.trim()).filter(Boolean);let foto=null;
 if($('groupPhoto').files[0])foto=await imageToBase64($('groupPhoto').files[0],700,.7);
 ids.push(user.id);socket.emit('crear_grupo',{nombre:name,foto,creador_id:user.id,miembros:[...new Set(ids)]});closeModal('addModal')
}
socket.on('contacto_resultado',r=>{if(!r.exito)alert(r.mensaje);else socket.emit('obtener_contactos',{id:user.id})});
socket.on('grupo_creado_resultado',r=>{if(!r.exito)alert(r.mensaje||'Error');socket.emit('obtener_contactos',{id:user.id})});

function openSettings(){
 $('editName').value=user.nombre;$('editTheme').value=user.tema||'dark';$('editBrightness').value=user.brilloFondo??100;openModal('settingsModal')
}
async function saveSettings(){
 let foto=user.foto||null,bg=user.fondoChat||null;
 if($('editPhoto').files[0])foto=await imageToBase64($('editPhoto').files[0],700,.7);
 if($('editBg').files[0])bg=await imageToBase64($('editBg').files[0],1200,.7);
 socket.emit('actualizar_perfil',{id:user.id,nombre:$('editName').value.trim(),pass:$('editPass').value,
  passActual:user.pass,foto,fondoChat:bg,tema:$('editTheme').value,brilloFondo:+$('editBrightness').value});
}
socket.on('perfil_actualizado',r=>{if(!r.exito)return alert(r.mensaje);user=r.usuario;localStorage.setItem('arxechat_user',JSON.stringify(user));closeModal('settingsModal');startApp()});
function logout(){localStorage.removeItem('arxechat_user');location.reload()}
</script>
</body>
</html>
"""


@app.route("/")
def home():
    return render_template_string(HTML_LAYOUT, vapid_public_key=VAPID_PUBLIC_KEY)


@app.route("/health")
def health():
    return jsonify({"ok": True})


@app.route("/service-worker.js")
def service_worker():
    js = """
self.addEventListener("push", event => {
    let data = {};
    try { data = event.data ? event.data.json() : {}; } catch (_) {}
    event.waitUntil(self.registration.showNotification(
        data.title || "Arxechat",
        { body: data.body || "Nuevo mensaje", data: {url: data.url || "/"} }
    ));
});
self.addEventListener("notificationclick", event => {
    event.notification.close();
    event.waitUntil(clients.matchAll({type:"window", includeUncontrolled:true}).then(list => {
        for (const client of list) {
            if ("focus" in client) return client.focus();
        }
        if (clients.openWindow) return clients.openWindow(
            event.notification.data?.url || "/"
        );
    }));
});
"""
    return app.response_class(js, mimetype="application/javascript")


@socketio.on("conectar_usuario")
def conectar(data):
    uid = str(data.get("id", ""))
    if not uid:
        return
    join_room(uid)
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT grupo_id FROM miembros_grupo WHERE usuario_id=%s AND aceptado=1",
            (uid,),
        )
        for row in cur.fetchall():
            join_room(row["grupo_id"])


@socketio.on("registrar_usuario")
def registrar(data):
    nombre = str(data.get("nombre", "")).strip()
    password = str(data.get("pass", ""))
    if not nombre or not password:
        return emit("auth_resultado", {"exito": False, "mensaje": "Faltan datos."})

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM usuarios WHERE LOWER(nombre)=LOWER(%s)", (nombre,))
        if cur.fetchone():
            return emit("auth_resultado", {"exito": False, "mensaje": "Ese usuario ya existe."})

        nuevo_id = str(random.randint(10000000, 99999999))
        cur.execute(
            """INSERT INTO usuarios
               (id,nombre,pass,foto,fondoChat,tema,brilloFondo)
               VALUES (%s,%s,%s,%s,NULL,'dark',100)""",
            (nuevo_id, nombre, generate_password_hash(password), data.get("foto")),
        )
        conn.commit()
        cur.execute("SELECT * FROM usuarios WHERE id=%s", (nuevo_id,))
        u = safe_user(cur.fetchone())
        u["pass"] = password
    emit("auth_resultado", {"exito": True, "usuario": u})


@socketio.on("login_usuario")
def login(data):
    nombre = str(data.get("nombre", "")).strip()
    password = str(data.get("pass", ""))
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM usuarios WHERE LOWER(nombre)=LOWER(%s)", (nombre,))
        row = cur.fetchone()
        if not row or not check_password_hash(row["pass"], password):
            return emit("auth_resultado", {"exito": False, "mensaje": "Cuenta o contraseña incorrecta."})
        u = dict(row)
        u["pass"] = password
    emit("auth_resultado", {"exito": True, "usuario": u})


@socketio.on("actualizar_perfil")
def actualizar_perfil(data):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM usuarios WHERE id=%s", (data.get("id"),))
        row = cur.fetchone()
        if not row:
            return emit("perfil_actualizado", {"exito": False, "mensaje": "Usuario no encontrado."})

        new_pass = data.get("pass") or data.get("passActual", "")
        pass_hash = generate_password_hash(new_pass) if data.get("pass") else row["pass"]

        try:
            cur.execute("""
                UPDATE usuarios
                SET nombre=%s,pass=%s,foto=%s,fondoChat=%s,tema=%s,brilloFondo=%s
                WHERE id=%s
            """, (
                data.get("nombre") or row["nombre"], pass_hash,
                data.get("foto"), data.get("fondoChat"),
                data.get("tema", "dark"), int(data.get("brilloFondo", 100)),
                data["id"],
            ))
            conn.commit()
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            return emit("perfil_actualizado", {"exito": False, "mensaje": "Ese nombre ya está en uso."})

        cur.execute("SELECT * FROM usuarios WHERE id=%s", (data["id"],))
        u = dict(cur.fetchone())
        u["pass"] = new_pass
    emit("perfil_actualizado", {"exito": True, "usuario": u})


@socketio.on("obtener_contactos")
def obtener_contactos(data):
    uid = str(data.get("id"))
    lista, seen = [], set()

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT u.id,u.nombre,u.foto
            FROM contactos c JOIN usuarios u ON u.id=c.contacto_id
            WHERE c.mi_id=%s ORDER BY u.nombre
        """, (uid,))
        for r in cur.fetchall():
            lista.append({"id":r["id"],"nombre":r["nombre"],"foto":r["foto"],"esGuardado":True,"esGrupo":False})
            seen.add(r["id"])

        cur.execute("""
            SELECT DISTINCT emisor,receptor FROM mensajes
            WHERE es_grupo=0 AND (emisor=%s OR receptor=%s)
            ORDER BY GREATEST(emisor,receptor)
        """, (uid,uid))
        for r in cur.fetchall():
            other = r["receptor"] if r["emisor"] == uid else r["emisor"]
            if other in seen: continue
            cur.execute("SELECT id,nombre,foto FROM usuarios WHERE id=%s",(other,))
            u=cur.fetchone()
            if u:
                lista.append({"id":u["id"],"nombre":u["nombre"],"foto":u["foto"],"esGuardado":False,"esGrupo":False})
                seen.add(other)

        cur.execute("""
            SELECT g.id,g.nombre,g.foto,mg.aceptado
            FROM miembros_grupo mg JOIN grupos g ON g.id=mg.grupo_id
            WHERE mg.usuario_id=%s ORDER BY g.nombre
        """,(uid,))
        for r in cur.fetchall():
            lista.append({"id":r["id"],"nombre":r["nombre"],"foto":r["foto"],
                          "esGuardado":bool(r["aceptado"]),"esGrupo":True})
    emit("contactos_cargados", lista)


@socketio.on("guardar_contacto")
def guardar_contacto(data):
    mi_id, contacto_id = str(data.get("mi_id")), str(data.get("contacto_id","")).strip()
    with get_db() as conn:
        cur=conn.cursor()
        cur.execute("SELECT id FROM usuarios WHERE id=%s OR LOWER(nombre)=LOWER(%s)",(contacto_id,contacto_id))
        row=cur.fetchone()
        if not row:
            return emit("contacto_resultado",{"exito":False,"mensaje":"No existe ese usuario."})
        if row["id"]==mi_id:
            return emit("contacto_resultado",{"exito":False,"mensaje":"No puedes añadirte a ti mismo."})
        cur.execute("""INSERT INTO contactos(mi_id,contacto_id) VALUES(%s,%s)
                       ON CONFLICT DO NOTHING""",(mi_id,row["id"]))
        conn.commit()
    emit("contacto_resultado",{"exito":True,"mensaje":"Contacto añadido."})


@socketio.on("crear_grupo")
def crear_grupo(data):
    gid="GRP_"+uuid.uuid4().hex[:12]
    miembros=list(dict.fromkeys(map(str,data.get("miembros",[]))))
    with get_db() as conn:
        cur=conn.cursor()
        cur.execute("INSERT INTO grupos(id,nombre,foto,creador_id) VALUES(%s,%s,%s,%s)",
                    (gid,data.get("nombre","Grupo"),data.get("foto"),data["creador_id"]))
        for uid in miembros:
            cur.execute("SELECT id FROM usuarios WHERE id=%s",(uid,))
            if cur.fetchone():
                cur.execute("""INSERT INTO miembros_grupo(grupo_id,usuario_id,aceptado)
                               VALUES(%s,%s,%s) ON CONFLICT DO NOTHING""",
                            (gid,uid,1 if uid==data["creador_id"] else 0))
        conn.commit()
    join_room(gid)
    emit("grupo_creado_resultado",{"exito":True,"grupo_id":gid})


@socketio.on("aceptar_grupo")
def aceptar_grupo(data):
    with get_db() as conn:
        cur=conn.cursor()
        cur.execute("""UPDATE miembros_grupo SET aceptado=1
                       WHERE grupo_id=%s AND usuario_id=%s""",
                    (data["grupo_id"],data["usuario_id"]))
        conn.commit()
    join_room(data["grupo_id"])
    emit("grupo_aceptado",{"grupo_id":data["grupo_id"]})


@socketio.on("cargar_historial")
def cargar_historial(data):
    es_grupo=bool(data.get("esGrupo"))
    clave=data["receptor"] if es_grupo else make_chat_key(data["emisor"],data["receptor"])

    with get_db() as conn:
        cur=conn.cursor()
        cur.execute("""
            SELECT m.*,
                   r.nombre AS reply_author,
                   r.texto AS reply_text
            FROM mensajes m
            LEFT JOIN mensajes r ON r.id=m.responde_a
            WHERE m.clave_chat=%s
            ORDER BY m.fecha ASC,m.id ASC
        """,(clave,))
        historial=[message_dict(r) for r in cur.fetchall()]
    emit("historial_cargado",historial)


@socketio.on("mensaje_enviado")
def manejar_mensaje(data):
    emisor=str(data.get("emisor"))
    receptor=str(data.get("receptor"))
    es_grupo=1 if data.get("esGrupo") else 0
    texto=str(data.get("texto",""))[:10000]
    tipo=data.get("tipo","texto")
    archivo=data.get("archivo") or {}
    responde_a=data.get("responde_a")

    if tipo not in ("texto","imagen","archivo"):
        tipo="texto"

    if archivo:
        raw=str(archivo.get("data",""))
        if len(raw)>MAX_FILE_BYTES*2:
            return emit("error_mensaje",{"mensaje":"El archivo es demasiado grande."})
        archivo_data=raw
        archivo_nombre=str(archivo.get("nombre","archivo"))[:255]
        archivo_tipo=str(archivo.get("tipo","application/octet-stream"))[:150]
        archivo_tamano=int(archivo.get("tamano",0) or 0)
    else:
        archivo_data=archivo_nombre=archivo_tipo=None
        archivo_tamano=None

    if not texto and not archivo_data:
        return

    clave=receptor if es_grupo else make_chat_key(emisor,receptor)

    with get_db() as conn:
        cur=conn.cursor()
        cur.execute("""
            INSERT INTO mensajes
            (clave_chat,emisor,receptor,texto,nombreEmisor,fotoEmisor,es_grupo,
             tipo,archivo_nombre,archivo_tipo,archivo_tamano,archivo_data,responde_a)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
        """,(
            clave,emisor,receptor,texto,data.get("nombreEmisor"),
            data.get("fotoEmisor"),es_grupo,tipo,archivo_nombre,archivo_tipo,
            archivo_tamano,archivo_data,responde_a
        ))
        row=cur.fetchone()
        conn.commit()

        if es_grupo:
            cur.execute("""SELECT usuario_id FROM miembros_grupo
                           WHERE grupo_id=%s AND aceptado=1 AND usuario_id<>%s""",
                        (receptor,emisor))
            destinatarios=[r["usuario_id"] for r in cur.fetchall()]
        else:
            destinatarios=[receptor]

        cur.execute("""SELECT r.nombre AS reply_author,r.texto AS reply_text
                       FROM mensajes m LEFT JOIN mensajes r ON r.id=m.responde_a
                       WHERE m.id=%s""",(row["id"],))
        reply=cur.fetchone()

    msg=message_dict(row)
    msg["reply_author"]=reply["reply_author"] if reply else None
    msg["reply_text"]=reply["reply_text"] if reply else None

    if es_grupo:
        emit("recibir_mensaje",msg,room=receptor)
    else:
        emit("recibir_mensaje",msg,room=emisor)
        emit("recibir_mensaje",msg,room=receptor)

    # Confirmación separada para el emisor: permite pintar el mensaje
    # aunque el evento de la sala llegue con un pequeño retraso.
    emit("mensaje_enviado_ok",msg)

    cuerpo=texto if texto else ("📷 Imagen" if tipo=="imagen" else "📎 "+(archivo_nombre or "Archivo"))
    for dest in destinatarios:
        notify_user(dest,emisor,data.get("nombreEmisor","Arxechat"),cuerpo)


@socketio.on("guardar_subscripcion_push")
def guardar_subscripcion_push(data):
    sub=data.get("subscription") or {}
    keys=sub.get("keys") or {}
    if not data.get("usuario_id") or not sub.get("endpoint") or not keys.get("p256dh") or not keys.get("auth"):
        return
    with get_db() as conn:
        cur=conn.cursor()
        cur.execute("""
            INSERT INTO push_subscriptions(usuario_id,endpoint,p256dh,auth)
            VALUES(%s,%s,%s,%s)
            ON CONFLICT(endpoint) DO UPDATE
            SET usuario_id=EXCLUDED.usuario_id,p256dh=EXCLUDED.p256dh,auth=EXCLUDED.auth
        """,(data["usuario_id"],sub["endpoint"],keys["p256dh"],keys["auth"]))
        conn.commit()


if __name__=="__main__":
    port=int(os.environ.get("PORT",5000))
    socketio.run(app,host="0.0.0.0",port=port,allow_unsafe_werkzeug=True)
