// Shapes returned by the Python worker (worker/src/gameclips). Times are
// seconds on the master (gameplay) timeline; rects are normalized 0..1.

export type SourceMode = "split" | "composite";
export type SpeakerLabel = "STREAMER" | "GAME" | "UNKNOWN";
export type CaptionMode = "streamer" | "all" | "none";

export interface NormRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface LayoutPreset {
  camera: NormRect;
  gameplay: NormRect;
}

export interface SessionSpec {
  id: string;
  mode: SourceMode;
  title: string;
  gameplay_path: string | null;
  camera_path: string | null;
  kick_url: string | null;
  layout: LayoutPreset | null;
  game_subtitles_region: NormRect | null;
  language: string | null;
  voiceprint: string | null;
  created_at: number;
}

export interface StreamInfo {
  path: string;
  duration: number;
  width: number;
  height: number;
  fps: number;
  has_audio: boolean;
}

export interface MediaManifest {
  mode: SourceMode;
  gameplay: StreamInfo;
  camera: StreamInfo;
  camera_wav: string | null;
  proxy_fps: number;
  kick_url: string | null;
}

export interface SyncResult {
  shift_sec: number;
  scale: number;
  method: "none" | "audio_xcorr" | "lipsync" | "manual" | "composite";
  confidence: number;
}

export interface WorkerJob {
  id: string;
  kind: "ingest" | "analyze" | "render";
  session_id: string;
  status: "queued" | "running" | "done" | "error";
  stage: string;
  progress: number;
  message: string;
  error: string | null;
  result: Record<string, unknown> | null;
  created_at: number;
  updated_at: number;
}

export interface SessionSummary {
  session: SessionSpec;
  manifest: MediaManifest | null;
  sync: SyncResult | null;
  source: Partial<Record<"gameplay" | "camera", StreamInfo>>;
  has_candidates: boolean;
  candidates: number;
  clips: number;
  jobs: WorkerJob[];
}

export interface Candidate {
  id: string;
  start: number;
  end: number;
  overlay_title: string;
  post_title: string;
  hashtags: string[];
  reason: string;
  llm_score: number;
  signal_score: number;
  verify_score: number | null;
  final_score: number;
  reaction_peak: number | null;
  verified: boolean;
  verification_notes: string;
}

export interface RenderedClip {
  id: string;
  candidate_id: string;
  start: number;
  end: number;
  overlay_title: string;
  path: string;
  created_at: number;
}

export interface RenderRequest {
  candidate_id: string;
  start?: number;
  end?: number;
  overlay_title?: string;
  captions: CaptionMode;
  title_duration_sec: number;
  camera_ratio: number;
  gameplay_focus_x: number;
  punch_in: boolean;
  voice_boost: boolean;
}

export interface CreateSessionRequest {
  mode: SourceMode;
  title: string;
  gameplay_path?: string;
  camera_path?: string;
  kick_url?: string;
  language?: string;
  voiceprint?: string;
}
