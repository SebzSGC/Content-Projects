// Session states from the orchestrator mapped onto the 7 user-facing steps.
import type { PipelineStep, StepStatus } from "@/components/StepProgress";
import type { SessionSummary } from "@/lib/api/client";

export const PIPELINE_STEPS: PipelineStep[] = [
  { key: "import", label: "Importar", hint: "Recibe el video del juego y el de tu cámara para trabajarlos juntos" },
  { key: "prepare", label: "Sincronizar", hint: "Alinea tu voz con la partida para que cada reacción coincida a tiempo" },
  { key: "transcribe", label: "Escuchar", hint: "Convierte lo que dices en texto y detecta dónde sube la emoción" },
  { key: "curate", label: "Elegir momentos", hint: "Selecciona las jugadas más entretenidas y con mejor historia" },
  { key: "frame", label: "Encuadrar", hint: "Centra tu cámara en formato vertical y recorta las pausas largas" },
  { key: "render", label: "Crear video", hint: "Genera el Short vertical 9:16 con subtítulos animados y audio mezclado" },
  { key: "deliver", label: "Listo", hint: "Tus clips están terminados y listos para revisar o publicar" },
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
  NEW: "Importando videos",
  DOWNLOADED: "Sincronizando audio",
  PREPARED: "Escuchando partida",
  TRANSCRIBED: "Eligiendo mejores momentos",
  CURATED: "Armando encuadre vertical",
  PLANNING: "Armando encuadre vertical",
  RENDERING: "Creando videos finales",
  DELIVERED: "Listo para publicar",
  FAILED: "Se detuvo",
  CANCELLED: "Cancelada",
};

export function friendlyState(state: string): string {
  return FRIENDLY_STATE[state] ?? state;
}
