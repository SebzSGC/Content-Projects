# Selección editorial y recopilaciones

FarmClips decide el formato dentro del flujo habitual de curación de cada sesión. Usa la transcripción y las señales que ya produce el pipeline. Con Gemini mantiene las mismas etapas y llamadas por ventana, con una instrucción y un contrato de salida ampliados. El cambio de contrato y del perfil genera una clave de caché nueva. El 85 % de curación y 15 % de señales siguen determinando el orden. El umbral existente sigue gobernando la entrega automática de los clips elegibles.

Una propuesta individual se resuelve en las frases presentadas por el curador. Una recopilación requiere dos acontecimientos distinguibles como mínimo, frases de evidencia dentro de cada tramo, explicación del vínculo, contexto inicial y cierre. Los tramos deben ser cronológicos, discontinuos y estar dentro de la ventana configurable de 600 s del VOD. El solapamiento se calcula sobre los tramos realmente retenidos. Se suprimen remates compartidos o montajes redundantes. La excepción de un individual requiere motivo de autonomía y remate distinto. El archivo `editorial_proposals.json` conserva tanto las propuestas como los resultados validados de la ejecución.

Se reutiliza `EditPlan.source.ranges` para la reproducción, el audio, los subtítulos, el render y los proyectos FilmCraft y OTIO. La sesión identifica el VOD y el ID del clip identifica el grupo. La información editorial de cada tramo, incluidos sus IDs de evidencia, queda en los datos del clip. Las tarjetas muestran el formato, la duración montada y los tramos cuando existen. El editor permite ajustar los límites de cada tramo en **Mezclador de Sonido y Ritmo**. **Valorar clip** guarda el formato y los tramos exactos revisados, junto con la nota y decisión. Estas revisiones quedan disponibles para una calibración posterior.

El suelo de 40 s se aplica después de los cortes rápidos y se vuelve a comprobar con FFprobe antes de marcar o entregar un MP4 final. Los archivos de trabajo y los proyectos editables pueden ser más breves. Los casos breves quedan disponibles para revisión. Se mantiene el máximo de 180 s montados que admite el editor. La ventana fuente de 600 s se modifica con `CLIPS_RELATED_WINDOW_SEC` y admite material de hasta 180 s montados. La comprobación de FFprobe mide el video y el contenedor, requiere pista de audio y comprueba la alineación básica de las pistas. El mezclador conserva el audio real de juego cuando el micrófono acaba antes.

La nota de origen `vault/15 - Requerimientos/Notas de origen/Plan de Mejora - Calidad de Clips, Costos y Personalización.md` quedó conciliada e integrada (EP-04 / HU-014). Además de la selección de formato (`individual` vs `recopilacion`) y el suelo de 40 s, el pipeline incorpora marcas explícitas de pausa (`--- [PAUSA Xs] ---`) y etiquetas de reacción (`[REACCIÓN]` / `[ALTA REACCIÓN]`) en el timeline compacto, ajuste dinámico de cola (`tail_pad`) guiado por el decaimiento de la reacción vocal, protección a 100 Hz en *jump cuts*, soporte nativo de modelos económicos DeepSeek con tarifas reales de *cache hit*, y aprendizaje editorial continuo (`build_learned_editorial_guidance`) a partir de las valoraciones de `ClipReview` y los diffs del editor (`edicion_estudio`). Las referencias utilizadas incluyen el montaje acústico parcial de plataformas, el plan de integración y la evidencia congelada de los tres VODs. La agrupación automática se valida contra IDs de transcripción y señales. Las pruebas de selección usan respuestas simuladas y evidencias de referencia. La capacidad de corregir montajes preserva el orden cronológico y permite modificar límites. La sesión mantiene el historial de valoraciones por intervalo.

## Arranque local en este Mac

Desde la raíz FarmClips de la rama, en la terminal del backend:

```sh
export FARMCLIPS_DEV_SITE_PACKAGES=/Users/usuario/Documents/Clips/FarmClips/.venv/lib/python3.12/site-packages
export CLIPS_FFMPEG=/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg
export CLIPS_FFPROBE=/opt/homebrew/opt/ffmpeg-full/bin/ffprobe
export CLIPS_EXPERIMENTAL_HIGHLIGHTS=1
./scripts/farmclips-local.sh server
```

En otra terminal de la misma raíz ejecutar `./scripts/farmclips-local.sh web` y abrir [Sesiones](http://127.0.0.1:3040/sessions). El análisis habitual selecciona el formato automáticamente. El flag habilita **Valorar clip**. Para procesar una grabación nueva con el proveedor real, se usan las credenciales de desarrollo de FarmClips y el flujo habitual de carga de gameplay y cámara.

## Pruebas sin llamadas facturables

Configurar los binarios de FFmpeg anteriores. Usar `source .venv/farmclips-env.sh` en este worktree para resolver los paquetes locales o instalar los paquetes Python de FarmClips en el entorno. Luego ejecutar:

```sh
.venv/bin/python -m pytest -q tests/test_editorial_formats.py tests/test_editorial_render.py tests/test_golden_e2e.py
.venv/bin/python scripts/verify_editorial_vods.py /Users/usuario/Downloads/Clips .venv/editorial-examples
(cd apps/web && ./node_modules/.bin/tsc --noEmit)
```

La prueba del render verifica imagen y frecuencia sonora a ambos lados del corte, además de los límites, la edición y las valoraciones. El script de referencias verifica los hashes de los tres VODs y del manifiesto, los 787 candidatos y las 295 ampliaciones congeladas. Renderiza el corte de llamada de 47 s sobre el VOD original. Los 34,9 s confirmados de plataformas y los 32 s de recoger pelotas se retienen para revisión. Todos los datos de estas pruebas se guardan fuera de la base de sesiones habitual.

## Resultados locales

- La sesión de prueba con proveedor simulado usó una sola llamada de curación. El flujo habitual produjo una recopilación de 48 s y un individual de 50 s, ambos con audio y video verificados por FFprobe.
- La prueba audiovisual aparte comprobó un montaje de 46 s con cambios de color y tono en la misma transición. El guion golden confirmó que un clip breve puede previsualizarse y que un ajuste manual suficiente habilita la entrega de un MP4 de 42 s con subtítulos.
- Chrome mostró ambos formatos en sesión, guardó un ajuste de tramo en el editor y mantuvo deshabilitada la exportación final de un clip de 12 s.
- La compilación de Next.js y TypeScript pasó. La suite ejecutada obtuvo 67 aprobadas, dos omitidas y dos fallos preexistentes del lanzador FilmCraft para Windows en este Mac. La colección MCP queda fuera de la corrida por la dependencia ausente ya registrada.
