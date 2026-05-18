# Comunicación con el servidor del profesor (API central)
from app.config import SERVER_URL, MY_ALIAS, logger
import httpx

# Mantener un cliente reutilizable mejora eficiencia
# y evita crear conexiones nuevas constantemente.
client = httpx.AsyncClient(timeout=10.0)


# Registrarse permite que el agente exista oficialmente dentro del sistema
# y pueda interactuar con el resto desde el principio.
async def postName():
    try:
        await client.post(f"{SERVER_URL}alias/{MY_ALIAS}")
    except Exception as e:
        logger.error(f"Error en postName: {e}")


# Consultamos información global para tomar decisiones
# basadas en el estado real del entorno.
async def getInfo():
    try:
        r = await client.get(f"{SERVER_URL}info")
        return r.json()
    except Exception as e:
        logger.warning(f"No se pudo obtener info del servidor: {e}")
        return {}


# Tener acceso a alias e IPs facilita localizar agentes
# sin depender de datos manuales o fijos.
async def getGente():
    try:
        r = await client.get(f"{SERVER_URL}gente")
        personas = r.json()
        return {p["alias"]: p["ip"] for p in personas}
    except Exception as e:
        logger.error(f"Error obteniendo lista de gente: {e}")
        return {}


# Esta versión inversa ayuda cuando primero conocemos la IP
# y necesitamos identificar rápidamente al agente.
async def getGenteAlias():
    try:
        r = await client.get(f"{SERVER_URL}gente")
        personas = r.json()
        return {p["ip"]: p["alias"] for p in personas}
    except Exception as e:
        logger.error(f"Error obteniendo aliases por IP: {e}")
        return {}


# Enviar objetos mediante alias reduce errores
# y mantiene la comunicación más organizada.
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

    # Gestionamos fallos para que problemas externos
    # no bloqueen el flujo general del sistema.
    except Exception as e:
        logger.error(f"Error en postObject hacia {alias}: {e}")
        return None
