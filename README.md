# Sistema Inteligente de Intercambio de Recursos con IA (OLLAMA)

## Descripción

Este proyecto implementa un sistema multi-agente basado en IA que permite la negociación automática de recursos entre jugadores en un entorno distribuido.

El sistema utiliza FastAPI para la comunicación entre agentes y Ollama para la generación de respuestas mediante un modelo de lenguaje local.

---

## Funcionamiento

1. El agente recibe mensajes de otros jugadores.
2. Se actualiza el historial de conversación.
3. Se consulta el estado del juego.
4. El modelo de IA genera una respuesta o una acción.
5. Si existe un acuerdo válido, se ejecuta el intercambio.
6. El resultado se envía al servidor del juego.

---

## Tecnologías

- Python
- FastAPI
- Ollama
- HTTPX
- Asyncio
- JSON

---

## Ejecución

### 1. Configurar servidor

En `app/config.py`:

```Bash
SERVER_URL = "http://147.96.80.104:7719/"
```

### 2. Iniciar modelo en Ollama
```Bash
ollama run ministral-3:8B
```

### 3. Ejecutar el sistema
```Bash
uv run run.py
```

# Miembros
	- JIAHUI YOU
	- XIN XIANG LIN ZHOU
