import uvicorn
import asyncio

from app.main import app
from app.config import MY_HOST, MY_ALIAS, MY_PORT, logger
from services.server_api import postName, getGente
from services.monitor import loop

async def start():
    # Registrar el nombre del agente en el servidor central
    await postName()

    # Obtener la lista de agentes y sus IPs
    await asyncio.sleep(0.5)
    gente = await getGente()

    # Determinar la IP propia usando el alias
    my_host = gente.get(MY_ALIAS, MY_HOST)

    logger.info(f"Starting agent {MY_ALIAS} on {my_host}:{MY_PORT}")

    # Se lanza como tarea asíncrona para no bloquear el servidor web
    asyncio.create_task(loop())
    # Iniciar servidor FastAPI con uvicorn
    config = uvicorn.Config(app, host="0.0.0.0", port=7720)
    server = uvicorn.Server(config)
    await server.serve()

# Función principal: inicia el agente, registra el nombre en el servidor,
# obtiene su IP y lanza tanto el monitor como el servidor web
if __name__ == "__main__":

    # Iniciar el agente usando asyncio para manejar tareas concurrentes
    try:
        asyncio.run(start())
    except KeyboardInterrupt:
        logger.info("Cerrando Programa.")