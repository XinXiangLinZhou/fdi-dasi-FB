import time

from fastapi import APIRouter, Request

from app.models.mensaje import Mensaje
from app.state import ip_time, list_ping, lock
from app.config import logger
from services.peer_api import ping
from services.ollama_agent import (
    ensure_chat,
    add_history,
    generar_respuesta_ollama,
    ejecutar_tool_call,
    get_chat_status,
)

router = APIRouter()


# Endpoint principal: recibe mensajes de otros agentes y genera una respuesta automática
@router.post("/buzon")
async def buzon(request: Request, mensaje: Mensaje):
    client_ip = request.client.host
    texto_recibido = mensaje.msg
    now = time.time()
    logger.info(f"IP: {client_ip}")
    logger.info(f"mensaje: {texto_recibido}")

    # Actualizar estado de conexión del agente que envía el mensaje
    async with lock:
        ip_time[client_ip] = now
        list_ping.discard(client_ip)

    # Guardar mensaje recibido en el historial
    await ensure_chat(client_ip)
    await add_history(client_ip, "user", texto_recibido)

    # Comprobar si la conversación sigue activa
    status = await get_chat_status(client_ip)
    if status != "chatting":
        return {"status": status}

    # Generar respuesta usando el modelo (Ollama)
    respuesta = await generar_respuesta_ollama(client_ip)

    # Caso 1: respuesta de texto normal
    if respuesta.get("type") == "text":
        respuesta_texto = respuesta["content"]
        await add_history(client_ip, "assistant", respuesta_texto)

        result = await ping(client_ip, {"msg": respuesta_texto})

        return {
            "status": "sent",
            "response": result
        }

    # Caso 2: llamada a herramienta (intercambio)
    if respuesta["type"] == "tool_call":
        tool_calls = respuesta["tool_calls"]

        if not tool_calls:
            return {"status": "error", "msg": "tool_calls vacío"}

        #Evita ejecución de tools no autorizadas
        function_name = tool_calls[0].get("function", {}).get("name")
        if function_name != "finish_trade":
            return {
                "status": "error",
                "msg": "tool no permitido"
            }

        tool_result = await ejecutar_tool_call(client_ip, tool_calls[0])

        respuesta_texto = tool_result["message"]
        await add_history(client_ip, "assistant", respuesta_texto)

        result = await ping(client_ip, {"msg": respuesta_texto})

        return {
            "status": "success" if tool_result["ok"] else "error",
            "response": result,
            "trade": tool_result.get("trade")
        }

    return {"status": "error", "msg": "respuesta no válida de Ollama"}