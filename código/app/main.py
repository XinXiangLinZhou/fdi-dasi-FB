# Aplicación FastAPI: punto de entrada que integra las rutas del sistema
from fastapi import FastAPI
from routes.buzon import router as buzon_router
from app.config import MY_ALIAS

# Crear la aplicación con el nombre del agente
app = FastAPI(title=f"Agent {MY_ALIAS}")

# Registrar las rutas (endpoint de comunicación entre agentes)
app.include_router(buzon_router)