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
)
from services.server_api import getGente
from services.ollama_agent import (
    ensure_chat,
    generar_respuesta_ollama,
    ejecutar_tool_call,
    add_history,
)
from services.peer_api import ping


# Actualizamos constantemente la red para trabajar solo con agentes reales
# y evitar perder tiempo con conexiones que ya no existen.
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

            # Detectar nuevos agentes permite integrarlos rápido
            # sin reiniciar el sistema.
            for ip in new_ips:
                if ip not in ip_time:
                    list_ping.add(ip)

            # Limpiar agentes desaparecidos evita usar datos obsoletos
            # que podrían generar errores o conversaciones falsas.
            old_ips = set(ip_time.keys()) - new_ips
            for ip in old_ips:
                ip_time.pop(ip, None)
                list_ping.discard(ip)
                chat_history.pop(ip, None)
                chat_status.pop(ip, None)
                post_objects.pop(ip, None)

    except Exception as e:
        logger.error(f"Error actualizando IP list: {e}")


# Revisar actividad permite detectar desconexiones
# y mantener la red actualizada de forma automática.
async def check_inactive_ips():
    now = time.time()
    NEGOTIATION_TIMEOUT = PING_TIME * 2

    async with lock:
        for ip in list_ip:
            last = ip_time.get(ip)

            if last is None:
                list_ping.add(ip)
            elif now - last > PING_TIME:
                if chat_status.get(ip, "chatting") == "chatting":
                    list_ping.add(ip)


# Solo iniciamos conversación cuando realmente hace falta
# para evitar mensajes duplicados o interacciones innecesarias.
async def iniciar_chat_si_hace_falta(ip: str):
    await ensure_chat(ip)

    async with lock:
        status = chat_status.get(ip, "chatting")
        history_len = len(chat_history.get(ip, []))

    if status != "chatting":
        return

    if history_len == 0:
        respuesta = await generar_respuesta_ollama(ip)

        # Diferenciamos texto y tool_call para adaptar la acción
        # según el tipo de respuesta generada.
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


# El loop principal mantiene todo funcionando de forma continua
# sin depender de intervención manual.
async def loop():
    while True:
        try:
            await update_ip()
            await check_inactive_ips()

            async with lock:
                current_ping_list = list(list_ping)

            # TaskGroup permite gestionar varios agentes a la vez
            # y hace el sistema más eficiente.
            if current_ping_list:
                async with asyncio.TaskGroup() as tg:
                    for ip in current_ping_list:
                        tg.create_task(iniciar_chat_si_hace_falta(ip))

        except Exception as e:
            logger.error(f"Error en el bucle: {e}")

        await asyncio.sleep(SLEEP_TIME)