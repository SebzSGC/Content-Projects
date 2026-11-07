---
titulo: "ADR-001 Arquitectura Híbrida: IA en la Nube y Proceso Local"
tipo: decision
estado: vigente
audiencia: [tecnico, negocio]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/decision, area/arquitectura]
---

# ADR-001: Arquitectura Híbrida — IA por API y Procesamiento Multimedia Local

> [!abstract] En pocas palabras
> Registra la decisión fundacional de no subir gigabytes de video crudo a la nube y no correr modelos pesados de video en la GPU local, dividiendo las tareas entre APIs livianas de lenguaje y procesamiento multimedia en disco con FFmpeg.

---

## 🎯 Contexto y Problema

Las plataformas tradicionales de edición automática de clips para videojuegos presentan dos fallas críticas:
1. **Modelos 100 % en la nube (SaaS)**: Exigen subir archivos VOD de 10 a 30 GB por sesión. Con conexiones domésticas estándar de internet, la subida tarda horas, saturando el ancho de banda del streamer y encareciendo enormemente el costo de almacenamiento en servidores externos.
2. **Modelos 100 % locales con IA pesada**: Intentar ejecutar modelos gigantescos de transcripción (Whisper Large en local), separación de pistas (Demucs) y visión en la misma computadora donde el creador juega provoca saturación de VRAM, sobrecalentamiento y caídas de FPS.

---

## ⚖️ Decisión adoptada

Adoptar una **[[Glosario#Arquitectura Híbrida|arquitectura híbrida estricta]]**:
- **A la nube solo viaja texto y audio comprimido**: Se extrae exclusivamente la pista del micrófono en formato Opus mono a $16\text{ kHz}$ ($24\text{ kbps}$, $\approx 7\text{ MB/h}$) y se envían líneas de tiempo textuales breves.
- **En local se queda el 100 % del video**: La decodificación, sincronización por Fourier (**[[Glosario#XCorr FFT|XCorr FFT]]**), tracking facial acotado con MediaPipe, composición en C++ y renderizado final con **[[Glosario#NVENC|NVENC]]** se ejecutan en la máquina del usuario.

---

## 🔬 Opciones consideradas y descartadas

1. **Subir videos completos a almacenamiento S3/Cloudflare R2**:
   *Descartada:* Inviable para streamers sin fibra óptica simétrica; costos mensuales de egreso y almacenamiento inasumibles.
2. **Ejecutar Whisper Large v3 y LLaMA 3 localmente en Ollama**:
   *Descartada:* Requiere mínimo 16 GB de VRAM dedicados exclusivamente a la IA, imposibilitando jugar y streamear en la misma máquina.

---

## ✅ Consecuencias

- **Positivas**:
  - Ingesta y subida casi instantánea ($\sim 7\text{ MB}$ por hora de VOD).
  - Costo por sesión menor a **\$0.15 USD**.
  - Total privacidad: las caras y el contenido de video nunca tocan servidores de terceros.
- **Negativas / Mitigaciones**:
  - Requiere que la computadora del usuario tenga instalada una versión reciente de FFmpeg (automatizado en los scripts de despliegue).

---

## 🔗 Relacionado
- [[Arquitectura general]]
- [[Resumen ejecutivo]]
- [[Alcance y objetivos]]