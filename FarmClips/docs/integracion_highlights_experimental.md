# Highlights experimentales de FarmClips

La rama de trabajo local parte de `develop` en `48056e798b1e1e0094ec13dcdd28ab26493acb06`. La nota «Plan de Mejora - Calidad de Clips, Costos y Personalización» queda sin verificar. Se buscó por título y fragmentos en `FarmClips/vault/15 - Requerimientos/Notas de origen`, historial Git, carpetas locales, rutas Obsidian/iCloud y Google Drive. La nota de selector por sesión y HU-004 sí se consultaron en el Vault actual. Por ello la matriz distingue lo verificado en esas referencias de lo solicitado en el encargo de integración. La comparación de posibles conflictos con la nota exacta queda abierta.

## Trazabilidad

| Requisito y procedencia | Implementación en develop | Evidencia experimental | Cambio en esta rama | Prueba de aceptación |
|---|---|---|---|---|
| Elegir cantidad de clips por sesión · nota de origen del 13 de noviembre, HU-013 | `max_clips` en sesiones, curación y render | 787 propuestas, aproximadamente 110/h | Presupuesto de presentación independiente, 12 grupos/hora, IoU ≥ 0,50 anclada en V1, diversidad por modalidad y cuarto de hora, acceso a todos | Ver 9, 30 y 47 grupos por defecto en los tres VODs y poder recuperar todo |
| Ajustar inicio y fin de clips · HU-004. Revisar candidatos experimentales · encargo | `retime_clip`, editor y EditPlan de clips ya creados | Dos llamadas ampliadas, con segunda llamada que requiere extender el final; resultado de plataformas puede requerir más contexto | Previews con controles AV y límites en el reloj del VOD, más revisión separada. Evita crear un clip del pipeline de entrega por cada ajuste | Seek, reproducción, límites válidos y persistencia después de recarga |
| Calidad, ranking explicable y reproducibilidad · encargo; nota original pendiente | Curación LLM por ventana y resolución sobre transcripción/señales preparadas | V2 conserva 787 centros y amplía 295 cortes. 001824 entró al top 3 y fue no interesante; 008239 entró y fue interesante. V1 recupera las dos referencias vinculadas en puesto 11; V2 mejora un solapamiento por ajuste manual, con evidencia editorial mixta | Ranking V1 inicial, selector V2, cortes independientes, factores y cobertura, y revisión atada a la versión | Comparar JSON por ID, puesto, factores e intervalos. Mantener los ajustes de inspección exclusivamente en el snapshot histórico identificado por SHA |
| Aprender de decisiones · encargo; nota original pendiente | Los planes editados pertenecen a clips; las decisiones de selección/comparación requieren contrato propio | 12 positivos publicados, 14 revisiones V1 y seis V2; algunos IDs aparecen en ambas. Auditoría de Deepgram/GPT: 12 parciales, 10 desbordamientos, 32 relaciones temáticas y 23 dudosas | Importación de procedencia y hashes, historial con revisión esperada y reintento idempotente. Calibración manual conservadora de categorías humanas. Se excluyen etiquetas dudosas, una revisión por candidato y VOD en el cálculo | Importar 32 filas y reimportar cero. Datos actuales conservan baseline. Un perfil explícito se puede seleccionar y abandonar sin cambiar la ejecución |
| Costos y eficiencia · encargo; nota original pendiente | Caché de artefactos, presupuestos de API, preparación de medios, pools CPU/API/render, FFmpeg y SSE | El ranking usa RMS y cambio de imagen y puede confundir transiciones con interés | Reutilizar caché, pool CPU y binarios. Reusar salidas por hash, o extraer mono local y dos imágenes por semilla con refinamiento en hasta doce candidatos. Una ejecución activa por proceso, tope configurable de duración. La ruta experimental hace cero llamadas a proveedores | Comprobar tiempo por corrida, hash, cache hit, tarea aislada y cero cargos experimentales |
| Montar varios momentos · encargo; nota original pendiente | EditPlan, línea de tiempo y FilmCraft multicapa con exportación de sesión | El positivo histórico 7704463841949764865 reúne tramos discontinuos de una ventana de diez minutos | Contrato de tramos ordenados en un VOD con SHA. Adaptación a EditPlan queda pendiente de probar el mapeo de segmentos, audio y subtítulos | Validar tramos y orden, luego round-trip con edición/exportación en una fase posterior |

## Diseño y límites de esta integración

El panel acepta un MP4 desde una biblioteca local configurada. Emplea la tarea CPU y caché del orquestador cuando hay cálculo nuevo. Los estados quedan en SQLite y se consultan periódicamente en la interfaz. Se emite un evento al finalizar. Previews y descargas pasan por el proxy existente de Next.js. La API experimental vive bajo `/experimental/highlights/v1` y expone fuentes, ejecuciones, candidatos, multimedia, evidencia de fotogramas, revisiones, exportación, feedback importado y perfiles. Las tablas `highlight_runs`, `highlight_revisions` y `highlight_profiles` se crean al habilitar el módulo. Las propuestas quedan como artefactos JSON independientes. El módulo no crea filas en `clips` ni invoca render o publicación.

El detector obtiene primero semillas con medidas locales baratas. V1 conserva la fórmula 55/45 auditable y V2 añade respaldo acústico y cortes alrededor de pausas. Ambos describen actividad. Menús, resultados y cambios de escena pueden puntuar alto aunque la situación carezca de interés. Eventos quietos o apariciones breves pueden perderse en el muestreo. En VODs nuevos el reloj debe estar alineado dentro de 50 ms para estas reglas. La biblioteca usa H.264/AAC de los VODs suministrados. Otros MP4 dependen de su compatibilidad con navegador y FFmpeg.

El corpus publicado, las correspondencias y el perfil TF-IDF aportan hipótesis sobre sustos, reacciones, llamadas, cambios de situación y progresión de una historia. Los clips verticales incorporan edición posterior. La semejanza textual requiere candidatos con texto comparable, y la auditoría no habilita las relaciones texto-imagen para sincronía. Por ello la aplicación registra cobertura ausente para diálogo/narrativa en la extracción experimental y acepta una categoría humana. El siguiente insumo viable es reutilizar frases ya disponibles de sesiones con reloj verificado, solo alrededor de candidatos, para mostrar preparación, giro y desenlace como evidencia separada de intensidad. Esto se evaluaría primero en un VOD reservado sin ampliar el procesamiento por defecto.

La calibración compara tasas descriptivas por categoría, exige al menos tres decisiones de cada clase en tres VODs distintos y reduce el ajuste hacia cero con una constante de regularización. Las categorías provienen de revisiones explícitas del panel. Solo puede afectar candidatos categorizados ya conocidos. Cada perfil identifica las revisiones fuente y se guarda sin activación global. Los doce positivos y las exportaciones originales se importan como evidencia histórica diferenciada, sin trasladar categorías ni timestamps dudosos al ranking. El corpus actual no permite entrenar ni validar generalización. La exportación JSON conserva propuestas y decisiones. El montaje, el uso del editor completo y la exportación de un candidato como clip son posteriores al alcance del panel.

Claude Code revisó en solo lectura `config.py`, `db.py` y `routes.py` con la suscripción local. Se incorporaron la biblioteca confinada al directorio configurado, el control de origen local, la verificación de rangos HTTP y el seguimiento de trabajos. Codex realizó el resto de la arquitectura, cambios, pruebas y verificación. El flujo normal mantiene sus rutas y política de publicación.

## Generación y valoración desde una sesión

Con `CLIPS_EXPERIMENTAL_HIGHLIGHTS=1`, la generación habitual incluye el perfil editorial FarmClips 1.0 en la curación existente. Usa los patrones revisados para pedir preparación, giro, consecuencia y límites que hagan comprensible el momento. Una llamada puede conservar su desarrollo posterior si explica el desenlace. Los picos de sonido y los cambios de imagen tienen peso secundario. El orden y la selección entre propuestas solapadas usan 85 % de curación y 15 % de señal, una decisión inicial de implementación. El umbral de render usa la puntuación de entrega existente. El perfil emplea la llamada normal de curación y forma parte de la clave de caché. Al cambiar el perfil, reprocesar puede requerir una nueva llamada normal al proveedor.

Desde [Sesiones](http://127.0.0.1:3040/sessions), abrir una sesión con clips y desplegar **Valorar clip** en una tarjeta. La revisión guarda la decisión, una categoría opcional, el motivo y el intervalo exacto que se valoró. **Personalizar clip** abre el editor existente para cambiar ese intervalo. Si el corte se modifica mientras una valoración está abierta, el servidor pide recargar antes de guardar. El historial de cortes anteriores se conserva. La navegación solo muestra el flujo de sesiones habitual.

La comparación offline V1/V2 conserva sus resultados y su URL directa para regresión. El generador habitual usa las pautas editoriales y decide los límites mediante los IDs de frases y el preset de la sesión. El conjunto revisado no permite un modelo estadístico validado. Las valoraciones de clips de producción se guardan con su propia procedencia para trazabilidad y para una calibración posterior con fuentes comparables.

## Arranque en este Mac

Desde `/Users/usuario/Documents/Clips-farmclips-experimental/FarmClips`, en una terminal:

```sh
export FARMCLIPS_DEV_SITE_PACKAGES=/Users/usuario/Documents/Clips/FarmClips/.venv/lib/python3.12/site-packages
export CLIPS_EXPERIMENTAL_HIGHLIGHTS=1
export CLIPS_HIGHLIGHTS_VOD_DIR='/Users/usuario/Downloads/Clips/Videos/VODs Completos'
export CLIPS_HIGHLIGHTS_FREEZE=/Users/usuario/Downloads/Clips/cierre_preintegracion_v1
./scripts/farmclips-local.sh server
```

En otra terminal:

```sh
cd /Users/usuario/Documents/Clips-farmclips-experimental/FarmClips
./scripts/farmclips-local.sh web
```

Para reproducir las pruebas offline, abrir directamente el [comparador de referencia](http://127.0.0.1:3040/experimental/highlights). Elegir un VOD y pulsar **Analizar VOD**. Por defecto, el paquete de referencia se usa solo si coinciden las huellas. Marcar **Calcular desde el VOD** para ejecutar reglas locales. Seleccionar un candidato, reproducir el corte V1 o V2, ajustar los límites, guardar una decisión y recargar para comprobar el historial. **Ver todos** muestra la lista completa. **Previsualizar calibración** avisa si los datos son insuficientes. Cuando exista un perfil guardado, **Baseline** restaura la vista original.

Las dependencias web se instalan con `npm --prefix apps/web ci --no-audit --no-fund`. Si hace falta reconstruir la venv de este worktree, usar el Python 3.12 de la venv existente con `-m venv .venv`, conservando la variable `FARMCLIPS_DEV_SITE_PACKAGES`. El arranque local usa un SQLite aislado en `.venv/local-data` y deshabilita Drive. Para desactivar, detener el backend, ejecutar `unset CLIPS_EXPERIMENTAL_HIGHLIGHTS` y reiniciar. Se conservan el historial y los artefactos. Para usar otro directorio de datos o puerto, configurar `CLIPS_DATA_DIR` y `CLIPS_PORT` y hacer coincidir `CLIPS_SERVER_URL` del frontend. Mantener ambas interfaces ligadas a localhost.

## Resultados de validación

| Verificación local | Resultado |
|---|---|
| Paquete de los tres VODs | Lectura íntegra de 787 candidatos por versión con exactamente 295 ampliaciones V2. IDs, orden, cortes y factores coinciden con el JSON congelado. Los hashes de los VODs y del manifiesto se comprobaron. |
| Cálculo nuevo, sin usar el paquete para puntuar | Games-Demos 84 candidatos / 13,1 s, Just-Chatting 280 / 45,5 s, Recoger pelotas 423 / 86,4 s en este Mac. Los tres conservaron todos los IDs, puestos y puntuaciones. V1 conserva los 787 cortes y V2 conserva 783; los cuatro restantes corresponden a intervenciones manuales que solo están en el paquete histórico. |
| Progreso y frontend | Salud HTTP correcta, compilación TypeScript y build de Next.js. Prueba de Chrome con video y audio decodificados, preview V2, ajuste, guardado, recarga y cambio de ranking con acceso a todos. El salto directo en el VOD completo mostró carga irregular en el navegador; los cortes usan previews H.264/AAC de hasta 180 s, generados localmente al pedirlos y guardados en caché. |
| Revisión y aprendizaje | Revisión idempotente, límites inválidos rechazados, importación histórica de 32 filas y reimportación de cero, y baseline preservado ante falta de etiquetas. La calibración se verificó con datos sintéticos en pruebas. No se entrenó un modelo con los datos reales. |
| Flag apagado | Ruta experimental devuelve 404, rutas de sesiones y salud disponibles. |
| Suite heredada en este Mac | Misma selección de pruebas antes y después. Base: 47 pasan, 5 fallan, 2 omitidas. Integración: 53 pasan, los mismos 5 fallan y 2 omitidas. Fallan dos pruebas de lanzador Windows, el escenario dorado de render/entrega, una prueba de render con filtros de subtítulos y una de limpieza/caché. La colección MCP requiere un módulo `mcp` ausente en el entorno tanto para la base como para la rama. |
| Costos | Cero llamadas a APIs facturables de transcripción, visión, ranking o render. Se midieron tiempos de trabajo, no consumo energético ni memoria pico. |
