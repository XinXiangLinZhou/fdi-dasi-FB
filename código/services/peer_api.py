# Comunicación directa entre agentes (peer-to-peer)
import httpx
import asyncio
import time
from app.config import MY_PORT, logger
from app.state import ip_time, list_ping, lock


# Esta función permite comprobar si otro agente sigue activo
# para mantener una red fiable y evitar trabajar con nodos caídos.
async def ping(ip: str, msg: dict, port: int = MY_PORT):
    url = f"http://{ip}:{port}/buzon"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            logger.debug(f"Intentando conectar al ip: {ip}...")

            r = await client.post(url, json=msg)

            # Si hay respuesta válida, actualizamos su estado
            # para que el sistema use información real y reciente.
            if r.status_code == 200:
                async with lock:
                    ip_time[ip] = time.time()
                    list_ping.discard(ip)

                logger.info(f"Conectado al ip: {ip}")
                return r.json()

            else:
                logger.warning(f"Respuesta inesperada de {ip}: {r.status_code}")

    # Capturamos errores para que un fallo externo
    # no detenga todo el funcionamiento del agente.
    except Exception as e:
        logger.debug(f"No se pudo contactar con {ip}: {e}")

    return None