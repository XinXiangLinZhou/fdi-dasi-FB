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


Miembros: ALONSO CAMPILLO MARTÍNEZ, ERICKA DEL VALLE BRACHO PÉREZ, JIAHUI YOU, LUIS ÁNGEL GARCÍA ROJAS, SHOMARA DEYANIRA ACOSTA SANTANA, XIN XIANG LIN ZHOU.

Hemos trabajado en diferentes ramas:

Rama test: es la rama inicial que estamos trabajando-> mian.py es el código inicial de la comunicación sin meter ollama, distintos ficheros test/pruebas son para probar metiendo ollama y flujo de arquitecturas.

Rama Dev: es la rama que tenemos la estructura inicial de los códigos.

Rama main: es la rama final con estructura de código final y con versión final de código metiendo ollama.


