# Modelos de datos usados en la comunicación (validación con Pydantic)
from pydantic import BaseModel


# Modelo: representa un mensaje simple entre agentes
class Mensaje(BaseModel):
    msg: str


# Modelo: representa una estructura de intercambio de recursos
class ListaRecursos(BaseModel):
    recursos: str
    cantidad: int
    accion: str  # aceptar, rechazar, contraoferta