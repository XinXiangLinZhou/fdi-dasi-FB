import threading
import uvicorn

from app.main import app
from app.config import MY_HOST, MY_ALIAS, MY_PORT
from services.server_api import postName, getGente
from services.monitor import loop


# Función principal: inicia el agente, registra el nombre en el servidor,
# obtiene su IP y lanza tanto el monitor como el servidor web
if __name__ == "__main__":

    # Registrar el nombre del agente en el servidor central
    postName()

    # Obtener la lista de agentes y sus IPs
    gente = getGente()

    # Determinar la IP propia usando el alias
    my_host = gente.get(MY_ALIAS, MY_HOST)

    print(f"Starting agent {MY_ALIAS} on {my_host}:{MY_PORT}")

    # Hilo secundario: ejecuta el loop de monitorización (ping, mensajes, etc.)
    thread = threading.Thread(
        target=loop,
        daemon=True
    )
    thread.start()

    # Iniciar servidor FastAPI con uvicorn
    uvicorn.run(app, host=getGente().get(MY_ALIAS), port=MY_PORT)