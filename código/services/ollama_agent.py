import json
import re
from time import time
import httpx
from app.config import OLLAMA_URL, OLLAMA_MODEL, MY_ALIAS, MAX_HISTORY, logger
from app.state import chat_history, chat_status, post_objects, lock
from services.server_api import getInfo, getGenteAlias, postObject

# Se define una única herramienta controlada porque aceptar intercambios
# implica una acción crítica, así que debe limitarse para evitar decisiones inválidas.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "finish_trade",
            "description": (
                # La descripción fuerza validación porque el modelo por sí solo
                # puede equivocarse, y aquí se busca seguridad antes de ejecutar.
                "Usa esta herramienta SOLO cuando quieres confirmar un intercambio válido. "
                "El agente validará el intercambio antes de ejecutar la acción real. "
                "El intercambio debe ser 1 por 1."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {

                    # Se separa lo que das porque el sistema necesita claridad total
                    # sobre el coste propio antes de confirmar cualquier trato.
                    "give": {
                        "type": "object",
                        "description": f"Recurso que {MY_ALIAS} entrega. Ejemplo: {{\"madera\": 1}}"
                    },

                    # Se define lo que recibes porque negociar sin beneficio claro
                    # rompería la lógica estratégica del agente.
                    "receive": {
                        "type": "object",
                        "description": f"Recurso que {MY_ALIAS} recibe. Ejemplo: {{\"piedra\": 1}}"
                    },

                    # Se incluye mensaje porque además de ejecutar acciones,
                    # el agente necesita mantener comunicación social coherente.
                    "message": {
                        "type": "string",
                        "description": "Mensaje corto para enviar al otro jugador."
                    }
                },

                # Se exige todo porque una decisión incompleta
                # podría generar errores o intercambios ambiguos.
                "required": ["give", "receive", "message"]
            }
        }
    }
]


# Se crea este prompt separado porque iniciar conversación requiere persuadir,
# no simplemente reaccionar, así que la estrategia es más proactiva.
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
# Estas reglas limitan creatividad excesiva porque en negociación libre
# el modelo podría proponer opciones imposibles o perjudiciales.
- Solo puedes proponer intercambios de INTERCAMBIOS VÁLIDOS.
- El intercambio debe ser 1 por 1.
- No inventes recursos.
- No uses oro.
- No uses finish_trade todavía, porque el otro jugador no ha aceptado.
- Responde solo con texto natural.
- Nunca uses herramientas en este paso

EJEMPLO:
# El ejemplo guía formato porque reduce respuestas ambiguas
# y mejora consistencia en la generación.
"Puedo darte 1 madera por 1 piedra."
"""


# Se separa este prompt porque responder exige evaluar riesgo,
# no solo ofrecer, así que necesita lógica más defensiva.
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
# Aquí se controla cuándo usar herramienta porque aceptar
# tiene consecuencias reales y no debe activarse por error.
- Si quieres aceptar la propuesta, usa la herramienta finish_trade.
- Si no quieres aceptar, responde con texto natural.
- Si haces una contraoferta, responde con texto natural.
- No uses finish_trade para contraofertas.

REGLAS:
# Estas restricciones protegen estrategia y coherencia,
# evitando decisiones impulsivas o fuera de objetivo.
- Solo puedes aceptar intercambios que aparezcan en INTERCAMBIOS VÁLIDOS.
- No inventes recursos.
- No uses oro.
- Solo intercambios 1 por 1.
- En finish_trade, give es lo que TÚ entregas.
- En finish_trade, receive es lo que TÚ recibes.
- No escribas JSON manualmente. Usa la herramienta si aceptas.
- Si la propuesta exacta NO aparece en INTERCAMBIOS VÁLIDOS, no la aceptes.

EJEMPLO DE TOOL:
# El ejemplo práctico reduce errores estructurales
# y enseña al modelo cómo ejecutar correctamente.
give={{"madera": 1}}
receive={{"piedra": 1}}
message="Vale, trato hecho."

EJEMPLO DE TEXTO:
# También se muestra rechazo útil porque negociar
# no siempre significa aceptar o perder oportunidad.
"No puedo aceptar ese intercambio, pero puedo darte 1 madera por 1 piedra."
"""

# Se calculan faltantes porque el agente necesita identificar exactamente
# qué recursos le impiden cumplir su objetivo y así priorizar mejor sus decisiones.
def calcular_faltantes(recursos: dict, objetivo: dict) -> dict:
    faltantes = {}

    # Se compara objetivo con situación real porque negociar sin conocer carencias
    # haría que el agente actuara sin estrategia.
    for r, meta in (objetivo or {}).items():
        actual = int(recursos.get(r, 0))
        meta = int(meta)

        # Solo importa lo que falta, porque lo ya cumplido
        # no requiere inversión adicional.
        if meta > actual:
            faltantes[r] = meta - actual

    return faltantes


# Se calculan ofrecibles porque intercambiar recursos necesarios para uno mismo
# sería una mala estrategia y podría bloquear el progreso.
def calcular_ofrecibles(recursos: dict, objetivo: dict) -> dict:
    ofrecibles = {}

    for r, actual in (recursos or {}).items():
        actual = int(actual)

        # Se excluye oro porque es una restricción del sistema
        # y evita intercambios fuera de reglas.
        if r == "oro":
            continue

        meta = int(objetivo.get(r, 0))

        # Si el recurso ni siquiera forma parte del objetivo,
        # puede aprovecharse como moneda de intercambio.
        if r not in objetivo:
            if actual > 0:
                ofrecibles[r] = actual

        # Si ya se tiene más de lo necesario,
        # solo el excedente debería usarse.
        else:
            sobrante = actual - meta
            if sobrante > 0:
                ofrecibles[r] = sobrante

    return ofrecibles


# Se generan intercambios válidos porque el modelo necesita límites claros
# para no inventar propuestas inútiles o perjudiciales.
def generar_intercambios_validos(recursos: dict, objetivo: dict) -> list:
    ofrecibles = calcular_ofrecibles(recursos, objetivo)
    faltantes = calcular_faltantes(recursos, objetivo)

    intercambios = []

    # Se parte solo de recursos realmente disponibles,
    # porque no se puede negociar con lo que no sobra.
    for give_r, give_v in ofrecibles.items():
        if give_v < 1:
            continue

        # Se buscan solo recursos realmente necesarios,
        # porque recibir algo inútil no aporta progreso.
        for recv_r, recv_v in faltantes.items():
            if recv_v < 1:
                continue

            # Se evita cambiar un recurso por sí mismo
            # porque no tendría sentido estratégico.
            if give_r != recv_r:
                intercambios.append({
                    "give": {give_r: 1},
                    "receive": {recv_r: 1}
                })

    return intercambios


# Se normalizan datos porque agentes externos o modelos
# pueden generar formatos inconsistentes o inválidos.
def normalizar_trade_dict(d: dict) -> dict:
    limpio = {}

    # Si ni siquiera llega un diccionario válido,
    # se evita romper el sistema.
    if not isinstance(d, dict):
        return limpio

    for k, v in d.items():
        try:
            cantidad = int(v)

        # Se ignoran errores porque robustez significa
        # seguir funcionando incluso con entradas malas.
        except Exception:
            continue

        # Solo se aceptan cantidades positivas porque
        # cero o negativos romperían lógica de intercambio.
        if cantidad > 0:
            limpio[str(k).strip()] = cantidad

    return limpio


# Se valida 1 por 1 porque esta restricción simplifica reglas,
# reduce abusos y mantiene decisiones más predecibles.
def es_trade_uno_a_uno(give: dict, receive: dict) -> bool:

    # Debe existir exactamente un recurso por lado,
    # porque múltiples recursos romperían la norma.
    if len(give) != 1 or len(receive) != 1:
        return False

    give_qty = list(give.values())[0]
    recv_qty = list(receive.values())[0]

    # Ambas cantidades deben ser exactamente 1
    # para mantener equilibrio del sistema.
    if give_qty != 1 or recv_qty != 1:
        return False

    return True


# Se usa esta capa intermedia porque centralizar respuesta
# facilita modificar lógica futura sin cambiar llamadas externas.
def generar_respuesta(ip: str) -> dict:
    return procesar_respuesta_agent(ip)


# Se encapsula llamada al modelo porque separar comunicación externa
# mejora mantenimiento, control de errores y trazabilidad.
async def llamar_ollama(system_prompt: str, history: list, tools=None) -> dict:

    # Se añade system prompt primero porque define estrategia,
    # personalidad y límites antes del contexto conversacional.
    messages = [{"role": "system", "content": system_prompt}] + history

    # Se prepara configuración porque controlar modelo,
    # memoria y persistencia mejora estabilidad.
    data = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "keep_alive": "10m"
    }

    # Las herramientas solo se añaden cuando son necesarias,
    # para evitar activaciones innecesarias.
    if tools:
        data["tools"] = tools

    try:
        # Se usa cliente async porque eficiencia en red
        # permite escalar mejor múltiples conversaciones.
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(OLLAMA_URL, json=data)

        # Se registran respuestas porque depurar modelos
        # sin trazabilidad es mucho más difícil.
        logger.info(f"Status Ollama: {r.status_code}")
        logger.info(f"Respuesta cruda Ollama: {r.text}")

        r.raise_for_status()
        result = r.json()

        msg = result.get("message", {})

        # Si hay tool_calls, se prioriza acción estructurada
        # sobre texto ambiguo.
        if msg.get("tool_calls"):
            return {
                "type": "tool_call",
                "tool_calls": msg["tool_calls"]
            }

        content = msg.get("content", "")

        # Se fuerza formato texto porque estabilidad
        # importa más que asumir formatos raros.
        if not isinstance(content, str):
            content = ""

        return {
            "type": "text",
            "content": content.strip()
        }

    except Exception as e:
        # Se controla fallo porque un agente silencioso
        # es peor que uno imperfecto pero funcional.
        logger.error(f"Ollama error: {e}")

        # Respuesta fallback porque mantener conversación viva
        # es mejor que colapso total.
        return {
            "type": "text",
            "content": "Tengo algunos recursos para intercambiar. ¿Qué necesitas?"
        }

# Se genera respuesta de forma dinámica porque cada conversación depende
# del contexto actual, recursos reales y comportamiento del otro agente.
async def generar_respuesta_ollama(ip: str) -> dict:

    # Se consulta estado real antes de decidir porque negociar con datos antiguos
    # podría producir malas decisiones.
    info = await getInfo()
    recursos = info.get("Recursos", {})
    objetivo = info.get("Objetivo", {})

    # Se recalcula estrategia en tiempo real porque recursos y necesidades
    # pueden cambiar tras cada intercambio.
    faltantes = calcular_faltantes(recursos, objetivo)
    ofrecibles = calcular_ofrecibles(recursos, objetivo)
    intercambios_validos = generar_intercambios_validos(recursos, objetivo)

    # Se asegura historial porque decidir sin contexto previo
    # reduce coherencia conversacional.
    await ensure_chat(ip)

    async with lock:
        # Se copia historial para analizarlo sin comprometer
        # seguridad concurrente.
        history = list(chat_history[ip])

    # Se analiza último mensaje porque la intención más reciente
    # suele definir la acción inmediata.
    ultimo_msg_otro = obtener_ultimo_mensaje_del_otro(history)

    # Se intenta interpretar propuesta porque no todo mensaje
    # implica negociación válida.
    propuesta_otro = extraer_propuesta_del_otro(ultimo_msg_otro)

    # Se registra todo porque depurar estrategia compleja
    # requiere máxima visibilidad.
    logger.info(f"=======================")
    logger.info(f"Recursos: {recursos}")
    logger.info(f"Objetivo: {objetivo}")
    logger.info(f"Faltantes: {faltantes}")
    logger.info(f"Ofrecibles: {ofrecibles}")
    logger.info(f"Intercambios validos: {intercambios_validos}")
    logger.info(f"=======================")
    logger.info(f"Ultimo mensaje otro: {ultimo_msg_otro}")
    logger.info(f"Propuesta otro: {propuesta_otro}")

    # Si el otro ya hizo una propuesta clara,
    # conviene evaluar antes que iniciar una nueva.
    if propuesta_otro:

        # Se usa prompt defensivo porque aquí importa responder estratégicamente,
        # no simplemente generar oferta.
        system_prompt = build_prompt_response(
            MY_ALIAS,
            propuesta_otro,
            intercambios_validos
        )

        return await llamar_ollama(
            system_prompt=system_prompt,
            history=history,

            # Se habilitan tools porque aceptar requiere ejecución formal,
            # no solo conversación.
            tools=TOOLS
        )

    # Si no existe posibilidad válida,
    # es mejor detener negociación que improvisar mal.
    if not intercambios_validos:
        return {
            "type": "text",
            "content": "Ahora mismo no tengo intercambios válidos posibles."
        }

    # Si nadie propuso nada claro,
    # el agente toma iniciativa para buscar progreso.
    system_prompt = build_prompt_generate(
        MY_ALIAS,
        faltantes,
        ofrecibles,
        intercambios_validos
    )

    return await llamar_ollama(
        system_prompt=system_prompt,
        history=history,

        # Aquí no se usan tools porque todavía estamos negociando,
        # no cerrando trato.
        tools=None
    )


# Se transforma perspectiva porque el mensaje del otro puede estar expresado
# desde su visión, pero el sistema necesita coherencia desde la propia.
def propuesta_a_trade(propuesta_otro: dict):

    """
    Se adapta formato para evitar errores de interpretación
    entre lenguaje natural y ejecución lógica.
    """

    # Sin propuesta interpretable no se puede convertir nada,
    # así que se evita romper flujo.
    if not propuesta_otro:
        return {}, {}

    # Se extrae desde perspectiva propia porque validar correctamente
    # depende de saber exactamente qué doy y qué recibo.
    give = propuesta_otro.get("yo_doy", {})
    receive = propuesta_otro.get("yo_recibo", {})

    # Se normaliza porque incluso propuestas interpretadas
    # pueden contener inconsistencias.
    return normalizar_trade_dict(give), normalizar_trade_dict(receive)


# Se ejecuta tool_call con validación extra porque el modelo puede sugerir,
# pero la autoridad final debe ser del sistema.
async def ejecutar_tool_call(ip: str, tool_call: dict) -> dict:

    fn = tool_call.get("function", {})
    name = fn.get("name")

    arguments = fn.get("arguments", {})

    # Se parsea string porque algunos modelos devuelven argumentos
    # serializados y no directamente estructurados.
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)

        # Si falla parseo, se neutraliza para evitar
        # ejecutar basura.
        except Exception:
            arguments = {}

    # Se bloquean herramientas desconocidas porque permitir acciones no previstas
    # comprometería control.
    if name != "finish_trade":
        return {
            "ok": False,
            "message": "No entiendo la herramienta solicitada.",
            "trade": None
        }

    # Se normaliza todo porque incluso con tool_call
    # puede haber errores estructurales.
    give = normalizar_trade_dict(arguments.get("give", {}))
    receive = normalizar_trade_dict(arguments.get("receive", {}))
    message = arguments.get("message", "Trato hecho.")

    # Se asegura mensaje social válido porque interacción coherente
    # también importa.
    if not isinstance(message, str) or not message.strip():
        message = "Trato hecho."
    else:
        message = message.strip()

    # Se vuelve a consultar estado porque aceptar basado en datos antiguos
    # sería peligroso.
    info = await getInfo()
    recursos = info.get("Recursos", {})
    objetivo = info.get("Objetivo", {})

    # El modelo propone, pero el sistema verifica,
    # porque seguridad > creatividad.
    if not validar_trade(give, receive, recursos, objetivo):
        return {
            "ok": False,

            # Se rechaza con claridad para mantener comunicación útil
            # sin ejecutar errores.
            "message": "Lo siento, no puedo confirmar ese intercambio porque no es válido para mí.",
            "trade": None
        }

    async with lock:

        # Se guarda intercambio porque registrar acuerdos
        # permite trazabilidad y seguimiento.
        post_objects[ip] = {
            "ip": ip,
            "give": give,
            "receive": receive
        }

        # Se marca éxito porque así el sistema evita seguir negociando
        # innecesariamente.
        chat_status[ip] = "success"

    try:
        # Se ejecuta acción real solo después de validar todo,
        # minimizando riesgos.
        await postObject(ip, {
            "give": give,
            "receive": receive
        })

    except Exception as e:
        logger.error(f"postObject error: {e}")

        # Si falla envío real, no basta con intención;
        # debe notificarse error.
        return {
            "ok": False,
            "message": "Quería aceptar, pero hubo un error al enviar el intercambio.",
            "trade": None
        }

    # Solo aquí se confirma éxito porque ya pasó
    # validación + registro + ejecución real.
    return {
        "ok": True,
        "message": message,
        "trade": {
            "give": give,
            "receive": receive
        }
    }

# Se centraliza el procesamiento final porque la respuesta del modelo
# puede ser texto o acción, y el sistema necesita unificar decisiones.
async def procesar_respuesta_agent(ip: str) -> dict:

    # Primero se obtiene intención del modelo porque antes de actuar
    # hay que saber si quiere negociar o cerrar trato.
    respuesta = await generar_respuesta_ollama(ip)

    # Si el modelo intenta usar herramienta,
    # se interpreta como intención de confirmación formal.
    if respuesta.get("type") == "tool_call":
        tool_calls = respuesta.get("tool_calls", [])

        # Sin tool concreta no se puede ejecutar nada,
        # así que se protege el flujo.
        if not tool_calls:
            return {
                "message": "No he podido confirmar el intercambio.",
                "trade": None,
                "ok": False
            }

        # Solo se ejecuta tras pasar por capa de control,
        # porque modelo ≠ autoridad final.
        resultado = await ejecutar_tool_call(ip, tool_calls[0])

        # Se guarda historial porque incluso decisiones automáticas
        # deben quedar registradas para continuidad.
        await add_history(ip, "assistant", resultado["message"])

        return {
            "message": resultado["message"],
            "trade": resultado["trade"],
            "ok": resultado["ok"]
        }

    # Si no hay tool, se asume conversación natural,
    # priorizando continuidad social.
    content = respuesta.get("content", "").strip()

    # Se evita silencio porque una conversación vacía
    # rompe interacción.
    if not content:
        content = "¿Qué recursos tienes para intercambiar?"

    # Se guarda siempre porque contexto acumulado
    # mejora futuras respuestas.
    await add_history(ip, "assistant", content)

    return {
        "message": content,
        "trade": None,
        "ok": False
    }


# Se valida por última vez porque incluso si todo parece correcto,
# aceptar sin verificación puede romper estrategia.
def validar_trade(give: dict, receive: dict, recursos: dict, objetivo: dict):

    # Se limpia formato porque datos inconsistentes
    # pueden falsear validación.
    give = normalizar_trade_dict(give)
    receive = normalizar_trade_dict(receive)

    # Se recalcula lógica real porque recursos actuales
    # son la base de cualquier decisión correcta.
    ofrecibles = calcular_ofrecibles(recursos, objetivo)
    faltantes = calcular_faltantes(recursos, objetivo)

    # Sin datos claros no hay trato confiable.
    if not give or not receive:
        return False

    # Se exige regla principal para mantener sistema simple y seguro.
    if not es_trade_uno_a_uno(give, receive):
        return False

    give_r, give_v = next(iter(give.items()))
    recv_r, recv_v = next(iter(receive.items()))

    # Oro está prohibido por reglas globales,
    # así que cualquier aparición invalida trato.
    if give_r == "oro" or recv_r == "oro":
        return False

    # No puedes regalar lo que todavía necesitas,
    # porque sería sabotear tu propio objetivo.
    if give_r in faltantes:
        return False

    # Debes tener suficiente excedente real,
    # no solo intención.
    if ofrecibles.get(give_r, 0) < give_v:
        return False

    # Debes recibir algo útil para tu progreso,
    # no cualquier cosa.
    if recv_r not in faltantes:
        return False

    # No tiene sentido recibir más de lo que realmente falta
    # según lógica de validación actual.
    if faltantes.get(recv_r, 0) < recv_v:
        return False

    # Cambiar lo mismo por lo mismo sería absurdo.
    if give_r == recv_r:
        return False

    return True


# Se interpreta lenguaje natural porque otros agentes hablan como humanos,
# pero el sistema necesita estructura lógica.
def extraer_propuesta_del_otro(texto: str) -> dict | None:
    """
    Se traduce texto simple a formato estructurado
    para convertir conversación en decisiones ejecutables.
    """

    # Si entrada no sirve, mejor ignorar
    # que interpretar mal.
    if not isinstance(texto, str):
        return None

    # Se normaliza porque comparar texto libre
    # sin limpieza aumenta errores.
    t = texto.lower().strip() if texto else ""

    # Se usa patrón controlado porque limitar formatos
    # mejora precisión inicial.
    patron = r'(\d+)\s+([a-záéíóúñ]+)\s+por\s+(\d+)\s+([a-záéíóúñ]+)'
    m = re.search(patron, t)

    # Si no encaja patrón,
    # no se fuerza interpretación.
    if not m:
        return None

    qty_give = int(m.group(1))
    res_give = m.group(2).strip()
    qty_want = int(m.group(3))
    res_want = m.group(4).strip()

    # Se transforma desde perspectiva ajena hacia lógica propia
    # para responder correctamente.
    return {
        "peer_gives": {res_give: qty_give},
        "peer_wants": {res_want: qty_want},
        "yo_recibo": {res_give: qty_give},
        "yo_doy": {res_want: qty_want},
    }


# Se busca el último mensaje del otro porque en negociación
# lo más reciente suele tener prioridad táctica.
def obtener_ultimo_mensaje_del_otro(history: list) -> str:

    # Se recorre al revés porque así se encuentra antes
    # el contexto más actual.
    for msg in reversed(history):

        # Solo importa lo que dijo el otro,
        # no lo propio.
        if msg.get("role") == "user":
            content = msg.get("content", "")

            # Se asegura contenido usable
            # antes de devolverlo.
            if isinstance(content, str) and content.strip():
                return content.strip()

    return ""


# Se garantiza existencia del chat porque trabajar sobre estructuras inexistentes
# generaría errores.
async def ensure_chat(ip: str):
    async with lock:

        # Se crea historial solo cuando hace falta,
        # optimizando recursos.
        if ip not in chat_history:
            chat_history[ip] = []

        # Se establece estado base porque toda conversación
        # necesita punto de partida.
        if ip not in chat_status:
            chat_status[ip] = "chatting"


# Se añade historial porque memoria conversacional
# mejora coherencia estratégica.
async def add_history(ip: str, role: str, text: str):
    await ensure_chat(ip)

    async with lock:
        chat_history[ip].append({
            "role": role,
            "content": text
        })

        # Se limita tamaño porque demasiada memoria
        # puede afectar rendimiento.
        if len(chat_history[ip]) > MAX_HISTORY:
            chat_history[ip] = chat_history[ip][-MAX_HISTORY:]


# Se consulta estado porque decisiones futuras
# dependen de saber si sigue activo o terminó.
async def get_chat_status(ip: str) -> str:
    await ensure_chat(ip)

    async with lock:
        return chat_status.get(ip, "chatting")


# Se mide longitud porque a veces estrategia depende
# de saber cuánto contexto existe.
async def get_history_length(ip: str) -> int:
    await ensure_chat(ip)

    async with lock:
        return len(chat_history.get(ip, []))


# Se limpia chat porque mantener datos obsoletos
# puede causar errores o ruido estratégico.
async def clear_chat(ip: str):
    async with lock:

        # Se elimina todo rastro relevante para reiniciar
        # desde cero si hace falta.
        chat_history.pop(ip, None)
        chat_status.pop(ip, None)
        post_objects.pop(ip, None)
