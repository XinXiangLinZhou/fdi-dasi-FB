# Configuración global del sistema (valores por defecto y variables de entorno)
import os

# ===== Configuración del servidor central =====
# URL del servidor del profesor para registrar agentes y obtener información
SERVER_URL = os.getenv("SERVER_URL", "http://147.96.81.252:7719/")


# ===== Configuración de Ollama =====
# Endpoint y modelo usado para generar respuestas inteligentes
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "ministral-3:8b")


# ===== Configuración del agente =====
# Identidad y parámetros de red del agente
MY_ALIAS = os.getenv("ALIAS", "bunny")
MY_PORT = int(os.getenv("PORT", "7720"))
MY_HOST = os.getenv("HOST", "127.0.0.1")


# ===== Parámetros de tiempo =====
# Control de frecuencia del loop, ping y tamaño del historial
SLEEP_TIME = int(os.getenv("SLEEP_TIME", "30"))
PING_TIME = int(os.getenv("PING_TIME", "60"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "12"))
