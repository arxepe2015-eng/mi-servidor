import socket
import threading
import urllib.parse
import json
import time
import os

# Archivos de persistencia de datos
FICHERO_PRODUCTOS = "productos_db.json"
FICHERO_TARJETAS = "tarjetas_db.json"

# Valores por defecto por si los ficheros están vacíos
productos_db = [
    { "id": 1, "nombre": "Hamburguesa Completa", "precio": 8.50, "personalizaciones": [{"name":"Extra Queso", "price":1.00}, {"name":"Bacon Crujiente", "price":1.50}] },
    { "id": 2, "nombre": "Pizza Pepperoni", "precio": 10.00, "personalizaciones": [{"name":"Borde de Queso", "price":2.00}] }
]
tarjetas_db = {"1234": 50.00}
pedido_pendiente = "NO"

def guardar_datos_en_disco():
    try:
        with open(FICHERO_PRODUCTOS, "w", encoding="utf-8") as f:
            json.dump(productos_db, f, indent=4, ensure_ascii=False)
        with open(FICHERO_TARJETAS, "w", encoding="utf-8") as f:
            json.dump(tarjetas_db, f, indent=4, ensure_ascii=False)
        print("[💾 MEMORIA] Copia de seguridad guardada con éxito.")
    except Exception as e:
        print(f"Error guardando datos: {e}")

def cargar_datos_del_disco():
    global productos_db, tarjetas_db
    if os.path.exists(FICHERO_PRODUCTOS):
        with open(FICHERO_PRODUCTOS, "r", encoding="utf-8") as f:
            productos_db = json.load(f)
    if os.path.exists(FICHERO_TARJETAS):
        with open(FICHERO_TARJETAS, "r", encoding="utf-8") as f:
            tarjetas_db = json.load(f)
    print("[📂 MEMORIA] Base de datos sincronizada y cargada.")

# Cargar datos al iniciar el script
cargar_datos_del_disco()

def obtener_html_completo():
    productos_json = json.dumps(productos_db)
    tarjetas_json = json.dumps(tarjetas_db)
    
    return """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Panel de Control - Restaurante</title>
    <style>
        body { font-family: 'Segoe UI', Arial, sans-serif; background: #121212; color: #fff; margin: 0; padding: 20px; }
        .container { max-width: 900px; margin: auto; background: #1e1e1e; padding: 25px; border-radius: 15px; box-shadow: 0 8px 24px rgba(0,0,0,0.6); }
        h1 { color: #ff9800; text-align: center; margin-top: 0; }
        .login-box { max-width: 400px; margin: 100px auto; background: #1e1e1e; padding: 30px; border-radius: 15px; text-align: center; box-shadow: 0 8px 24px rgba(0,0,0,0.6); border: 2px solid #333; }
        .login-box input { width: 90%; padding: 12px; font-size: 16px; border-radius: 8px; border: 1px solid #444; background: #2a2a2a; color: white; text-align: center; outline: none; margin-bottom: 15px; }
        .btn-login { background: #ff9800; color: #000; border: none; padding: 12px 25px; font-size: 16px; font-weight: bold; cursor: pointer; border-radius: 8px; width: 95%; transition: 0.2s; }
        .btn-login:hover { background: #e65100; }
        .btn-salir { background: #555; color: white; border: none; padding: 8px 15px; cursor: pointer; border-radius: 5px; font-weight: bold; margin-bottom: 20px; float: left; }
        .btn-salir:hover { background: #cc1111; }
        .clear { clear: both; }
        .menu-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }
        .producto-card { background: #2a2a2a; padding: 15px; border-radius: 10px; border: 1px solid #3c3c3c; }
        .producto-card h3 { margin: 0 0 10px 0; color: #ffb74d; }
        .precio-base { font-weight: bold; color: #4caf50; font-size: 18px; }
        .custom-section { margin: 10px 0; background: #333; padding: 10px; border-radius: 6px; }
        .btn-add { background: #ff9800; color: #000; border: none; width: 100%; padding: 10px; font-weight: bold; cursor: pointer; border-radius: 5px; margin-top: 10px; }
        .carrito-box { background: #252525; padding: 15px; border-radius: 10px; margin-top: 20px; border-left: 5px solid #ff9800; }
        .tarjeta-pago { background: #0d47a1; padding: 15px; border-radius: 10px; margin-top: 15px; text-align: center; }
        .tarjeta-pago input { padding: 10px; width: 60%; text-align: center; font-size: 16px; border-radius: 5px; border: none; }
        .btn-pagar { background: #4caf50; color: white; border: none; padding: 12px 30px; font-size: 16px; font-weight: bold; cursor: pointer; border-radius: 5px; margin-top: 10px; width: 100%; }
        .admin-section { background: #2d2d2d; padding: 20px; border-radius: 10px; margin-bottom: 20px; border: 1px dashed #ff9800; }
        .admin-section h3 { margin-top: 0; color: #ff9800; border-bottom: 1px solid #444; padding-bottom: 5px; }
        .grid-formulario { display: grid; grid-template-columns: 1fr; gap: 12px; text-align: left; }
        .form-group { margin-bottom: 12px; text-align: left; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: bold; }
        .form-group input { width: 100%; padding: 8px; box-sizing: border-box; background: #444; color: white; border: 1px solid #555; border-radius: 4px; }
        .btn-admin { background: #00838f; color: white; border: none; padding: 10px 20px; cursor: pointer; font-weight: bold; border-radius: 4px; }
        .lista-items { background: #1a1a1a; padding: 12px; border-radius: 5px; max-height: 200px; overflow-y: auto; font-family: monospace; }
        .item-admin-row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #333; }
        .btn-eliminar-plato { background: #c62828; color: white; border: none; padding: 6px 12px; cursor: pointer; font-weight: bold; border-radius: 4px; }
        #estado-pago { text-align: center; font-weight: bold; margin-top: 15px; font-size: 18px; }
        
        .ticket-box { max-width: 500px; margin: 30px auto; background: #1e1e1e; padding: 30px; border-radius: 15px; border: 2px dashed #4caf50; box-shadow: 0 8px 24px rgba(0,0,0,0.6); }
        .ticket-item { background: #262626; padding: 12px; border-radius: 8px; margin-bottom: 12px; border-left: 4px solid #ffb74d; }
    </style>
</head>
<body>

<div id="pantalla-login" class="login-box">
    <h1>Restaurante Total</h1>
    <input type="text" id="input-nombre" placeholder="Introduce tu nombre..." onkeydown="if(event.key === 'Enter') procesarAcceso()">
    <button class="btn-login" onclick="procesarAcceso()">Entrar al Sistema</button>
</div>

<div id="pantalla-principal" class="container" style="display: none;">
    <button class="btn-salir" onclick="cerrarSesion()">◀ Salir de la Cuenta</button>
    <div class="clear"></div>
    <h1 id="titulo-interfaz">Cargando...</h1>

    <div id="vista-cliente" style="display: none;">
        <div class="menu-grid" id="grid-productos"></div>
        <div class="carrito-box">
            <h3>🛒 Lista del Pedido</h3>
            <div id="contenido-carrito">Vacío.</div>
            <p style="text-align: right; font-size: 20px; font-weight: bold;">TOTAL COMANDA: <span id="total-carrito">0.00</span>€</p>
        </div>
        <div class="tarjeta-pago">
            <label style="display:block; margin-bottom:8px; font-weight:bold;">MÉTODO DE PAGO: TARJETA VIRTUAL</label>
            <input type="text" id="codigo-tarjeta" placeholder="Introduce el pin/código">
            <button class="btn-pagar" onclick="procesarPago()">Confirmar y Pagar</button>
            <div id="estado-pago"></div>
        </div>
    </div>

    <div id="vista-admin" style="display: none;">
        <div class="admin-section">
            <h3>🗑️ Gestión de Productos Actuales</h3>
            <div class="lista-items" id="lista-productos-admin"></div>
        </div>
        <div class="admin-section">
            <h3>🍔 Añadir Nueva Comida</h3>
            <div class="form-group">
                <label>Nombre del Plato:</label>
                <input type="text" id="admin-prod-name">
            </div>
            <div class="form-group">
                <label>Precio de Venta (€):</label>
                <input type="number" id="admin-prod-price" step="0.01">
            </div>
            <div class="form-group">
                <label>Opciones Extras (Formato -> Nombre:Precio, Nombre:Precio):</label>
                <input type="text" id="admin-prod-customs" placeholder="Ejemplo: Queso:1.00, Bacon:1.50">
            </div>
            <button class="btn-admin" style="background:#e65100;" onclick="guardarProducto()">Publicar Comida</button>
        </div>
        <div class="admin-section">
            <h3>💳 Registro de Tarjetas del Banco</h3>
            <div style="display:flex; gap:10px;">
                <input type="text" id="admin-card-code" placeholder="PIN" style="flex:1; padding:5px;">
                <input type="number" id="admin-card-balance" placeholder="Fondos iniciales" step="0.01" style="flex:1; padding:5px;">
            </div>
            <button class="btn-admin" onclick="guardarTarjeta()" style="margin-top:10px;">Crear/Recargar Tarjeta</button>
            <div class="lista-items" id="lista-tarjetas-sistema" style="margin-top:10px;"></div>
        </div>
    </div>
</div>

<div id="pantalla-ticket" class="ticket-box" style="display: none;">
    <h1 style="color: #4caf50; margin-top: 0; text-align: center;">🧾 TICKET GENERADO</h1>
    <div id="datos-ticket-cuerpo"></div>
    <button class="btn-login" style="background: #555; color: white; margin-top: 15px;" onclick="volverAlMenu()">◀ Hacer otro pedido</button>
</div>

<script>
let productosDB = """ + productos_json + """;
let tarjetasDB = """ + tarjetas_json + """;
let carrito = [];
let usuarioActual = "";

window.onload = function() {
    try {
        let sesionGuardada = localStorage.getItem("sesion_usuario_restaurante");
        if(sesionGuardada) {
            document.getElementById('input-nombre').value = sesionGuardada;
            procesarAcceso();
        }
    } catch(e) {}
}

function procesarAcceso() {
    const nombre = document.getElementById('input-nombre').value.trim();
    if(!nombre) return;
    usuarioActual = nombre;
    
    try { localStorage.setItem("sesion_usuario_restaurante", usuarioActual); } catch(e) {}
    
    document.getElementById('pantalla-login').style.display = 'none';
    document.getElementById('pantalla-principal').style.display = 'block';
    document.getElementById('pantalla-ticket').style.display = 'none';
    
    if(nombre.toLowerCase() === "arxe") {
        document.getElementById('titulo-interfaz').innerText = "Consola de Administración Central";
        document.getElementById('vista-admin').style.display = 'block';
        document.getElementById('vista-cliente').style.display = 'none';
        renderAdmin();
    } else {
        document.getElementById('titulo-interfaz').innerText = "Carta Digital - Cliente: " + usuarioActual;
        document.getElementById('vista-admin').style.display = 'none';
        document.getElementById('vista-cliente').style.display = 'block';
        renderTienda();
    }
}

function cerrarSesion() {
    usuarioActual = ""; carrito = [];
    try { localStorage.removeItem("sesion_usuario_restaurante"); } catch(e) {}
    document.getElementById('pantalla-principal').style.display = 'none';
    document.getElementById('pantalla-ticket').style.display = 'none';
    document.getElementById('pantalla-login').style.display = 'block';
}

function renderTienda() {
    const grid = document.getElementById('grid-productos'); grid.innerHTML = "";
    productosDB.forEach(p => {
        let opcionesHtml = "";
        if(p.personalizaciones && p.personalizaciones.length > 0) {
            opcionesHtml = `<div class="custom-section">`;
            p.personalizaciones.forEach(opt => {
                opcionesHtml += `<label><input type="checkbox" class="opt-${p.id}" data-name="${opt.name}" data-price="${opt.price}"> ${opt.name} (+${opt.price}€)</label><br>`;
            });
            opcionesHtml += `</div>`;
        }
        grid.innerHTML += `<div class="producto-card"><h3>${p.nombre}</h3><span class="precio-base">${p.precio.toFixed(2)}€</span>${opcionesHtml}<button class="btn-add" onclick="agregarAlCarrito(${p.id})">Añadir al Carrito</button></div>`;
    });
}

function agregarAlCarrito(idProducto) {
    const producto = productosDB.find(p => p.id === idProducto);
    let extrasElegidos = []; let precioExtraTotal = 0;
    
    document.querySelectorAll(`.opt-${idProducto}`).forEach(cb => {
        if(cb.checked) {
            let nombreExtra = cb.getAttribute('data-name');
            let precioExtra = parseFloat(cb.getAttribute('data-price'));
            extrasElegidos.push({ nombre: nombreExtra, precio: precioExtra });
            precioExtraTotal += precioExtra;
        }
    });
    
    carrito.push({ 
        nombre: producto.nombre, 
        precioBase: producto.precio,
        precioFinal: producto.precio + precioExtraTotal, 
        extras: extrasElegidos 
    });
    actualizarCarritoVisual();
}

function actualizarCarritoVisual() {
    const contenido = document.getElementById('contenido-carrito');
    const totalSpan = document.getElementById('total-carrito');
    if(carrito.length === 0) { contenido.innerHTML = "Vacío."; totalSpan.innerText = "0.00"; return; }
    let html = "<ul>"; let total = 0;
    carrito.forEach((item) => {
        total += item.precioFinal;
        let nombresExtras = item.extras.map(e => e.nombre);
        let ext = nombresExtras.length > 0 ? ` (${nombresExtras.join('+')})` : '';
        html += `<li>${item.nombre}${ext} - ${item.precioFinal.toFixed(2)}€</li>`;
    });
    contenido.innerHTML = html + "</ul>"; totalSpan.innerText = total.toFixed(2);
}

function procesarPago() {
    const estado = document.getElementById('estado-pago');
    const codigoTarjeta = document.getElementById('codigo-tarjeta').value.trim();
    if(carrito.length === 0) return;
    
    let totalFactura = parseFloat(document.getElementById('total-carrito').innerText);
    
    // Formatear cada plato con un guion claro delante
    let resumenPlatos = carrito.map(item => {
        let nExt = item.extras.map(e => e.nombre);
        return "- " + item.nombre + (nExt.length > 0 ? " [+" + nExt.join("+") + "]" : "");
    });
    
    // CONSTRUCCIÓN DEL PROTOCOLO CON SEPARADORES DE SECCIÓN CLAROS Y MARCA FINAL DE COMANDA
    let comandaTexto = "USER:" + usuarioActual + "\\n" +
                       "--------------------\\n" + 
                       resumenPlatos.join("\\n") + "\\n" +
                       "--------------------\\n" +
                       "TOTAL:" + totalFactura.toFixed(2) + "e\\n" +
                       "###";
    
    fetch(`/procesar_pago?codigo=${encodeURIComponent(codigoTarjeta)}&total=${totalFactura}&msg=${encodeURIComponent(comandaTexto)}`)
    .then(res => res.text())
    .then(respuesta => {
        if(respuesta.startsWith("OK")) {
            let cuerpoHtml = `<p style="font-size: 16px;"><strong>Comprador:</strong> ${usuarioActual}</p><hr style="border: 1px dashed #444;">`;
            
            carrito.forEach((item, index) => {
                cuerpoHtml += `<div class="ticket-item">`;
                cuerpoHtml += `<p style="margin: 0; font-size: 16px; color: #ffb74d;"><strong>Plato ${index+1}: ${item.nombre}</strong></p>`;
                cuerpoHtml += `<p style="margin: 3px 0; font-size: 14px; color: #aaa;">• Precio Base: ${item.precioBase.toFixed(2)}€</p>`;
                if(item.extras.length > 0) {
                    item.extras.forEach(ext => {
                        cuerpoHtml += `<p style="margin: 2px 0 2px 15px; font-size: 13px; color: #4caf50;">+ Extra: ${ext.nombre} (${ext.precio.toFixed(2)}€)</p>`;
                    });
                }
                cuerpoHtml += `<p style="margin: 5px 0 0 0; font-size: 14px; text-align: right; font-weight: bold;">Subtotal: ${item.precioFinal.toFixed(2)}€</p>`;
                cuerpoHtml += `</div>`;
            });
            
            cuerpoHtml += `<hr style="border: 1px dashed #444;">`;
            cuerpoHtml += `<h2 style="text-align: center; color: #ff9800; margin: 15px 0;">TOTAL PAGADO: ${totalFactura.toFixed(2)}€</h2>`;
            
            document.getElementById('datos-ticket-cuerpo').innerHTML = cuerpoHtml;
            document.getElementById('pantalla-principal').style.display = 'none';
            document.getElementById('pantalla-ticket').style.display = 'block';
        } else {
            estado.innerText = "❌ Denegado: " + respuesta;
        }
    });
}

function volverAlMenu() {
    carrito = [];
    actualizarCarritoVisual();
    document.getElementById('codigo-tarjeta').value = "";
    document.getElementById('estado-pago').innerText = "";
    document.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = false);
    
    document.getElementById('pantalla-ticket').style.display = 'none';
    document.getElementById('pantalla-principal').style.display = 'block';
}

function renderAdmin() {
    let lt = document.getElementById('lista-tarjetas-sistema'); lt.innerHTML = "";
    for(let c in tarjetasDB) {
        lt.innerHTML += `<div class="item-admin-row"><span>Tarjeta Ficha [ ${c} ] => Balance: ${tarjetasDB[c].toFixed(2)}€</span><button class="btn-eliminar-plato" onclick="eliminarTarjetaSistema('${c}')">Borrar Tarjeta</button></div>`;
    }
    let lp = document.getElementById('lista-productos-admin'); lp.innerHTML = "";
    productosDB.forEach(p => {
        lp.innerHTML += `<div class="item-admin-row"><span>${p.nombre} (${p.precio}€)</span><button class="btn-eliminar-plato" onclick="eliminarProductoMenu(${p.id})">Quitar del Menú</button></div>`;
    });
}

function guardarProducto() {
    const n = document.getElementById('admin-prod-name').value.trim();
    const p = document.getElementById('admin-prod-price').value;
    const e = document.getElementById('admin-prod-customs').value.trim();
    if(!n || !p) return;
    fetch(`/admin_add?nombre=${encodeURIComponent(n)}&precio=${p}&extras=${encodeURIComponent(e)}`).then(() => window.location.reload());
}

function eliminarProductoMenu(id) {
    fetch(`/admin_delete?id=${id}`).then(() => window.location.reload());
}

function guardarTarjeta() {
    const c = document.getElementById('admin-card-code').value.trim();
    const s = document.getElementById('admin-card-balance').value;
    if(!c || !s) return;
    fetch(`/admin_card?codigo=${encodeURIComponent(c)}&saldo=${s}`).then(() => window.location.reload());
}

function eliminarTarjetaSistema(codigo) {
    fetch(`/admin_borrar_tarjeta?codigo=${encodeURIComponent(codigo)}`).then(() => window.location.reload());
}
</script>
</body>
</html>
"""

def manejar_conexiones(conexion, direccion):
    global pedido_pendiente, productos_db, tarjetas_db
    try:
        peticion = conexion.recv(8192).decode('utf-8', errors='ignore')
        if not peticion:
            conexion.close()
            return

        # NUEVO: Ahora empaquetamos la respuesta de la CyberPi en formato Web real (HTTP)
        if "PETICION_PEDIDO" in peticion:
            respuesta_http = f"HTTP/1.1 200 OK\r\nAccess-Control-Allow-Origin: *\r\nContent-Type: text/plain\r\n\r\n{pedido_pendiente}"
            conexion.send(respuesta_http.encode('utf-8'))
            if pedido_pendiente != "NO":
                pedido_pendiente = "NO"
        
        elif "GET /admin_add" in peticion:
            linea = peticion.split("\n")[0]
            params = urllib.parse.parse_qs(urllib.parse.urlparse(linea.split(" ")[1]).query)
            nombre = params.get('nombre', [''])[0]
            precio = float(params.get('precio', [0])[0])
            extras_raw = params.get('extras', [''])[0]
            
            personalizaciones = []
            if extras_raw:
                for b in extras_raw.split(','):
                    partes = b.split(':')
                    if len(partes) == 2:
                        personalizaciones.append({"name": partes[0].strip(), "price": float(partes[1].strip())})
            
            productos_db.append({"id": int(time.time()), "nombre": nombre, "precio": precio, "personalizaciones": personalizaciones})
            guardar_datos_en_disco()
            conexion.send("HTTP/1.1 200 OK\r\nAccess-Control-Allow-Origin: *\r\n\r\nOK".encode('utf-8'))

        elif "GET /admin_delete" in peticion:
            linea = peticion.split("\n")[0]
            params = urllib.parse.parse_qs(urllib.parse.urlparse(linea.split(" ")[1]).query)
            id_plato = int(params.get('id', [0])[0])
            productos_db = [p for p in productos_db if p['id'] != id_plato]
            guardar_datos_en_disco()
            conexion.send("HTTP/1.1 200 OK\r\nAccess-Control-Allow-Origin: *\r\n\r\nOK".encode('utf-8'))

        elif "GET /admin_borrar_tarjeta" in peticion:
            linea = peticion.split("\n")[0]
            params = urllib.parse.parse_qs(urllib.parse.urlparse(linea.split(" ")[1]).query)
            codigo = params.get('codigo', [''])[0]
            if codigo in tarjetas_db:
                del tarjetas_db[codigo]
            guardar_datos_en_disco()
            conexion.send("HTTP/1.1 200 OK\r\nAccess-Control-Allow-Origin: *\r\n\r\nOK".encode('utf-8'))

        elif "GET /admin_card" in peticion:
            linea = peticion.split("\n")[0]
            params = urllib.parse.parse_qs(urllib.parse.urlparse(linea.split(" ")[1]).query)
            codigo = params.get('codigo', [''])[0]
            saldo = float(params.get('saldo', [0])[0])
            tarjetas_db[codigo] = tarjetas_db.get(codigo, 0) + saldo
            guardar_datos_en_disco()
            conexion.send("HTTP/1.1 200 OK\r\nAccess-Control-Allow-Origin: *\r\n\r\nOK".encode('utf-8'))

        elif "GET /procesar_pago" in peticion:
            linea = peticion.split("\n")[0]
            params = urllib.parse.parse_qs(urllib.parse.urlparse(linea.split(" ")[1]).query)
            codigo = params.get('codigo', [''])[0]
            total = float(params.get('total', [0])[0])
            msg = params.get('msg', [''])[0]
            
            if codigo not in tarjetas_db:
                msg_resp = "TARJETA_NO_EXISTE"
            elif tarjetas_db[codigo] < total:
                msg_resp = "SALDO_INSUFICIENTE"
            else:
                tarjetas_db[codigo] -= total
                pedido_pendiente = msg
                msg_resp = f"OK:{tarjetas_db[codigo]:.2f}"
                guardar_datos_en_disco()
                
            resp = f"HTTP/1.1 200 OK\r\nAccess-Control-Allow-Origin: *\r\n\r\n{msg_resp}"
            conexion.send(resp.encode('utf-8'))

        elif "GET / " in peticion or "GET /index.html" in peticion:
            html_contenido = obtener_html_completo()
            respuesta_http = f"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {len(html_contenido.encode('utf-8'))}\r\nConnection: close\r\n\r\n{html_contenido}"
            conexion.send(respuesta_http.encode('utf-8'))
        
    except Exception as e:
        pass
    finally:
        conexion.close()

def iniciar_servidor_central():
    IP_LOCAL = "0.0.0.0"
    PUERTO = int(os.environ.get("PORT", 8080))
    
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind((IP_LOCAL, PUERTO))
    servidor.listen(10)
    print(f"🚀 SERVIDOR EN LA NUBE ACTIVO EN EL PUERTO: {PUERTO}")
    while True:
        conexion, direccion = servidor.accept()
        threading.Thread(target=manejar_conexiones, args=(conexion, direccion)).start()

if __name__ == "__main__":
    iniciar_servidor_central()
