"use client";

import { useEffect, useRef } from "react";
import type { EditPlan } from "./editplan";

export const API_PREFIX = "/api/server";

export interface BudgetBreakdownItem {
  provider: string;
  model: string;
  kind: string;
  calls: number;
  units: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export interface BudgetSummary {
  spent_usd: number;
  max_budget_usd: number;
  remaining_usd: number;
  calls_count: number;
  breakdown: BudgetBreakdownItem[];
}

export interface ServerHealth {
  ok: boolean;
  ffmpeg: boolean;
  mediapipe_face_detector: boolean;
  stt_primary: string;
  stt_backup: string;
  llm_primary: string;
  llm_model: string;
  llm_backup: string;
  style_preset: string;
  drive_mode: string;
  drive_local_dir: string;
  cpu_workers: number;
  render_slots: number;
  use_nvenc: boolean;
  budget: BudgetSummary;
}

export interface DriveStatus {
  mode: "local" | "oauth" | "service_account" | "disabled" | string;
  connected?: boolean;
  oauth_connected?: boolean;
  client_configured?: boolean;
  client_id?: string;
  has_client_secret?: boolean;
  user_email?: string | null;
  user_name?: string | null;
  root_folder_id?: string | null;
  local_dir: string;
  poll_sec: number;
  entradas: string[];
  salidas: string[];
}

export interface DriveBreadcrumb {
  id: string;
  name: string;
}

export interface DriveFolderItem {
  id: string;
  name: string;
  modified_ts?: number;
}

export interface DriveVideoItem {
  id: string;
  name: string;
  size: number;
  mime_type?: string;
  modified_ts?: number;
  role_hint?: "gameplay" | "camera" | null;
}

export interface DriveDetectedPair {
  recording_name: string;
  gameplay: DriveVideoItem;
  camera: DriveVideoItem;
}

export interface DriveBrowseResponse {
  mode: string;
  folder_id: string;
  folder_name: string;
  parent_id: string | null;
  breadcrumbs: DriveBreadcrumb[];
  folders: DriveFolderItem[];
  files: DriveVideoItem[];
  detected_pair: DriveDetectedPair | null;
}

export interface DriveAuthUrlResponse {
  auth_url: string;
  url?: string;
  redirect_uri: string;
  state?: string | null;
}

export interface SyncInfo {
  shift_sec: number;
  scale: number;
  method: "audio_xcorr" | "manual" | "zero";
  confidence: number;
  samples?: { t: number; camera_t: number; confidence: number }[];
}

export interface SessionSummary {
  id: string;
  title: string;
  recording_name: string;
  state: string;
  gameplay_path: string | null;
  camera_path: string | null;
  drive_folder_id: string | null;
  language: string;
  style_preset: string;
  detected_game?: string | null;
  keyterms_count?: number;
  sync: SyncInfo | null;
  prepared: {
    gameplay: { width: number; height: number; fps: number; duration: number };
    camera: { width: number; height: number; fps: number; duration: number };
    chunks: { index: number; start_cam_sec: number; end_cam_sec: number; size_bytes: number }[];
    gameplay_clean_audio_stream: number | null;
  } | null;
  error: string | null;
  clips_count: number;
  rendered_count: number;
  created_at: number;
  updated_at: number;
  tasks?: {
    id: string;
    kind: string;
    clip_id: string | null;
    state: string;
    error: string | null;
    updated_at: number;
  }[];
}

export interface SignalPeak {
  t: number;
  score: number;
  mic: number;
  game: number;
  motion: number;
  hud?: number;
}

export interface SignalSeries {
  duration: number;
  mic_loudness: number[];
  mic_burst: number[];
  game_loudness: number[];
  motion: number[];
  motion_cx: number[];
  hud_activity?: number[];
  reaction: number[];
  excitement: number[];
  peaks: SignalPeak[];
}

export interface ClipItem {
  id: string;
  session_id: string;
  rank_order: number;
  start: number;
  end: number;
  overlay_title: string;
  post_title: string;
  hashtags: string[];
  reason: string;
  llm_score: number;
  signal_score: number;
  final_score: number;
  curated: {
    start_id: string;
    end_id: string;
    hook: string;
    emphasis_words: string[];
    emojis: { word: string; emoji: string }[];
    reaction_peaks: number[];
  } | null;
  editplan: EditPlan | null;
  has_draft: boolean;
  has_final: boolean;
  drive_salidas: Record<string, string> | null;
  state: string;
  created_at: number;
  updated_at: number;
}

export interface StylePreset {
  id: string;
  format: { width: number; height: number; max_fps: number; target_lufs: number };
  layout: { camera_ratio: number; gameplay_ratio: number; camera_full_sec: number };
  title: { duration_sec: number; font_family: string; text_color: string; bg_color: string };
  captions: {
    font_family: string;
    uppercase: boolean;
    gameplay_top_third_ratio: number;
    active_word: { color_hex: string; pop_scale_pct: number; pop_duration_ms: number };
    emphasis_word: { color_hex: string; scale_pct: number };
  };
  emojis: { size_px: number };
}

export interface ClipDetailPayload {
  clip: ClipItem;
  session: SessionSummary;
  preset: StylePreset;
}

export interface ServerSseEvent {
  type: string;
  ts?: number;
  session_id?: string;
  clip_id?: string;
  state?: string;
  stage?: string;
  quality?: "draft" | "final";
  progress?: number;
  message?: string;
  error?: string;
  spent_usd?: number;
  max_budget_usd?: number;
  remaining_usd?: number;
  calls_count?: number;
  stt_primary?: string;
  llm_primary?: string;
  llm_model?: string;
  connected_to_resolve?: boolean;
  timeline_name?: string;
  project_name?: string;
}

export interface ApiKeyStatus {
  masked: string;
  has_key: boolean;
}

export interface AppSettings {
  env_path: string;
  stt_primary: "deepgram" | "groq" | "fixture";
  stt_backup: "groq" | "deepgram" | "fixture" | "none";
  deepgram_model: string;
  groq_stt_model: string;
  llm_primary: "gemini" | "openai_compat" | "fixture";
  llm_model: string;
  llm_backup: "openai_compat" | "gemini" | "fixture" | "none";
  llm_backup_model: string;
  llm_backup_base_url: string;
  max_budget_usd: number;
  webhook_url: string;
  temp_ttl_days: number;
  auto_render_top_k: number;
  auto_render_min_score: number;
  default_keyterms: string[];
  editor_backend?: "local" | "resolve_mcp" | "both";
  resolve_mcp_mode?: "auto" | "mcp_stdio" | "mcp_http" | "direct_script" | "bundle_only";
  resolve_mcp_command?: string;
  resolve_mcp_url?: string;
  resolve_project_prefix?: string;
  resolve_auto_export?: boolean;
  drive_mode?: "local" | "oauth" | "service_account" | "disabled";
  drive_local_dir?: string;
  drive_root_folder_id?: string;
  drive_poll_sec?: number;
  drive_client_id?: string;
  drive_client_secret?: string;
  has_drive_client_secret?: boolean;
  drive_oauth_connected?: boolean;
  deepgram_api_key: string;
  groq_api_key: string;
  gemini_api_key: string;
  openai_api_key: string;
  has_deepgram_key: boolean;
  has_groq_key: boolean;
  has_gemini_key: boolean;
  has_openai_key: boolean;
  api_keys: {
    deepgram: ApiKeyStatus;
    groq: ApiKeyStatus;
    gemini: ApiKeyStatus;
    openai: ApiKeyStatus;
  };
}

export interface UpdateSettingsPayload {
  stt_primary?: "deepgram" | "groq" | "fixture";
  stt_backup?: "groq" | "deepgram" | "fixture" | "none";
  deepgram_model?: string;
  groq_stt_model?: string;
  llm_primary?: "gemini" | "openai_compat" | "fixture";
  llm_model?: string;
  llm_backup?: "openai_compat" | "gemini" | "fixture" | "none";
  llm_backup_model?: string;
  llm_backup_base_url?: string;
  max_budget_usd?: number;
  deepgram_api_key?: string;
  groq_api_key?: string;
  gemini_api_key?: string;
  openai_api_key?: string;
  webhook_url?: string;
  temp_ttl_days?: number;
  editor_backend?: "local" | "resolve_mcp" | "both";
  resolve_mcp_mode?: "auto" | "mcp_stdio" | "mcp_http" | "direct_script" | "bundle_only";
  resolve_mcp_command?: string;
  resolve_mcp_url?: string;
  resolve_project_prefix?: string;
  resolve_auto_export?: boolean;
  drive_mode?: "local" | "oauth" | "service_account" | "disabled";
  drive_client_id?: string;
  drive_client_secret?: string;
  drive_root_folder_id?: string;
  drive_local_dir?: string;
  drive_poll_sec?: number;
}

export interface ResolveStatusResponse {
  installed: boolean;
  resolve_binary_path: string | null;
  scripting_modules_dir: string | null;
  fusionscript_lib_path: string | null;
  process_running: boolean;
  scripting_connected: boolean;
  product_info: string;
  editor_backend: "local" | "resolve_mcp" | "both" | string;
  mcp_mode: "auto" | "mcp_stdio" | "mcp_http" | "direct_script" | "bundle_only" | string;
  mcp_command: string;
  mcp_url: string;
  mcp_server_ready: boolean;
  available_tools: string[];
  instructions: string[];
}

export interface ResolveClipExportResponse {
  ok: boolean;
  status?: string;
  clip_id: string;
  session_id?: string;
  project_name: string;
  timeline_name: string;
  bundle_dir?: string;
  fcpxml_path?: string;
  srt_path?: string;
  ass_path?: string;
  script_path?: string;
  mcp_plan_path?: string;
  mode_used?: string;
  connected_to_resolve: boolean;
  message: string;
  segments_count?: number;
  captions_count?: number;
  sfx_count?: number;
  markers_count?: number;
  tool_calls?: { tool: string; arguments: Record<string, unknown> }[];
}

export interface ResolveSessionExportResponse {
  ok: boolean;
  status?: string;
  session_id: string;
  project_name: string;
  exported_count?: number;
  clips?: ResolveClipExportResponse[];
  message?: string;
}

export interface TestConnectionResult {
  ok: boolean;
  provider: string;
  latency_ms: number;
  status_code?: number;
  detail: string;
}

export type AnalyticsAlertStatus = "NORMAL" | "WARNING" | "CRITICAL" | "BLOCKED";

export interface AnalyticsProjections {
  avg_cost_per_stream_hour_usd: number;
  stt_cost_per_stream_hour_usd: number;
  llm_cost_per_stream_hour_usd: number;
  avg_cost_per_clip_usd: number;
  avg_clips_per_stream_hour: number;
  avg_tokens_per_stream_hour: number;
  estimated_remaining_stream_hours: number;
  estimated_remaining_clips: number;
}

export interface AnalyticsFreeTierPoint {
  hour_epoch: number;
  label: string;
  peak_rpm: number;
  peak_tpm: number;
  requests: number;
  cumulative_rpd: number;
}

export interface AnalyticsFreeTierModel {
  id: string;
  provider: string;
  model: string;
  display_name: string;
  category: string;
  tier_name: string;
  within_free_tier: boolean;
  zero_cost_in_free_tier: boolean;
  rpm: {
    peak: number;
    limit: number;
    pct: number;
  };
  tpm: {
    peak: number;
    limit: number;
    pct: number;
    label: string;
    unit: string;
  };
  rpd: {
    used: number;
    limit: number;
    pct: number;
  };
  credit: {
    limit_usd: number;
    used_usd: number;
    remaining_usd: number;
    pct: number;
    estimated_used_usd?: number;
    source?: "estimated" | "manual" | "live" | string;
    calibrated_at?: number | null;
    used_since_calibration_usd?: number;
  };
  timeline_24h: AnalyticsFreeTierPoint[];
}

export interface AnalyticsFreeTierComparison {
  window_hours: number;
  models: AnalyticsFreeTierModel[];
}

export interface AnalyticsSummary {
  spent_usd: number;
  stt_cost_usd: number;
  llm_cost_usd: number;
  max_budget_usd: number;
  remaining_usd: number;
  usage_pct: number;
  alert_status: AnalyticsAlertStatus;
  total_calls: number;
  stt_calls: number;
  llm_calls: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  audio_seconds_billed: number;
  audio_minutes_billed: number;
  audio_hours_billed: number;
  avg_latency_ms: number;
  sessions_with_calls: number;
  total_clips_curated: number;
  total_clips_rendered: number;
  projections: AnalyticsProjections;
  free_tier?: AnalyticsFreeTierComparison;
}

export interface AnalyticsProviderItem {
  provider: string;
  kind: "stt" | "llm" | string;
  calls: number;
  audio_seconds: number;
  audio_minutes: number;
  audio_hours: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  share_pct: number;
  avg_latency_ms: number;
}

export interface AnalyticsModelItem {
  provider: string;
  model: string;
  kind: "stt" | "llm" | string;
  calls: number;
  units_billed: number;
  audio_seconds: number;
  audio_minutes: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  share_pct: number;
  avg_latency_ms: number;
}

export interface AnalyticsDayItem {
  date: string;
  calls: number;
  stt_calls: number;
  llm_calls: number;
  cost_usd: number;
  stt_cost_usd: number;
  llm_cost_usd: number;
  audio_minutes: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export interface AnalyticsSessionItem {
  session_id: string;
  session_title: string;
  state: string;
  calls: number;
  stt_calls: number;
  llm_calls: number;
  cost_usd: number;
  stt_cost_usd: number;
  llm_cost_usd: number;
  audio_seconds: number;
  audio_minutes: number;
  audio_hours: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  clips_count: number;
  cost_per_clip_usd: number;
  first_call_at: number;
  last_call_at: number;
}

export interface AnalyticsBreakdown {
  spent_usd: number;
  by_provider: AnalyticsProviderItem[];
  by_model: AnalyticsModelItem[];
  by_day: AnalyticsDayItem[];
  by_session: AnalyticsSessionItem[];
}

export interface AnalyticsLogItem {
  id: string;
  session_id: string | null;
  session_title: string;
  task_hash: string;
  provider: string;
  model: string;
  kind: "stt" | "llm" | string;
  units_billed: number;
  audio_seconds: number;
  audio_minutes: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  latency_ms: number;
  created_at: number;
  created_iso: string;
}

export interface AnalyticsLogsResponse {
  total: number;
  limit: number;
  offset: number;
  filtered_cost_usd: number;
  items: AnalyticsLogItem[];
}

export interface AnalyticsLogsQuery {
  provider?: string;
  kind?: string;
  session_id?: string;
  date_from?: string;
  date_to?: string;
  search?: string;
  limit?: number;
  offset?: number;
}

async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    headers: {
      ...(init?.body && !(init.body instanceof ReadableStream) ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Error HTTP ${res.status}`;
    try {
      const errJson = await res.json();
      detail = errJson.detail || JSON.stringify(errJson);
    } catch {
      detail = (await res.text()) || detail;
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export interface EmojiCatalogItem {
  id: string;
  char: string;
  name: string;
  category: string;
  url: string;
}

export interface GameKeytermProfile {
  id: string;
  name: string;
  triggers: string[];
  keyterms_count: number;
  sample_keyterms: string[];
}

export interface KeytermsPreviewPayload {
  profiles: GameKeytermProfile[];
  detected_game: string | null;
  resolved_keyterms: string[];
}

export interface MaintenanceStats {
  temp_ttl_days: number;
  temp_media_bytes: number;
  renders_bytes: number;
  preserved_cache_bytes: number;
  eligible_cleanup_bytes: number;
  eligible_sessions_count: number;
  webhook_configured: boolean;
}

export interface CleanupResult {
  ttl_days: number;
  purged_files: number;
  freed_bytes: number;
  cleaned_sessions: string[];
}

export const fetchHealth = () => apiJson<ServerHealth>("/health");
export const fetchBudget = () => apiJson<BudgetSummary>("/budget");
export const fetchAnalyticsSummary = () => apiJson<AnalyticsSummary>("/analytics/summary");
export const fetchAnalyticsBreakdown = () => apiJson<AnalyticsBreakdown>("/analytics/breakdown");
export const calibrateFreeTierBalance = (balance_usd?: number, credit_usd = 200, provider: "deepgram" = "deepgram") =>
  apiJson<{ ok: boolean; summary: AnalyticsSummary }>("/analytics/free-tier/calibrate", {
    method: "POST",
    body: JSON.stringify({ provider, balance_usd, credit_usd }),
  });
export const resetFreeTierCalibration = (provider = "deepgram") =>
  apiJson<{ ok: boolean; summary: AnalyticsSummary }>(`/analytics/free-tier/calibrate/${encodeURIComponent(provider)}`, {
    method: "DELETE",
  });
export const fetchAnalyticsLogs = (query?: AnalyticsLogsQuery) => {
  const params = new URLSearchParams();
  if (query?.provider && query.provider !== "all") params.set("provider", query.provider);
  if (query?.kind && query.kind !== "all") params.set("kind", query.kind);
  if (query?.session_id && query.session_id !== "all") params.set("session_id", query.session_id);
  if (query?.date_from) params.set("date_from", query.date_from);
  if (query?.date_to) params.set("date_to", query.date_to);
  if (query?.search) params.set("search", query.search);
  if (typeof query?.limit === "number") params.set("limit", String(query.limit));
  if (typeof query?.offset === "number") params.set("offset", String(query.offset));
  const qs = params.toString();
  return apiJson<AnalyticsLogsResponse>(`/analytics/logs${qs ? `?${qs}` : ""}`);
};
export const getSettings = () => apiJson<AppSettings>("/settings");
export const saveSettings = (data: UpdateSettingsPayload) =>
  apiJson<AppSettings>("/settings", {
    method: "POST",
    body: JSON.stringify(data),
  });
export const testSettingsConnection = (
  provider: "deepgram" | "groq" | "gemini" | "openai_compat" | "openai" | "fixture",
  api_key?: string,
  options?: { model?: string; base_url?: string }
) =>
  apiJson<TestConnectionResult>("/settings/test-connection", {
    method: "POST",
    body: JSON.stringify({
      provider,
      api_key,
      model: options?.model,
      base_url: options?.base_url,
    }),
  });
export const fetchDriveStatus = () => apiJson<DriveStatus>("/drive/status");
export const triggerDrivePoll = () => apiJson<{ launched_sessions: string[] }>("/drive/poll", { method: "POST" });
export const fetchDriveAuthUrl = (redirectUri?: string, state?: string) => {
  const params = new URLSearchParams();
  if (redirectUri) params.set("redirect_uri", redirectUri);
  if (state) params.set("state", state);
  const qs = params.toString();
  return apiJson<DriveAuthUrlResponse>(`/drive/auth/url${qs ? `?${qs}` : ""}`);
};
export const completeDriveAuthCallback = (code: string, redirectUri?: string, state?: string) => {
  const params = new URLSearchParams({ code, format: "json" });
  if (redirectUri) params.set("redirect_uri", redirectUri);
  if (state) params.set("state", state);
  return apiJson<{
    ok: boolean;
    mode: string;
    connected: boolean;
    oauth_connected: boolean;
    user_email?: string | null;
    user_name?: string | null;
  }>(`/drive/auth/callback?${params.toString()}`);
};
export const disconnectDriveAuth = () =>
  apiJson<{ ok: boolean; mode: string; connected: boolean; oauth_connected: boolean }>("/drive/auth/disconnect", {
    method: "POST",
  });
export const fetchDriveFiles = (folderId?: string, query?: string) => {
  const params = new URLSearchParams();
  if (folderId) params.set("folder_id", folderId);
  if (query && query.trim()) params.set("query", query.trim());
  const qs = params.toString();
  return apiJson<DriveBrowseResponse>(`/drive/files${qs ? `?${qs}` : ""}`);
};
export const createDriveSession = (body: {
  title?: string;
  folder_id?: string;
  gameplay_file_id?: string;
  camera_file_id?: string;
  recording_name?: string;
  language?: string;
  style_preset?: string;
  auto_start?: boolean;
}) => apiJson<SessionSummary>("/drive/sessions", { method: "POST", body: JSON.stringify(body) });
export const fetchEmojiCatalog = () => apiJson<EmojiCatalogItem[]>("/emojis");
export const fetchKeytermsPreview = (title = "", recordingName = "") =>
  apiJson<KeytermsPreviewPayload>(
    `/keyterms?title=${encodeURIComponent(title)}&recording_name=${encodeURIComponent(recordingName)}`
  );
export const fetchMaintenanceStats = () => apiJson<MaintenanceStats>("/maintenance/stats");
export const triggerMaintenanceCleanup = (ttl_days?: number, include_inputs = false) =>
  apiJson<CleanupResult>("/maintenance/cleanup", {
    method: "POST",
    body: JSON.stringify({ ttl_days, include_inputs }),
  });
export const triggerTestWebhook = (webhook_url?: string, session_id?: string) =>
  apiJson<{ ok: boolean; status_code?: number; format?: string; detail?: string }>("/webhooks/test", {
    method: "POST",
    body: JSON.stringify({ webhook_url, session_id }),
  });

export const fetchSessions = () => apiJson<SessionSummary[]>("/sessions");
export const fetchSessionDetail = (id: string) => apiJson<SessionSummary>(`/sessions/${encodeURIComponent(id)}`);
export const fetchSessionSignals = (id: string) => apiJson<SignalSeries | null>(`/sessions/${encodeURIComponent(id)}/signals`);
export const fetchSessionClips = (id: string) => apiJson<ClipItem[]>(`/sessions/${encodeURIComponent(id)}/clips`);

export const createSession = (body: {
  title: string;
  gameplay_path: string;
  camera_path: string;
  recording_name?: string;
  language?: string;
  style_preset?: string;
  auto_start?: boolean;
}) => apiJson<SessionSummary>("/sessions", { method: "POST", body: JSON.stringify(body) });

export const rerunSession = (id: string) =>
  apiJson<SessionSummary>(`/sessions/${encodeURIComponent(id)}/run`, { method: "POST" });

export const cancelSession = (id: string) =>
  apiJson<SessionSummary>(`/sessions/${encodeURIComponent(id)}/cancel`, { method: "POST" });

export const updateManualSync = (id: string, shift_sec: number, scale = 1.0) =>
  apiJson<SyncInfo>(`/sessions/${encodeURIComponent(id)}/sync`, {
    method: "PUT",
    body: JSON.stringify({ shift_sec, scale }),
  });

export async function uploadVideoFile(file: File): Promise<{ path: string; size: number }> {
  const res = await fetch(`${API_PREFIX}/uploads?filename=${encodeURIComponent(file.name)}`, {
    method: "POST",
    headers: { "Content-Type": file.type || "application/octet-stream" },
    body: file,
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || `Error subiendo ${file.name}`);
  }
  return res.json();
}

export const fetchClipDetail = (clipId: string) =>
  apiJson<ClipDetailPayload>(`/clips/${encodeURIComponent(clipId)}`);

export const saveClipEditPlan = (clipId: string, plan: EditPlan) =>
  apiJson<{ clip: ClipItem; editplan: EditPlan }>(`/clips/${encodeURIComponent(clipId)}/editplan`, {
    method: "PUT",
    body: JSON.stringify(plan),
  });

export const renderClip = (clipId: string, quality: "draft" | "final", upload_to_drive = true) =>
  apiJson<{ clip: ClipItem; mp4_path: string }>(`/clips/${encodeURIComponent(clipId)}/render`, {
    method: "POST",
    body: JSON.stringify({ quality, upload_to_drive }),
  });

export const fetchResolveStatus = () => apiJson<ResolveStatusResponse>("/resolve/status");

export const exportClipToResolve = (
  clipId: string,
  options?: { open_in_resolve?: boolean; trigger_render?: boolean; project_name?: string; async_mode?: boolean }
) =>
  apiJson<ResolveClipExportResponse>(`/clips/${encodeURIComponent(clipId)}/resolve`, {
    method: "POST",
    body: JSON.stringify({
      open_in_resolve: options?.open_in_resolve ?? true,
      trigger_render: options?.trigger_render ?? false,
      project_name: options?.project_name,
      async_mode: options?.async_mode ?? true,
    }),
  });

export const exportSessionToResolve = (
  sessionId: string,
  options?: { top_k?: number; open_in_resolve?: boolean; trigger_render?: boolean; project_name?: string; async_mode?: boolean }
) =>
  apiJson<ResolveSessionExportResponse>(`/sessions/${encodeURIComponent(sessionId)}/resolve`, {
    method: "POST",
    body: JSON.stringify({
      top_k: options?.top_k,
      open_in_resolve: options?.open_in_resolve ?? true,
      trigger_render: options?.trigger_render ?? false,
      project_name: options?.project_name,
      async_mode: options?.async_mode ?? true,
    }),
  });

export const resolveArtifactUrl = (
  clipId: string,
  artifact: "fcpxml" | "srt" | "ass" | "script" | "mcp_plan"
) => `${API_PREFIX}/clips/${encodeURIComponent(clipId)}/resolve/download/${artifact}`;

export function useServerEvents(
  sessionId: string | undefined,
  onEvent: (ev: ServerSseEvent) => void
): void {
  const cbRef = useRef(onEvent);
  cbRef.current = onEvent;

  useEffect(() => {
    const q = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
    const es = new EventSource(`${API_PREFIX}/events${q}`);
    es.onmessage = (msg) => {
      try {
        const parsed = JSON.parse(msg.data) as ServerSseEvent;
        cbRef.current(parsed);
      } catch {
        // Ignore keepalive comments
      }
    };
    return () => {
      es.close();
    };
  }, [sessionId]);
}
