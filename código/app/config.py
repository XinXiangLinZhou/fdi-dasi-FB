# Configuración global del sistema (valores por defecto y variables de entorno)
import os
import logging

# ===== Configuración del servidor central =====
# Se conecta con el servidor principal para que el agente pueda registrarse,
# recibir información del entorno y participar en el sistema común.
SERVER_URL = os.getenv("SERVER_URL", "http://147.96.80.104:7719/")


# ===== Configuración de Ollama =====
# Separamos la IA local del resto del sistema para poder cambiar modelo
# o endpoint fácilmente sin tocar toda la lógica del proyecto.
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "ministral-3:8b")


# ===== Configuración del agente =====
# Definimos una identidad propia y parámetros de red para que cada agente
# pueda funcionar de forma independiente dentro de la simulación.
MY_ALIAS = os.getenv("ALIAS", "FB")
MY_PORT = int(os.getenv("PORT", "7720"))
MY_HOST = os.getenv("HOST", "127.0.0.1")


# ===== Parámetros de tiempo =====
# Estos valores ayudan a controlar el ritmo del agente para evitar
# sobrecargar el sistema y mantener una comunicación estable.
SLEEP_TIME = int(os.getenv("SLEEP_TIME", "30"))
PING_TIME = int(os.getenv("PING_TIME", "60"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "12"))

# ===== Configuración de logging =====
# Usamos logging para detectar errores y seguir el comportamiento del agente
# de forma clara durante pruebas y depuración.
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("Agent")

