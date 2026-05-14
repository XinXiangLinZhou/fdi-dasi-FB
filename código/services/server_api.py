# Comunicación con el servidor del profesor (API central)
from app.config import SERVER_URL, MY_ALIAS, logger
import httpx

client = httpx.AsyncClient(timeout=10.0)
# Función: registra el alias del agente en el servidor si aún no existe
async def postName():
    try:
        await client.post(f"{SERVER_URL}alias/{MY_ALIAS}")
    except Exception as e:
        logger.error(f"Error en postName: {e}")


# Función: obtiene toda la información global del servidor (recursos, objetivos, etc.)
async def getInfo():
    try:
        r = await client.get(f"{SERVER_URL}info")
        return r.json()
    except Exception as e:
        logger.warning(f"No se pudo obtener info del servidor: {e}")
        return {}


# Función: obtiene un diccionario alias -> IP de todos los agentes
async def getGente():
    try:
        r = await client.get(f"{SERVER_URL}gente")
        personas = r.json()
        return {p["alias"]: p["ip"] for p in personas}
    except Exception as e:
        logger.error(f"Error obteniendo lista de gente: {e}")
        return {}


# Función: obtiene un diccionario IP -> alias
async def getGenteAlias():
    try:
        r = await client.get(f"{SERVER_URL}gente")
        personas = r.json()
        return {p["ip"]: p["alias"] for p in personas}
    except Exception as e:
        logger.error(f"Error obteniendo aliases por IP: {e}")
        return {}


# Función: envía un objeto (mensaje/paquete) a otro agente usando su IP
async def postObject(ip, obj):
    gente_alias = await getGenteAlias()
    alias = gente_alias.get(ip)

    if alias is None:
        logger.warning(f"postObject fallido: No se encontró alias para la IP {ip}")
        return None

    try:
        r = await client.post(
            f"{SERVER_URL}paquete/{alias}",
            json=obj
        )
        return r.json()
    except Exception as e:
        logger.error(f"Error en postObject hacia {alias}: {e}")
        return None
