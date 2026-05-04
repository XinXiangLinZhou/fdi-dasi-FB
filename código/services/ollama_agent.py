import json
import re
from time import time
import httpx
from app.config import OLLAMA_URL, OLLAMA_MODEL, MY_ALIAS, MAX_HISTORY, logger
from app.state import chat_history, chat_status, post_objects, lock, conversation_last_activity
from services.server_api import getInfo, getGenteAlias, postObject

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "finish_trade",
            "description": (
                "Usa esta herramienta SOLO cuando quieres confirmar un intercambio válido. "
                "El agente validará el intercambio antes de ejecutar la acción real. "
                "El intercambio debe ser 1 por 1."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "give": {
                        "type": "object",
                        "description": f"Recurso que {MY_ALIAS} entrega. Ejemplo: {{\"madera\": 1}}"
                    },
                    "receive": {
                        "type": "object",
                        "description": f"Recurso que {MY_ALIAS} recibe. Ejemplo: {{\"piedra\": 1}}"
                    },
                    "message": {
                        "type": "string",
                        "description": "Mensaje corto para enviar al otro jugador."
                    }
                },
                "required": ["give", "receive", "message"]
            }
        }
    }
]

#Para generar una propuesta de intercambio cuando el agente inicia la conversación.
def build_prompt_generate(my_alias, faltantes, ofrecibles, intercambios_validos):

    return f"""
Eres {my_alias}, un jugador en un juego de intercambio.

CONTEXTO:
Necesitas conseguir recursos para cumplir tu objetivo.

RECURSOS QUE NECESITAS:
{faltantes}

RECURSOS QUE PUEDES DAR:
{ofrecibles}

INTERCAMBIOS VÁLIDOS:
{intercambios_validos}

TAREA:
Genera UNA propuesta corta para otro jugador.

REGLAS:
- Solo puedes proponer intercambios de INTERCAMBIOS VÁLIDOS.
- El intercambio debe ser 1 por 1.
- No inventes recursos.
- No uses oro.
- No uses finish_trade todavía, porque el otro jugador no ha aceptado.
- Responde solo con texto natural.
- Nunca uses herramientas en este paso

EJEMPLO:
"Puedo darte 1 madera por 1 piedra."
"""

#Para decidir si aceptar, rechazar o contraofertar una propuesta recibida.
def build_prompt_response(my_alias, propuesta_otro, intercambios_validos):
    return f"""
Eres {my_alias}, un jugador en un juego de intercambio.

PROPUESTA DEL OTRO YA INTERPRETADA:
{propuesta_otro}

INTERCAMBIOS VÁLIDOS PARA TI:
{intercambios_validos}

TAREA:
Decide si aceptas, rechazas o haces una contraoferta.

DECISIÓN:
- Si quieres aceptar la propuesta, usa la herramienta finish_trade.
- Si no quieres aceptar, responde con texto natural.
- Si haces una contraoferta, responde con texto natural.
- No uses finish_trade para contraofertas.

REGLAS:
- Solo puedes aceptar intercambios que aparezcan en INTERCAMBIOS VÁLIDOS.
- No inventes recursos.
- No uses oro.
- Solo intercambios 1 por 1.
- En finish_trade, give es lo que TÚ entregas.
- En finish_trade, receive es lo que TÚ recibes.
- No escribas JSON manualmente. Usa la herramienta si aceptas.
- Si la propuesta exacta NO aparece en INTERCAMBIOS VÁLIDOS, no la aceptes.

EJEMPLO DE TOOL:
give={{"madera": 1}}
receive={{"piedra": 1}}
message="Vale, trato hecho."

EJEMPLO DE TEXTO:
"No puedo aceptar ese intercambio, pero puedo darte 1 madera por 1 piedra."
"""

def calcular_faltantes(recursos: dict, objetivo: dict) -> dict:
    faltantes = {}
    for r, meta in (objetivo or {}).items():
        actual = int(recursos.get(r, 0))
        meta = int(meta)
        if meta > actual:
            faltantes[r] = meta - actual
    return faltantes

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

# Para limpiar y estandarizar los datos de intercambio recibidos
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

def generar_respuesta(ip: str) -> dict:
    return procesar_respuesta_agent(ip)

async def llamar_ollama(system_prompt: str, history: list, tools=None) -> dict:
    messages = [{"role": "system", "content": system_prompt}] + history

    data = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "keep_alive": "10m"
    }

    if tools:
        data["tools"] = tools

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(OLLAMA_URL, json=data)
        logger.info(f"Status Ollama: {r.status_code}")
        logger.info(f"Respuesta cruda Ollama: {r.text}")

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

        return {
            "type": "text",
            "content": content.strip()
        }

    except Exception as e:
        logger.error(f"Ollama error: {e}")
        return {
            "type": "text",
            "content": "Tengo algunos recursos para intercambiar. ¿Qué necesitas?"
        }

async def generar_respuesta_ollama(ip: str) -> dict:
    info = await getInfo()
    recursos = info.get("Recursos", {})
    objetivo = info.get("Objetivo", {})

    faltantes = calcular_faltantes(recursos, objetivo)
    ofrecibles = calcular_ofrecibles(recursos, objetivo)
    intercambios_validos = generar_intercambios_validos(recursos, objetivo)

    await ensure_chat(ip)

    async with lock:
        history = list(chat_history[ip])

    ultimo_msg_otro = obtener_ultimo_mensaje_del_otro(history)
    propuesta_otro = extraer_propuesta_del_otro(ultimo_msg_otro)

    logger.info(f"Recursos: {recursos}")
    logger.info(f"Objetivo: {objetivo}")
    logger.info(f"Faltantes: {faltantes}")
    logger.info(f"Ofrecibles: {ofrecibles}")
    logger.info(f"Intercambios validos: {intercambios_validos}")
    logger.info(f"Ultimo mensaje otro: {ultimo_msg_otro}")
    logger.info(f"Propuesta otro: {propuesta_otro}")

    # Caso 1: hay propuesta clara del otro jugador
    if propuesta_otro:
        system_prompt = build_prompt_response(
            MY_ALIAS,
            propuesta_otro,
            intercambios_validos
        )

        return await llamar_ollama(
            system_prompt=system_prompt,
            history=history,
            tools=TOOLS
        )

    # Caso 2: no hay propuesta clara, genero una propuesta activa
    if not intercambios_validos:
        return {
            "type": "text",
            "content": "Ahora mismo no tengo intercambios válidos posibles."
        }

    system_prompt = build_prompt_generate(
        MY_ALIAS,
        faltantes,
        ofrecibles,
        intercambios_validos
    )

    return await llamar_ollama(
        system_prompt=system_prompt,
        history=history,
        tools=None
    )

def propuesta_a_trade(propuesta_otro: dict):
    """
    Convierte la propuesta interpretada del otro a formato de trade
    desde MI perspectiva.

    propuesta_otro:
    {
        "yo_doy": {"vino": 1},
        "yo_recibo": {"tela": 1}
    }

    return:
    give = {"vino": 1}
    receive = {"tela": 1}
    """
    if not propuesta_otro:
        return {}, {}

    give = propuesta_otro.get("yo_doy", {})
    receive = propuesta_otro.get("yo_recibo", {})

    return normalizar_trade_dict(give), normalizar_trade_dict(receive)

async def ejecutar_tool_call(ip: str, tool_call: dict) -> dict:
    fn = tool_call.get("function", {})
    name = fn.get("name")

    arguments = fn.get("arguments", {})

    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except Exception:
            arguments = {}

    if name != "finish_trade":
        return {
            "ok": False,
            "message": "No entiendo la herramienta solicitada.",
            "trade": None
        }

    give = normalizar_trade_dict(arguments.get("give", {}))
    receive = normalizar_trade_dict(arguments.get("receive", {}))
    message = arguments.get("message", "Trato hecho.")

    if not isinstance(message, str) or not message.strip():
        message = "Trato hecho."
    else:
        message = message.strip()

    info = await getInfo()
    recursos = info.get("Recursos", {})
    objetivo = info.get("Objetivo", {})

    # Seguridad final: Ollama decide aceptar, pero Agent valida antes de ejecutar
    if not validar_trade(give, receive, recursos, objetivo):
        return {
            "ok": False,
            "message": "Lo siento, no puedo confirmar ese intercambio porque no es válido para mí.",
            "trade": None
        }

    async with lock:
        post_objects[ip] = {
            "ip": ip,
            "give": give,
            "receive": receive
        }
        chat_status[ip] = "success"

    try:
        await postObject(ip, {
            "give": give,
            "receive": receive
        })
    except Exception as e:
        logger.error(f"postObject error: {e}")
        return {
            "ok": False,
            "message": "Quería aceptar, pero hubo un error al enviar el intercambio.",
            "trade": None
        }

    return {
        "ok": True,
        "message": message,
        "trade": {
            "give": give,
            "receive": receive
        }
    }

async def procesar_respuesta_agent(ip: str) -> dict:
    respuesta = await generar_respuesta_ollama(ip)

    if respuesta.get("type") == "tool_call":
        tool_calls = respuesta.get("tool_calls", [])

        if not tool_calls:
            return {
                "message": "No he podido confirmar el intercambio.",
                "trade": None,
                "ok": False
            }

        resultado = await ejecutar_tool_call(ip, tool_calls[0])

        await add_history(ip, "assistant", resultado["message"])

        return {
            "message": resultado["message"],
            "trade": resultado["trade"],
            "ok": resultado["ok"]
        }

    content = respuesta.get("content", "").strip()

    if not content:
        content = "¿Qué recursos tienes para intercambiar?"

    await add_history(ip, "assistant", content)

    return {
        "message": content,
        "trade": None,
        "ok": False
    }

def validar_trade(give: dict, receive: dict, recursos: dict, objetivo: dict):
    give = normalizar_trade_dict(give)
    receive = normalizar_trade_dict(receive)

    ofrecibles = calcular_ofrecibles(recursos, objetivo)
    faltantes = calcular_faltantes(recursos, objetivo)

    if not give or not receive:
        return False

    if not es_trade_uno_a_uno(give, receive):
        return False

    give_r, give_v = next(iter(give.items()))
    recv_r, recv_v = next(iter(receive.items()))

    if give_r == "oro" or recv_r == "oro":
        return False

    if give_r in faltantes:
        return False

    if ofrecibles.get(give_r, 0) < give_v:
        return False

    if recv_r not in faltantes:
        return False

    if faltantes.get(recv_r, 0) < recv_v:
        return False

    if give_r == recv_r:
        return False

    return True

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

    t = texto.lower().strip() if texto else ""

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

def obtener_ultimo_mensaje_del_otro(history: list) -> str:
    for msg in reversed(history):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                return content.strip()
    return ""

async def ensure_chat(ip: str):
    async with lock:
        if ip not in chat_history:
            chat_history[ip] = []
        if ip not in chat_status:
            chat_status[ip] = "chatting"

# Función: añade un mensaje al historial del chat y limita su tamaño
async def add_history(ip: str, role: str, text: str):
    await ensure_chat(ip)
    async with lock:
        conversation_last_activity[ip] = time.time()
        chat_history[ip].append({
            "role": role,
            "content": text
        })
        if len(chat_history[ip]) > MAX_HISTORY:
            chat_history[ip] = chat_history[ip][-MAX_HISTORY:]

# Función: devuelve el estado actual de una conversación
async def get_chat_status(ip: str) -> str:
    await ensure_chat(ip)
    async with lock:
        return chat_status.get(ip, "chatting")

# Función: devuelve cuántos mensajes hay en el historial de un chat
async def get_history_length(ip: str) -> int:
    await ensure_chat(ip)
    async with lock:
        return len(chat_history.get(ip, []))

# Función: limpia toda la información asociada a un chat
async def clear_chat(ip: str):
    async with lock:
        chat_history.pop(ip, None)
        chat_status.pop(ip, None)
        post_objects.pop(ip, None)