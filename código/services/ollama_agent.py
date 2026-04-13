import json
import re
import requests

from app.config import OLLAMA_URL, OLLAMA_MODEL, MY_ALIAS, MAX_HISTORY
from app.state import chat_history, chat_status, post_objects, lock
from services.server_api import getRecursos, getObjetivo, getGenteAlias, postObject


# Herramienta disponible para cerrar un intercambio válido
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "finish_trade",
            "description": f"Usa esta herramienta solo cuando el intercambio ya esté claramente aceptado por ambas partes. El intercambio debe ser estrictamente 1 por 1: un solo recurso con cantidad 1 que {MY_ALIAS} entrega, y un solo recurso con cantidad 1 que {MY_ALIAS} recibe.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "give": {
                        "type": "object",
                        "description": f"Exactamente un solo recurso que {MY_ALIAS} entrega, con cantidad 1. Ejemplo: {{'madera': 1}}"
                    },
                    "receive": {
                        "type": "object",
                        "description": f"Exactamente un solo recurso que {MY_ALIAS} recibe, con cantidad 1. Ejemplo: {{'piedra': 1}}"
                    },
                    "message": {
                        "type": "string",
                        "description": "Mensaje corto final de confirmación para enviar al otro jugador."
                    }
                },
                "required": ["give", "receive", "message"]
            }
        }
    }
]


# Función: calcula los recursos que todavía faltan para cumplir el objetivo
def calcular_faltantes(recursos: dict, objetivo: dict) -> dict:
    faltantes = {}
    for r, meta in (objetivo or {}).items():
        actual = int(recursos.get(r, 0))
        meta = int(meta)
        if meta > actual:
            faltantes[r] = meta - actual
    return faltantes


# Función: calcula qué recursos se pueden ofrecer sin perjudicar el objetivo propio
def calcular_ofrecibles(recursos: dict, objetivo: dict) -> dict:
    ofrecibles = {}
    for r, actual in (recursos or {}).items():
        actual = int(actual)
        if r == "oro":
            continue

        meta = int(objetivo.get(r, 0))

        if r not in objetivo:
            if actual > 0:
                ofrecibles[r] = actual
        else:
            sobrante = actual - meta
            if sobrante > 0:
                ofrecibles[r] = sobrante

    return ofrecibles


# Función: calcula cuánto oro se puede usar sin bajar de una reserva mínima
def calcular_oro_disponible(recursos: dict, reserva_min=10):
    oro = int(recursos.get("oro", 0))
    return max(0, oro - reserva_min)


# Función: inicializa el historial y el estado del chat si no existen
def ensure_chat(ip: str):
    with lock:
        if ip not in chat_history:
            chat_history[ip] = []
        if ip not in chat_status:
            chat_status[ip] = "chatting"


# Función: añade un mensaje al historial del chat y limita su tamaño
def add_history(ip: str, role: str, text: str):
    ensure_chat(ip)
    with lock:
        chat_history[ip].append({
            "role": role,
            "content": text
        })
        if len(chat_history[ip]) > MAX_HISTORY:
            chat_history[ip] = chat_history[ip][-MAX_HISTORY:]


# Función: interpreta una propuesta simple escrita por el otro jugador
def extraer_propuesta_del_otro(texto: str) -> dict | None:
    """
    Interpreta mensajes simples del otro tipo:
    - '1 tela por 1 vino'
    - 'te doy 1 tela por 1 vino'
    - '1 madera por 1 queso'
    
    IMPORTANTE:
    Siempre se interpreta desde la perspectiva DEL OTRO jugador:
    '1 tela por 1 vino' = el otro te da tela y quiere vino.
    """

    if not isinstance(texto, str):
        return None

    t = texto.lower().strip()

    patron = r'(\d+)\s+([a-záéíóúñ]+)\s+por\s+(\d+)\s+([a-záéíóúñ]+)'
    m = re.search(patron, t)
    if not m:
        return None

    qty_give = int(m.group(1))
    res_give = m.group(2).strip()
    qty_want = int(m.group(3))
    res_want = m.group(4).strip()

    return {
        "peer_gives": {res_give: qty_give},
        "peer_wants": {res_want: qty_want},
        "yo_recibo": {res_give: qty_give},
        "yo_doy": {res_want: qty_want},
    }


# Función principal: genera la respuesta del agente usando Ollama y el contexto del juego
def generar_respuesta_ollama(ip: str) -> dict:
    recursos = getRecursos() or {}
    objetivo = getObjetivo() or {}

    faltantes = calcular_faltantes(recursos, objetivo)
    ofrecibles = calcular_ofrecibles(recursos, objetivo)
    oro_disp = calcular_oro_disponible(recursos)
    intercambios_validos = generar_intercambios_validos(recursos, objetivo)

    ensure_chat(ip)

    with lock:
        history = list(chat_history[ip])

    ultimo_msg_otro = obtener_ultimo_mensaje_del_otro(history)
    propuesta_otro = extraer_propuesta_del_otro(ultimo_msg_otro)

    system_prompt = f"""
Eres {MY_ALIAS}, un jugador en un juego de intercambio.

TUS RECURSOS ACTUALES:
{recursos}

TU OBJETIVO FINAL:
{objetivo}

TUS FALTANTES:
{faltantes}

TUS RECURSOS OFRECIBLES:
{ofrecibles}

ORO DISPONIBLE:
{oro_disp}

INTERCAMBIOS VÁLIDOS QUE SÍ PUEDES HACER:
{intercambios_validos}

ÚLTIMO MENSAJE DEL OTRO JUGADOR:
{ultimo_msg_otro}

INTERPRETACIÓN DEL ÚLTIMO MENSAJE DEL OTRO JUGADOR:
{propuesta_otro}

REGLA MUY IMPORTANTE:
- El último mensaje siempre viene desde la perspectiva DEL OTRO jugador.
- Si el otro dice "1 tela por 1 vino", significa:
  - el otro te da 1 tela
  - el otro quiere 1 vino de ti
- Desde TU perspectiva, eso significa:
  - tú recibes 1 tela
  - tú entregas 1 vino

REGLAS OBLIGATORIAS:
- SOLO puedes razonar y responder desde TU perspectiva
- SOLO puedes proponer intercambios 1 por 1
- SOLO un recurso en give y SOLO un recurso en receive
- La cantidad SIEMPRE debe ser 1
- Nunca ofrezcas recursos que NO estén en "TUS RECURSOS OFRECIBLES"
- Nunca ofrezcas recursos que todavía necesitas
- Nunca inventes recursos
- Nunca hagas intercambios de muchos por muchos
- REGLA CRÍTICA (NO FALLAR),Cuando alguien dice "X por Y":
	- El otro jugador TE DA X
	- El otro jugador QUIERE Y
- Solo puedes proponer o aceptar intercambios que estén en "INTERCAMBIOS VÁLIDOS QUE SÍ PUEDES HACER"
- Si el otro te ofrece algo que tú no necesitas, rechaza o haz contraoferta
- Si el otro te pide algo que tú no puedes dar, rechaza o haz contraoferta
- Solo usa finish_trade cuando el otro jugador ya haya aceptado claramente
- Si no puedes hacer un intercambio válido, responde con texto corto
- Si no tienes ningún intercambio válido posible, responde solo con texto
- No uses oro en finish_trade

Ejemplo válido desde TU perspectiva:
give={{"madera": 1}}
receive={{"piedra": 1}}

Ejemplo inválido:
give={{"madera": 2, "trigo": 1}}
receive={{"piedra": 3}}

Responde corto y natural.
"""

    messages = [{"role": "system", "content": system_prompt}] + history

    data = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "tools": TOOLS,
        "stream": False,
        "keep_alive": "10m"
    }

    try:
        r = requests.post(OLLAMA_URL, json=data, timeout=60)
        print("Status Ollama:", r.status_code)
        print("Respuesta cruda Ollama:", r.text)

        r.raise_for_status()
        result = r.json()

        msg = result.get("message", {})

        if msg.get("tool_calls"):
            return {
                "type": "tool_call",
                "tool_calls": msg["tool_calls"]
            }

        content = msg.get("content", "")
        if not isinstance(content, str):
            content = ""

        content = content.strip()

        return {
            "type": "text",
            "content": content or "¿Qué recursos tienes para intercambiar?"
        }

    except Exception as e:
        print("Ollama error:", e)
        return {
            "type": "text",
            "content": "Tengo algunos recursos para intercambiar. ¿Qué tienes tú y qué necesitas?"
        }


# Función: obtiene el último mensaje enviado por el otro jugador
def obtener_ultimo_mensaje_del_otro(history: list) -> str:
    for msg in reversed(history):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                return content.strip()
    return ""


# Función: ejecuta la herramienta solicitada por Ollama y valida el intercambio
def ejecutar_tool_call(ip: str, tool_call: dict) -> dict:
    fn = tool_call.get("function", {})
    name = fn.get("name")

    arguments = fn.get("arguments", {})
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except Exception:
            arguments = {}

    if name == "finish_trade":
        give = normalizar_trade_dict(arguments.get("give", {}))
        receive = normalizar_trade_dict(arguments.get("receive", {}))
        message = arguments.get("message", "Trato hecho.")

        if not isinstance(message, str) or not message.strip():
            message = "Trato hecho."
        else:
            message = message.strip()

        recursos = getRecursos() or {}
        objetivo = getObjetivo() or {}

        if not validar_trade(give, receive, recursos, objetivo):
            return {
                "ok": False,
                "message": "Ese intercambio no es válido para mí.",
                "trade": None
            }

        with lock:
            post_objects[ip] = {
                "ip": ip,
                "give": give,
                "receive": receive
            }
            chat_status[ip] = "success"

        try:
            if give:
                postObject(ip, give)
        except Exception as e:
            print("postObject error:", e)

        return {
            "ok": True,
            "message": message,
            "trade": {
                "give": give,
                "receive": receive
            }
        }

    return {
        "ok": False,
        "message": "No entiendo la herramienta solicitada.",
        "trade": None
    }


# Función: devuelve el estado actual de una conversación
def get_chat_status(ip: str) -> str:
    ensure_chat(ip)
    with lock:
        return chat_status.get(ip, "chatting")


# Función: devuelve cuántos mensajes hay en el historial de un chat
def get_history_length(ip: str) -> int:
    ensure_chat(ip)
    with lock:
        return len(chat_history.get(ip, []))


# Función: limpia toda la información asociada a un chat
def clear_chat(ip: str):
    with lock:
        chat_history.pop(ip, None)
        chat_status.pop(ip, None)
        post_objects.pop(ip, None)


# Función: comprueba si un intercambio cumple las reglas del juego
def validar_trade(give: dict, receive: dict, recursos: dict, objetivo: dict):
    give = normalizar_trade_dict(give)
    receive = normalizar_trade_dict(receive)

    ofrecibles = calcular_ofrecibles(recursos, objetivo)
    faltantes = calcular_faltantes(recursos, objetivo)

    # 1) 必须严格 1 换 1
    if not es_trade_uno_a_uno(give, receive):
        return False

    give_r, give_v = next(iter(give.items()))
    recv_r, recv_v = next(iter(receive.items()))

    # 2) 先禁用 oro，避免模型拿黄金乱换
    if give_r == "oro" or recv_r == "oro":
        return False

    # 3) 不能把自己需要的东西送出去
    if give_r in faltantes:
        return False

    # 4) 送出去的必须真的是“可给的”
    if ofrecibles.get(give_r, 0) < give_v:
        return False

    # 5) 收到的必须是自己缺的
    if recv_r not in faltantes:
        return False

    # 6) 收到数量不能超过当前缺口（这里因为一换一，本质上就是必须为1）
    if faltantes.get(recv_r, 0) < recv_v:
        return False

    # 7) 不允许同种资源互换同种资源
    if give_r == recv_r:
        return False

    return True


# Función: limpia y normaliza el formato de un diccionario de intercambio
def normalizar_trade_dict(d: dict) -> dict:
    limpio = {}
    if not isinstance(d, dict):
        return limpio

    for k, v in d.items():
        try:
            cantidad = int(v)
        except Exception:
            continue

        if cantidad > 0:
            limpio[str(k).strip()] = cantidad

    return limpio


# Función: comprueba si el intercambio es estrictamente 1 por 1
def es_trade_uno_a_uno(give: dict, receive: dict) -> bool:
    if len(give) != 1 or len(receive) != 1:
        return False

    give_qty = list(give.values())[0]
    recv_qty = list(receive.values())[0]

    if give_qty != 1 or recv_qty != 1:
        return False

    return True


# Función: genera todas las combinaciones de intercambios válidos posibles
def generar_intercambios_validos(recursos: dict, objetivo: dict) -> list:
    ofrecibles = calcular_ofrecibles(recursos, objetivo)
    faltantes = calcular_faltantes(recursos, objetivo)

    intercambios = []
    for give_r, give_v in ofrecibles.items():
        if give_v < 1:
            continue
        for recv_r, recv_v in faltantes.items():
            if recv_v < 1:
                continue
            if give_r != recv_r:
                intercambios.append({
                    "give": {give_r: 1},
                    "receive": {recv_r: 1}
                })

    return intercambios
