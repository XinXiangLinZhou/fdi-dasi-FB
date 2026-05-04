# Comunicación directa entre agentes (peer-to-peer)
import httpx
import asyncio
import time
from app.config import MY_PORT, logger
from app.state import ip_time, list_ping, lock


# Función: envía un mensaje (ping) a otro agente y actualiza su estado si responde
async def ping(ip: str, msg: dict, port: int = MY_PORT):
    url = f"http://{ip}:{port}/buzon"

    try:
        # Enviar petición POST al buzón del otro agente
        async with httpx.AsyncClient(timeout=5.0) as client:
            logger.debug(f"Intentando conectar al ip: {ip}...")

            r = await client.post(url, json=msg)

            # Si responde correctamente, actualizar estado de conexión
            if r.status_code == 200:
                async with lock:
                    ip_time[ip] = time.time()   # última vez que respondió
                    list_ping.discard(ip)       # quitar de la lista de pendientes

                logger.info(f"Conectado al ip: {ip}")
                return r.json()

            else:
                logger.warning(f"Respuesta inesperada de {ip}: {r.status_code}")

    except Exception as e:
        logger.debug(f"No se pudo contactar con {ip}: {e}")

    return None