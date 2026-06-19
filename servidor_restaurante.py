import socket
import threading
import urllib.parse
import json
import time
import os

# Archivos
FICHERO_PRODUCTOS = "productos_db.json"
FICHERO_TARJETAS = "tarjetas_db.json"

# Datos globales
productos_db = [{"id": 1, "nombre": "Hamburguesa Completa", "precio": 8.50}]
tarjetas_db = {"1234": 50.00}
pedido_pendiente = "NO"

def cargar_datos():
    global productos_db, tarjetas_db
    if os.path.exists(FICHERO_PRODUCTOS):
        with open(FICHERO_PRODUCTOS, "r") as f: productos_db = json.load(f)
    if os.path.exists(FICHERO_TARJETAS):
        with open(FICHERO_TARJETAS, "r") as f: tarjetas_db = json.load(f)

cargar_datos()

def manejar_conexiones(conexion):
    global pedido_pendiente, tarjetas_db
    try:
        peticion = conexion.recv(2048).decode('utf-8', errors='ignore')
        if not peticion: return

        # RESPUESTA LIMPIA PARA LA CYBERPI
        if "PETICION_PEDIDO" in peticion:
            msg = pedido_pendiente if pedido_pendiente != "NO" else "VACIO"
            respuesta = f"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n{msg}"
            conexion.send(respuesta.encode('utf-8'))
            if pedido_pendiente != "NO": pedido_pendiente = "NO"

        # PROCESAR PAGO
        elif "GET /procesar_pago" in peticion:
            params = urllib.parse.parse_qs(urllib.parse.urlparse(peticion.split(" ")[1]).query)
            cod = params.get('codigo', [''])[0]
            tot = float(params.get('total', [0])[0])
            msg = params.get('msg', [''])[0]
            
            if cod in tarjetas_db and tarjetas_db[cod] >= tot:
                tarjetas_db[cod] -= tot
                pedido_pendiente = msg
                conexion.send(b"HTTP/1.1 200 OK\r\n\r\nOK")
            else:
                conexion.send(b"HTTP/1.1 200 OK\r\n\r\nERROR")

        # SERVIR WEB (Solo si no es una petición de la CyberPi)
        else:
            html = "<html><body><h1>Servidor Activo</h1></body></html>"
            conexion.send(f"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n{html}".encode())
            
    except: pass
    finally: conexion.close()

def iniciar_servidor():
    puerto = int(os.environ.get("PORT", 8080))
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind(("0.0.0.0", puerto))
    servidor.listen(5)
    print(f"🚀 SERVIDOR OK EN PUERTO {puerto}")
    while True:
        con, _ = servidor.accept()
        threading.Thread(target=manejar_conexiones, args=(con,)).start()

if __name__ == "__main__":
    iniciar_servidor()
