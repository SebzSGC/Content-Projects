// The worker's ~13 internal stages, grouped into 7 user-facing steps.
import type { SessionSummary, WorkerJob } from "@/types/gaming";

export type StepStatus = "done" | "active" | "pending" | "error";

export const STEPS: Array<{ key: string; label: string; hint: string; stages: string[] }> = [
  { key: "import", label: "Importar", hint: "Leer o descargar la fuente y preparar copias ligeras", stages: ["ingest", "media"] },
  { key: "voices", label: "Voces", hint: "Separar las voces de la música y los efectos", stages: ["separation"] },
  { key: "camera", label: "Cámara", hint: "Seguir tu cara y sincronizar cámara y juego", stages: ["face", "sync"] },
  { key: "transcribe", label: "Transcribir", hint: "Pasar a texto lo que se dice, palabra por palabra", stages: ["transcription", "ocr"] },
  { key: "reactions", label: "Reacciones", hint: "Encontrar risas, gritos y momentos intensos", stages: ["motion", "audio_events", "speakers", "signals"] },
  { key: "stories", label: "Historias", hint: "La IA elige y revisa los mejores momentos", stages: ["selection", "verification", "done"] },
  { key: "render", label: "Renderizar", hint: "Crear los Shorts verticales", stages: ["render"] },
];

const isActive = (j: WorkerJob) => j.status === "running" || j.status === "queued";

export function stepIndexForStage(stage: string): number {
  const i = STEPS.findIndex((s) => s.stages.includes(stage));
  return i < 0 ? 0 : i;
}

export interface StepState {
  statuses: StepStatus[];
  /** 0..1 position of the filled track (0 = first dot, 1 = last dot). */
  fill: number;
  current: number;
}

export function computeSteps(summary: SessionSummary, renderJobs: WorkerJob[] = []): StepState {
  const last = STEPS.length - 1;
  const pipelineJob = summary.jobs.find((j) => (j.kind === "analyze" || j.kind === "ingest") && isActive(j));
  const latest = summary.jobs.find((j) => j.kind === "analyze" || j.kind === "ingest");
  const statuses: StepStatus[] = STEPS.map(() => "pending");

  if (pipelineJob) {
    const idx = pipelineJob.kind === "ingest" ? 0 : stepIndexForStage(pipelineJob.stage);
    statuses.forEach((_, i) => (statuses[i] = i < idx ? "done" : i === idx ? "active" : "pending"));
    // Analysis covers steps 1–6; its overall progress maps onto that stretch of the track.
    const fill = pipelineJob.kind === "ingest" ? 0 : (pipelineJob.progress * (last - 1)) / last;
    return { statuses, fill: Math.max(fill, idx / last), current: idx };
  }

  if (latest?.status === "error" && !summary.has_candidates) {
    const idx = latest.kind === "ingest" ? 0 : stepIndexForStage(latest.stage);
    statuses.forEach((_, i) => (statuses[i] = i < idx ? "done" : i === idx ? "error" : "pending"));
    return { statuses, fill: idx / last, current: idx };
  }

  if (summary.has_candidates) {
    for (let i = 0; i < last; i++) statuses[i] = "done";
    const rendering = renderJobs.some(isActive) || summary.jobs.some((j) => j.kind === "render" && isActive(j));
    statuses[last] = rendering ? "active" : summary.clips > 0 ? "done" : "pending";
    return { statuses, fill: statuses[last] === "done" ? 1 : (last - 1) / last, current: last };
  }

  const sourceReady = Boolean(summary.source.gameplay);
  statuses[0] = sourceReady ? "done" : "pending";
  return { statuses, fill: 0, current: sourceReady ? 1 : 0 };
}
