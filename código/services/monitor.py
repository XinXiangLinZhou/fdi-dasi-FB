import time
import asyncio
from app.config import MY_ALIAS, PING_TIME, SLEEP_TIME, logger
from app.state import (
    ip_time,
    list_ip,
    list_ping,
    chat_history,
    chat_status,
    post_objects,
    lock,
    conversation_last_activity,
)
from services.server_api import getGente
from services.ollama_agent import (
    ensure_chat,
    generar_respuesta_ollama,
    ejecutar_tool_call,
    add_history,
)
from services.peer_api import ping


# Función: actualiza la lista de IPs activas a partir de la información del servidor
async def update_ip():
    try:
        gente = await getGente()

        new_ips = {
            ip for alias, ip in gente.items()
            if alias != MY_ALIAS
        }

        async with lock:
            list_ip.clear()
            list_ip.update(new_ips)

            for ip in new_ips:
                if ip not in ip_time:
                    list_ping.add(ip)

            old_ips = set(ip_time.keys()) - new_ips
            for ip in old_ips:
                ip_time.pop(ip, None)
                list_ping.discard(ip)
                chat_history.pop(ip, None)
                chat_status.pop(ip, None)
                post_objects.pop(ip, None)

    except Exception as e:
        logger.error(f"Error actualizando IP list: {e}")


# Función: detecta agentes inactivos y los marca para volver a comprobar conexión
async def check_inactive_ips():
    now = time.time()
    NEGOTIATION_TIMEOUT = PING_TIME * 2

    async with lock:
        for ip in list_ip:
            last = conversation_last_activity.get(ip)

            if last is None:
                list_ping.add(ip)
                continue

            if chat_status.get(ip, "chatting") == "chatting":
                if now - last > NEGOTIATION_TIMEOUT:
                    list_ping.add(ip)


# Función: inicia una conversación solo si todavía no existe historial con ese agente
async def iniciar_chat_si_hace_falta(ip: str):
    await ensure_chat(ip)

    async with lock:
        status = chat_status.get(ip, "chatting")
        history_len = len(chat_history.get(ip, []))

    if status != "chatting":
        return

    # Solo se envía el primer mensaje si todavía no hubo conversación
    if history_len == 0:
        respuesta = await generar_respuesta_ollama(ip)

        if respuesta["type"] == "text":
            primer_mensaje = respuesta["content"]
            await add_history(ip, "assistant", primer_mensaje)
            await ping(ip, {"msg": primer_mensaje})

        elif respuesta["type"] == "tool_call":
            tool_calls = respuesta["tool_calls"]
            if tool_calls:
                tool_result = await ejecutar_tool_call(ip, tool_calls[0])
                mensaje_final = tool_result["message"]
                await add_history(ip, "assistant", mensaje_final)
                await ping(ip, {"msg": mensaje_final})
        return

    # Si ya hubo conversación pero no se ha respondido en un tiempo, enviar un mensaje de seguimiento
    now = time.time()
    STALL_TIMEOUT = PING_TIME * 2
    last_activity = conversation_last_activity.get(ip)

    if last_activity is None:
        last_activity = now

    if now - last_activity > STALL_TIMEOUT:

        msg = "¿Sigues interesado en el intercambio?"

        await add_history(ip, "assistant", msg)
        await ping(ip, {"msg": msg})

        # Actualizar la última actividad para evitar enviar mensajes de seguimiento repetidos
        async with lock:
            conversation_last_activity[ip] = now


# Bucle principal: mantiene actualizado el estado de los agentes y lanza chats cuando hace falta
async def loop():
    while True:
        try:
            await update_ip()
            await check_inactive_ips()

            async with lock:
                current_ping_list = list(list_ping)

            if current_ping_list:
                async with asyncio.TaskGroup() as tg:
                    for ip in current_ping_list:
                        tg.create_task(iniciar_chat_si_hace_falta(ip))
        except Exception as e:
            logger.error(f"Error en el bucle: {e}")

        await asyncio.sleep(SLEEP_TIME)