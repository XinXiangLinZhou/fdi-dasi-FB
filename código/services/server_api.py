# Comunicación con el servidor del profesor (API central)
import requests

from app.config import SERVER_URL, MY_ALIAS


# Función: registra el alias del agente en el servidor si aún no existe
def postName():
    try:
        gente = getGente()
        if gente.get(MY_ALIAS) is None:
            requests.post(SERVER_URL + f"alias/{MY_ALIAS}", timeout=3)
    except Exception as e:
        print("postName error:", e)


# Función: obtiene toda la información global del servidor (recursos, objetivos, etc.)
def getInfo():
    info = requests.get(SERVER_URL + "info", timeout=3)
    return info.json()


# Función: devuelve los recursos disponibles del agente
def getRecursos():
    informacion = getInfo()
    return informacion["Recursos"]


# Función: devuelve los objetivos que el agente necesita conseguir
def getObjetivo():
    informacion = getInfo()
    return informacion["Objetivo"]


# Función: obtiene un diccionario alias -> IP de todos los agentes
def getGente():
    gente = requests.get(SERVER_URL + "gente", timeout=3)
    personas = gente.json()

    jugadores = {}
    for p in personas:
        jugadores[p["alias"]] = p["ip"]

    return jugadores


# Función: obtiene un diccionario IP -> alias (inverso de getGente)
def getGenteAlias():
    gente = requests.get(SERVER_URL + "gente", timeout=3)
    personas = gente.json()

    jugadores = {}
    for p in personas:
        jugadores[p["ip"]] = p["alias"]

    return jugadores


# Función: envía un objeto (mensaje/paquete) a otro agente usando su IP
def postObject(ip, obj):
    alias = getGenteAlias().get(ip)

    if alias is None:
        print(f"postObject error: no alias encontrado para IP {ip}")
        return

    requests.post(
        SERVER_URL + "paquete/" + alias,
        json=obj,
        timeout=3
    )