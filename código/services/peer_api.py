# Comunicación directa entre agentes (peer-to-peer)
import requests
import time

from app.config import MY_PORT
from app.state import ip_time, list_ping, lock


# Función: envía un mensaje (ping) a otro agente y actualiza su estado si responde
def ping(ip: str, msg: dict, port: int = MY_PORT):
    url = f"http://{ip}:{port}/buzon"

    try:
        # Enviar petición POST al buzón del otro agente
        r = requests.post(url, json=msg, timeout=5)

        # Si responde correctamente, actualizar estado de conexión
        if r.status_code == 200:
            with lock:
                ip_time[ip] = time.time()   # última vez que respondió
                list_ping.discard(ip)       # quitar de la lista de pendientes
            return r.json()

    except requests.exceptions.RequestException:
        # Si falla la conexión, se ignora (el monitor lo gestionará)
        pass

    return None