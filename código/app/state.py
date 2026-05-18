# Estado global compartido entre diferentes módulos del sistema
import asyncio

# Centralizamos aquí la información para que todos los módulos
# trabajen con los mismos datos y evitar desorden o duplicados.
ip_time = {}

# Guardamos solo IPs activas para saber rápidamente qué agentes
# siguen disponibles dentro de la red.
list_ip = set()

# Separar las IPs pendientes permite controlar mejor
# cuáles necesitan comprobación sin repetir procesos.
list_ping = set()

# Mantener historial ayuda a que cada conversación tenga contexto
# y no parezca que el agente responde desde cero cada vez.
chat_history = {}

# Este estado permite tomar decisiones según la fase de interacción
# y evita comportamientos incoherentes.
chat_status = {}

# Registramos intercambios para hacer seguimiento y evitar
# perder operaciones importantes o repetirlas.
post_objects = {}

# El lock protege los datos compartidos cuando varias tareas
# intentan modificarlos al mismo tiempo.
lock = asyncio.Lock()
