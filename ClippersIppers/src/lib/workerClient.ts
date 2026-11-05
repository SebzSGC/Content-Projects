// Browser-side helpers for the gaming clip worker (always via /api/worker).
import type {
  Candidate,
  CreateSessionRequest,
  LayoutPreset,
  NormRect,
  RenderedClip,
  RenderRequest,
  SessionSummary,
  SyncResult,
  WorkerJob,
} from "@/types/gaming";

const BASE = "/api/worker";

export class WorkerError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store", ...init });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const detail = Array.isArray(data?.detail)
      ? data.detail.map((d: { msg?: string }) => d.msg).join("; ")
      : data?.detail;
    throw new WorkerError(detail || `Error ${res.status} del worker`);
  }
  return res.json() as Promise<T>;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const worker = {
  health: () =>
    request<{
      ok: boolean;
      llm_provider: string;
      llm_model: string;
      llm_vision: boolean;
      face_model: boolean;
      ffmpeg: boolean;
    }>("/health"),
  listSessions: () => request<SessionSummary[]>("/sessions"),
  getSession: (id: string) => request<SessionSummary>(`/sessions/${id}`),
  createSession: (body: CreateSessionRequest) =>
    request<{ session: SessionSummary["session"]; job: WorkerJob }>("/sessions", json("POST", body)),
  updateSession: (
    id: string,
    body: {
      title?: string;
      layout?: LayoutPreset;
      game_subtitles_region?: NormRect;
      clear_game_subtitles_region?: boolean;
      voiceprint?: string;
    }
  ) => request<SessionSummary>(`/sessions/${id}`, json("PATCH", body)),
  setSync: (id: string, shift_sec: number, scale = 1) =>
    request<SyncResult>(`/sessions/${id}/sync`, json("PUT", { shift_sec, scale })),
  ingest: (id: string) => request<WorkerJob>(`/sessions/${id}/ingest`, { method: "POST" }),
  analyze: (id: string, force = false) => request<WorkerJob>(`/sessions/${id}/analyze`, json("POST", { force })),
  candidates: (id: string) => request<Candidate[]>(`/sessions/${id}/candidates`),
  clips: (id: string) => request<RenderedClip[]>(`/sessions/${id}/clips`),
  render: (id: string, body: RenderRequest) => request<WorkerJob>(`/sessions/${id}/clips`, json("POST", body)),
  job: (jobId: string) => request<WorkerJob>(`/jobs/${jobId}`),
  voiceprints: () => request<string[]>("/voiceprints"),
  frameUrl: (id: string, source: "gameplay" | "camera", t: number) =>
    `${BASE}/sessions/${id}/frame?source=${source}&t=${t.toFixed(1)}`,
  clipUrl: (sessionId: string, clipId: string, download = false) =>
    `${BASE}/sessions/${sessionId}/clips/${clipId}/file${download ? "?download=true" : ""}`,
};

/** Streams a file to the worker's disk; resolves with the path to use in a session. */
export function uploadFile(file: File, onProgress?: (fraction: number) => void): Promise<string> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE}/uploads?filename=${encodeURIComponent(file.name)}`);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
    xhr.onload = () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) resolve(data.path);
        else reject(new WorkerError(data.detail || `Error ${xhr.status} al subir`));
      } catch {
        reject(new WorkerError(`Error ${xhr.status} al subir`));
      }
    };
    xhr.onerror = () => reject(new WorkerError("No se pudo subir el archivo"));
    xhr.send(file);
  });
}

/** Polls a job until it finishes. Resolves with the final job (done or error). */
export async function waitForJob(
  jobId: string,
  onUpdate: (job: WorkerJob) => void,
  intervalMs = 1500
): Promise<WorkerJob> {
  for (;;) {
    const job = await worker.job(jobId);
    onUpdate(job);
    if (job.status === "done" || job.status === "error") return job;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

export function formatClock(sec: number): string {
  const s = Math.max(0, sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = Math.floor(s % 60);
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}` : `${m}:${String(r).padStart(2, "0")}`;
}

export const STAGE_LABELS: Record<string, string> = {
  ingest: "Ingesta",
  media: "Preparando medios",
  separation: "Separando voces",
  face: "Siguiendo la cara",
  sync: "Sincronizando",
  transcription: "Transcribiendo",
  ocr: "Leyendo diálogos del juego",
  motion: "Movimiento del juego",
  audio_events: "Risas, gritos y eventos",
  speakers: "Quién habla",
  signals: "Combinando señales",
  selection: "La IA elige historias",
  verification: "La IA revisa los clips",
  render: "Renderizando",
  done: "Listo",
};
