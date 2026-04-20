Para la ejecución del sistema es necesario:

- Disponer de Python instalado.

- Tener configurado uv para la gestión de dependencias.

- Contar con el servidor del juego en funcionamiento.

- Tener Ollama instalado y ejecutando el modelo seleccionado.

- Disponer de conectividad entre los jugadores.

Pasos básicos de ejecución:

- Iniciar el servidor del juego.

- Cambiar ip del servidor en código/app/config.py en esta linea del código

        SERVER_URL = os.getenv("SERVER_URL", "http://147.96.81.252:7719/")

- Ejecutar Ollama con el modelo correspondiente.

        bin/ollama run ministral-3:8B
    
- Lanzar la aplicación FastAPI entrando carpeta código.

        uv run run.py
    
- Verificar el registro del agente.

- Iniciar la interacción entre jugadores.


Miembros: JIAHUI YOU, XIN XIANG LIN ZHOU.


