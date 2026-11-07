// Session states from the orchestrator mapped onto the 7 user-facing steps.
import type { PipelineStep, StepStatus } from "@/components/StepProgress";
import type { SessionSummary } from "@/lib/api/client";

export const PIPELINE_STEPS: PipelineStep[] = [
  { key: "import", label: "Importar", hint: "Ingesta de gameplay.mp4 y camara.mp4 (local o Google Drive)" },
  { key: "prepare", label: "Preparar audio", hint: "Audio Opus mono 16 kHz y sincronización cámara ↔ juego por FFT" },
  { key: "transcribe", label: "Transcribir", hint: "STT de la voz y señales de emoción en Parquet" },
  { key: "curate", label: "Elegir momentos", hint: "La IA elige los mejores tramos por IDs de frase" },
  { key: "frame", label: "Encuadrar", hint: "Tracking facial MediaPipe por clip y EditPlan v2" },
  { key: "render", label: "Renderizar", hint: "Render 1080×1920 con NVENC / libx264" },
  { key: "deliver", label: "Entregado", hint: "Clips publicados en Salidas/" },
];

/** Step that is running while the session sits in each state (a state means the previous step just finished). */
const ACTIVE_STEP: Record<string, number> = {
  NEW: 0,
  DOWNLOADED: 1,
  PREPARED: 2,
  TRANSCRIBED: 3,
  CURATED: 4,
  PLANNING: 4,
  RENDERING: 5,
};

export interface StepState {
  statuses: StepStatus[];
  fill: number;
  current: number;
  running: boolean;
}

export function sessionSteps(s: SessionSummary): StepState {
  const last = PIPELINE_STEPS.length - 1;
  if (s.state === "DELIVERED") {
    return { statuses: PIPELINE_STEPS.map(() => "done"), fill: 1, current: last, running: false };
  }
  if (s.state === "FAILED" || s.state === "CANCELLED") {
    // The state no longer says where it stopped; infer it from what was produced.
    const at = s.rendered_count > 0 ? 5 : s.clips_count > 0 ? 4 : s.prepared ? 2 : s.sync ? 1 : 0;
    const statuses = PIPELINE_STEPS.map((_, i): StepStatus => (i < at ? "done" : i === at ? "error" : "pending"));
    return { statuses, fill: at / last, current: at, running: false };
  }
  const at = ACTIVE_STEP[s.state] ?? 0;
  const statuses = PIPELINE_STEPS.map((_, i): StepStatus => (i < at ? "done" : i === at ? "active" : "pending"));
  return { statuses, fill: at / last, current: at, running: true };
}

const FRIENDLY_STATE: Record<string, string> = {
  NEW: "Importando",
  DOWNLOADED: "Preparando audio",
  PREPARED: "Transcribiendo",
  TRANSCRIBED: "Eligiendo momentos",
  CURATED: "Encuadrando",
  PLANNING: "Encuadrando",
  RENDERING: "Renderizando",
  DELIVERED: "Entregado",
  FAILED: "Con error",
  CANCELLED: "Cancelada",
};

export function friendlyState(state: string): string {
  return FRIENDLY_STATE[state] ?? state;
}
