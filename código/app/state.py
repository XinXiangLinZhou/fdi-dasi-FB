# Estado global compartido entre diferentes módulos del sistema
import threading

# Diccionario: guarda la última vez que cada IP respondió
ip_time = {}

# Conjunto: lista de IPs activas conocidas en el sistema
list_ip = set()

# Conjunto: IPs pendientes de verificación (ping)
list_ping = set()

# Diccionario: historial de conversación por IP
chat_history = {}

# Diccionario: estado de cada conversación (chatting, success, etc.)
chat_status = {}

# Diccionario: almacena intercambios realizados o pendientes
post_objects = {}

# Lock global: evita conflictos entre hilos al acceder a datos compartidos
lock = threading.Lock()