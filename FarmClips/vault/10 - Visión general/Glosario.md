---
titulo: Glosario de términos
tipo: glosario
estado: vigente
audiencia: [negocio, tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/glosario, area/general]
---

# Glosario de términos

> [!abstract] En pocas palabras
> Diccionario central de conceptos técnicos, acrónimos y vocabulario audiovisual utilizados en FarmClips. Cada definición incluye su explicación sencilla y su aplicación real dentro de la aplicación.

---

### Arquitectura Híbrida
Modelo de diseño donde las tareas inteligentes de análisis textual y curación narrativa se delegan a modelos de inteligencia artificial en la nube mediante API ligeras, mientras que el transporte, decodificación, tracking y renderizado de video pesado se ejecutan al 100 % de forma local en la máquina del usuario.

### Shorts
Formato de video vertical en relación de aspecto 9:16 (resolución estándar de $1080 \times 1920$ píxeles), de duración comprendida entre 20 y 60 segundos, optimizado para plataformas como YouTube Shorts, TikTok e Instagram Reels.

### LUFS
*Loudness Units relative to Full Scale*. Estándar internacional de medición de volumen sonoro percibido por el oído humano. FarmClips normaliza automáticamente todo el audio final a $-14\text{ LUFS}$ con verdadero pico (True Peak) a $-1.0\text{ dBTP}$ para cumplir las especificaciones de YouTube y TikTok sin distorsiones ni caídas de volumen.

### Hormozi Gaming
Estilo de edición audiovisual y subtitulado viral caracterizado por tipografías gruesas e impactantes (Montserrat ExtraBold), resaltado dinámico palabra por palabra con colores contrastantes (amarillo `#FFD400`, verde énfasis `#39FF14`), títulos magnéticos en el tercio superior y emojis en alta resolución superpuestos al ritmo de la voz.

### FFmpeg
Conjunto de librerías y herramienta de línea de comandos de código abierto para decodificar, procesar, sincronizar, mezclar y codificar audio y video en prácticamente cualquier formato existente.

### XCorr FFT
*Cross-Correlation Fast Fourier Transform* (Correlación cruzada mediante transformada rápida de Fourier). Algoritmo matemático empleado en FarmClips para alinear milimétricamente el audio del juego con el audio del micrófono de la cámara, encontrando el retraso temporal exacto entre ambas fuentes sin necesidad de claqueta manual.

### MediaPipe
Framework de aprendizaje automático desarrollado por Google. En FarmClips se utiliza el modelo `blaze_face_short_range.tflite` sobre CPU para detectar y seguir el rostro del creador frame a frame a 15 cuadros por segundo, recortando solo el área del streamer para mantenerlo centrado.

### NVENC
Codificador por hardware integrado en las tarjetas gráficas NVIDIA (NVIDIA Encoder). Permite renderizar y exportar videos en formato H.264 a resoluciones de 1080p a alta velocidad sin saturar el procesador del ordenador.

### libx264
Codificador por software libre para compresión de video H.264 ejecutado en el procesador principal (CPU). Actúa como respaldo automático y configurable en caso de no disponer de tarjeta gráfica NVIDIA o en entornos de renderizado por lotes.

### libass
Librería de renderizado de subtítulos altamente configurable y eficiente para el estándar Advanced SubStation Alpha (`.ass`). Soporta animaciones por frame, deformaciones, escalado tipográfico y cambios cromáticos instantáneos.

### STT
*Speech-to-Text* (Transcripción de voz a texto). Proceso que convierte la señal acústica de la voz del streamer en palabras con marcas de tiempo exactas. En FarmClips se apoya primariamente en Deepgram Nova-3 y con respaldo en Groq Whisper Large v3 Turbo.

### LLM
*Large Language Model* (Modelo de lenguaje extenso). Inteligencia artificial generativa encargada de comprender la narrativa de la partida, calificar el valor de entretenimiento de cada escena y seleccionar los fragmentos más destacados (Gemini 3.5 Flash-Lite u OpenAI GPT-6 Luna).

### Utterance
Unidad lingüística continua o frase hablada con sentido completo dentro de la línea de tiempo. Se compone de un identificador único (p. ej. `u0015`), una marca de tiempo de inicio, una marca de fin y una lista de palabras individuales con sus respectivos tiempos milimétricos.

### ID de Frase
Identificador alfanumérico compacto (desde `u0001` hasta `u9999`) asignado a cada frase detectada en la transcripción. El LLM trabaja únicamente con estos códigos de texto, reduciendo drásticamente el consumo de tokens y evitando errores de cálculo numérico de tiempos.

### Ataque Acústico
Instante de inicio enérgico de una vocal o consonante explosiva en la señal sonora. FarmClips analiza la envolvente de la señal a 100 Hz para ajustar el corte del video justo antes del ataque acústico de la primera palabra, evitando cortar palabras por la mitad o dejar silencios molestos.

### Idempotencia
Propiedad de un sistema por la cual una operación ejecutada múltiples veces produce el mismo resultado sin generar efectos secundarios ni costos adicionales. FarmClips cachea en SQLite cada respuesta de API y cada artefacto computado; si una sesión se reintenta, no se vuelve a pagar ni un centavo en APIs.

### Leases
Mecanismo de concurrencia y tolerancia a fallos donde un proceso adquiere el derecho exclusivo de ejecutar una tarea computacional pesada (p. ej. calcular señales) durante un tiempo determinado (lease time). Si el servidor se apaga abruptamente, al reiniciar detecta los leases expirados y los reanuda sin duplicar procesos.

### Score
Calificación numérica del 0 al 100 que mide el potencial viral y la calidad técnica de un clip. Combina la evaluación narrativa del modelo de lenguaje (`llm_score`, 60 %) con la intensidad de la euforia acústica y movimiento en pantalla (`signal_score`, 40 %).

### SQLite WAL
Motor de base de datos relacional local configurado con *Write-Ahead Logging* (WAL). Permite que múltiples procesos de lectura y escritura concurrentes (servidor web, orquestador, tareas en background) operen de forma fluida sin bloqueos de base de datos.

### One Euro Filter
Filtro adaptativo de suavizado de señales en tiempo real diseñado para eliminar el temblor (jitter) cuando el rostro está casi quieto, manteniendo una respuesta inmediata y sin retardo (lag) durante movimientos rápidos de la cabeza.

### RDP
*Ramer-Douglas-Peucker*. Algoritmo matemático de simplificación de trayectorias y curvas poligonales. Reduce miles de coordenadas continuas de posición facial a unas pocas decenas de puntos clave indispensables para el encuadre, ahorrando memoria y cálculos en el renderizado.

### Deadband
Zona muerta de tolerancia espacial. Si el rostro del streamer se desplaza menos de un porcentaje determinado respecto al centro de la cámara (p. ej. menos del 8 %), el sistema no mueve el encuadre, evitando mareos en la visualización del video vertical.

### ApiPool
Módulo asíncrono del servidor encargado de gestionar todas las comunicaciones externas hacia servicios de IA (STT, LLM). Aplica limitadores triples de velocidad (concurrencia máxima, peticiones por minuto y presupuesto acumulado en dólares), reintentos con retraso exponencial y cortacircuitos de respaldo.

### CpuPool
Módulo de ejecución basado en un grupo de procesos de Python (`ProcessPoolExecutor`) que paraleliza las tareas pesadas de computación local (extracción de audio, envolventes acústicas a 100 Hz, movimiento por visión artificial y tracking facial) sin bloquear el servidor web.

### RenderPool
Cola de renderizado de alta prioridad que asigna sesiones de exportación de video a la tarjeta gráfica NVIDIA (NVENC) o a la CPU (libx264), garantizando que las previsualizaciones rápidas y los clips finales no colapsen la memoria del sistema.

### EditPlan
Contrato declarativo estructurado en formato JSON (versión 2) que define la edición completa de un clip: rangos de tiempo del video original, disposición de cámaras (split, pantalla completa), encuadres dinámicos, subtítulos animados con tiempos por palabra, emojis y mezcla de audio.

### Web Audio API
Estándar del navegador web para procesamiento y mezcla de audio de alto rendimiento en JavaScript. El editor interactivo de FarmClips utiliza esta API para aplicar ganancias de micrófono, efectos de atenuación sobre el juego y reproducción de efectos sonoros en tiempo real sin tener que procesar archivos en disco.

### FastCompositor
Módulo de renderizado de video acelerado en C++ (`cv2.warpAffine`) que aplica transformaciones afines, recortes, paneos y transiciones suaves de cámara de forma ultra veloz antes de enviar los fotogramas al codificador de video.

### Loudnorm
Filtro de audio de FFmpeg que analiza y normaliza la sonoridad acústica en dos pasadas consecutivas, asegurando que el clip cumpla estrictamente los estándares de sonoridad integrada ($-14\text{ LUFS}$), rango dinámico (LRA) y pico real (True Peak) sin producir saturación ni compresión desagradable.

### Keyterms
Lista de palabras clave, nombres propios y términos específicos de jerga de videojuegos (p. ej. *clutch, headshot, spike, ulti, flankear*) que se inyectan en el prompt de la transcripción para mejorar la precisión fonética del modelo STT.

### Killfeed
Zona específica de la pantalla de videojuegos de disparos donde se muestran las bajas consecutivas y eventos relevantes. FarmClips incluye un analizador de actividad visual que detecta cambios rápidos en estas regiones para elevar la puntuación del clip.

### Webhook
Mecanismo de comunicación automatizado mediante peticiones HTTP POST por el cual FarmClips notifica en tiempo real a canales de Discord, Slack o servidores de terceros cuando un clip final ha sido renderizado y entregado con éxito.

### TTL
*Time-To-Live* (Tiempo de vida útil). Política de mantenimiento automático que elimina archivos temporales (como fragmentos de audio Opus intermedios o frames de tracking) que hayan superado un número configurable de días, liberando espacio en disco de forma transparente.

### Ducking Sidechain
Técnica de procesamiento de audio donde el volumen de una señal secundaria (el audio del videojuego) se reduce automáticamente de manera proporcional cuando la señal principal (la voz del streamer en el micrófono) está activa, garantizando total claridad en el discurso.

### Jump Cut
Técnica de montaje de video donde se eliminan fragmentos muertos o pausas de silencio prolongadas uniendo directamente los momentos hablados, logrando un ritmo dinámico e ininterrumpido en el video vertical final.

---

## 🔗 Relacionado
- [[Resumen ejecutivo]]
- [[Arquitectura general]]
- [[Contrato EditPlan v2]]
- [[Modelo de datos]]