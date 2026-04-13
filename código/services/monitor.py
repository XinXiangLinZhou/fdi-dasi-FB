import time

from app.config import MY_ALIAS, PING_TIME, SLEEP_TIME
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


# Función: actualiza la lista de IPs activas a partir de la información del servidor
def update_ip():
    try:
        gente = getGente()

        new_ips = {
            ip for alias, ip in gente.items()
            if alias != MY_ALIAS
        }

        with lock:
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
        print("Error updating IP list:", e)


# Función: detecta agentes inactivos y los marca para volver a comprobar conexión
def check_inactive_ips():
    now = time.time()

    with lock:
        for ip in list_ip:
            last = ip_time.get(ip)

            if last is None:
                list_ping.add(ip)
            elif now - last > PING_TIME:
                if chat_status.get(ip, "chatting") == "chatting":
                    list_ping.add(ip)


# Función: inicia una conversación solo si todavía no existe historial con ese agente
def iniciar_chat_si_hace_falta(ip: str):
    ensure_chat(ip)

    with lock:
        status = chat_status.get(ip, "chatting")
        history_len = len(chat_history.get(ip, []))

    if status != "chatting":
        return

    # Solo se envía el primer mensaje si todavía no hubo conversación
    if history_len == 0:
        respuesta = generar_respuesta_ollama(ip)

        if respuesta["type"] == "text":
            primer_mensaje = respuesta["content"]
            add_history(ip, "assistant", primer_mensaje)
            ping(ip, {"msg": primer_mensaje})

        elif respuesta["type"] == "tool_call":
            tool_calls = respuesta["tool_calls"]
            if tool_calls:
                tool_result = ejecutar_tool_call(ip, tool_calls[0])
                mensaje_final = tool_result["message"]
                add_history(ip, "assistant", mensaje_final)
                ping(ip, {"msg": mensaje_final})


# Bucle principal: mantiene actualizado el estado de los agentes y lanza chats cuando hace falta
def loop():
    while True:
        try:
            update_ip()
            check_inactive_ips()

            with lock:
                current_ping_list = list(list_ping)

            for ip in current_ping_list:
                print(f"Iniciar o reanudar chat con {ip}")
                iniciar_chat_si_hace_falta(ip)

        except Exception as e:
            print("Loop error:", e)

        time.sleep(SLEEP_TIME)