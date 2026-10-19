"use client";

import React, { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAtom } from "jotai";
import {
  aiConfigAtom,
  brandTemplatesAtom,
  clipsAtom,
  draftSubmissionAtom,
  projectsAtom,
  selectedBrandTemplateIdAtom,
} from "@/store/opusStore";
import { AspectRatioOption, ClipProject } from "@/types/opus";
import { formatSecondsToTimecode } from "@/lib/multipartUploader";
import {
  Sparkles,
  ArrowLeft,
  Film,
  Play,
  Pause,
  Scissors,
  Check,
  AlertCircle,
  SlidersHorizontal,
  RotateCcw,
  Volume2,
  VolumeX,
} from "lucide-react";

export default function WorkflowPage() {
  const router = useRouter();
  const [draft, setDraft] = useAtom(draftSubmissionAtom);
  const [, setProjects] = useAtom(projectsAtom);
  const [, setClips] = useAtom(clipsAtom);
  const [brandTemplates] = useAtom(brandTemplatesAtom);
  const [selectedBrandId, setSelectedBrandId] = useAtom(selectedBrandTemplateIdAtom);
  const [aiConfig] = useAtom(aiConfigAtom);

  const [isGenerating, setIsGenerating] = useState(false);
  const [progressMsg, setProgressMsg] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const previewVideoRef = useRef<HTMLVideoElement | null>(null);
  const [isPlayingPreview, setIsPlayingPreview] = useState(false);
  const [previewTime, setPreviewTime] = useState(draft.rangeStartSec || 0);
  const [isMutedPreview, setIsMutedPreview] = useState(false);

  const totalDuration = Math.max(15, draft.durationSec || 300);
  const rangeDuration = Math.max(5, draft.rangeEndSec - draft.rangeStartSec);

  const extractYtId = (url?: string) => {
    return url?.match(/(?:v=|youtu\.be\/|embed\/|shorts\/)([a-zA-Z0-9_-]{11})/)?.[1];
  };

  const ytId = extractYtId(draft.sourceUrl);
  const resolvedStreamUrl =
    draft.localObjectUrl || (ytId ? `/api/video-stream?videoId=${ytId}` : null);

  const handleTogglePreviewPlay = () => {
    const v = previewVideoRef.current;
    if (!v) return;
    if (v.paused) {
      if (v.currentTime < draft.rangeStartSec || v.currentTime >= draft.rangeEndSec) {
        v.currentTime = draft.rangeStartSec;
      }
      v.play().catch(() => {});
      setIsPlayingPreview(true);
    } else {
      v.pause();
      setIsPlayingPreview(false);
    }
  };

  const handleSeekPreview = (sec: number) => {
    const clamped = Math.max(0, Math.min(totalDuration, sec));
    setPreviewTime(clamped);
    if (previewVideoRef.current) {
      previewVideoRef.current.currentTime = clamped;
    }
  };

  const handleStartProcessing = async () => {
    setIsGenerating(true);
    setErrorMessage(null);
    setProgressMsg("Extrayendo flujo MP4 directo y transcripción real palabra por palabra...");

    const newProjectId = `proj-${Date.now().toString().slice(-6)}`;
    const finalTitle = draft.title.trim() || "Video Clip";

    try {
      const res = await fetch("/api/ai-curate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: aiConfig.isConnected ? aiConfig.provider : "local",
          apiKey: aiConfig.isConnected ? aiConfig.apiKey : "",
          videoData: {
            url: draft.sourceUrl || draft.localObjectUrl || "",
            title: finalTitle,
            author: draft.author || "",
            durationSec: rangeDuration,
            keywords: draft.keywords || [],
            customPrompt: draft.customPrompt || "",
            modelChoice: draft.model || "ClipAnything",
            aspectRatio: draft.aspectRatio || "9:16",
          },
        }),
      });

      const data = await res.json();
      let generatedClips: any[] = [];

      if (res.ok && data.success && Array.isArray(data.clips) && data.clips.length > 0) {
        generatedClips = data.clips.map((c: any) => ({
          clipId: `clip-${newProjectId}-${c.rank}`,
          projectId: newProjectId,
          rank: c.rank,
          title: c.title,
          viralityScore: c.viralityScore,
          scoreBreakdown: c.scoreBreakdown,
          viralityExplanation: c.viralityExplanation,
          duration: c.duration,
          startSec: draft.rangeStartSec + c.startSec,
          endSec: draft.rangeStartSec + c.endSec,
          aspectRatio: draft.aspectRatio,
          layoutMode: draft.layoutMode || "fill",
          transcriptWords: c.transcriptWords,
          like: c.rank === 1,
          dislike: false,
          isEdited: false,
          hasAutoHook: draft.enableAutoHook,
          hookText: c.hookText,
          brollSegments: [],
          captionPresetId: selectedBrandId,
          keywords: draft.keywords || ["viral"],
          videoUrl: draft.localObjectUrl || c.videoStreamUrl || data.videoStreamUrl,
          thumbnailUrl: draft.thumbnailUrl,
          cropX: 50,
          zoom: 1,
        }));
      }

      // Save project to Jotai / LocalStorage
      const newProject: ClipProject = {
        id: newProjectId,
        projectId: newProjectId,
        title: finalTitle,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        stage: "COMPLETE",
        progress: 1,
        sourceInfo: {
          title: finalTitle,
          type: draft.platform,
          videoUrl: draft.sourceUrl,
          thumbnailUrl: draft.thumbnailUrl,
          durationMs: rangeDuration * 1000,
          resolution: draft.resolution,
          language: "es",
        },
        productTier: "PRO",
        clipCount: generatedClips.length,
        isPrivate: true,
        storageStatus: "PERMANENT",
        storageExpireAt: "",
        collectionIds: [],
        workflowId: draft.workflowId,
        brandTemplateId: selectedBrandId,
        curationPref: {
          model: "ClipAnything",
          genre: "Auto",
          clipLengths: draft.clipLengths,
          customPrompt: draft.customPrompt,
          keywords: draft.keywords,
          rangeStartSec: draft.rangeStartSec,
          rangeEndSec: draft.rangeEndSec,
          skipSlicing: false,
        },
        renderPref: {
          enableCaptions: draft.enableCaptions,
          enableAutoHook: draft.enableAutoHook,
          enableEmojis: draft.enableEmojis,
          removeFillerWords: draft.removeFillerWords,
          removePauses: draft.removePauses,
          brollType: "none",
          enableSpeechEnhance: false,
          enableUpscale: false,
          aspectRatio: draft.aspectRatio,
          layoutMode: draft.layoutMode,
        },
        creditsCharged: 0,
        creditsFrozen: 0,
      };

      setProjects((prev) => [newProject, ...prev]);
      setClips((prev) => [...prev, ...generatedClips]);

      router.push(`/clip/${newProjectId}`);
    } catch (err: any) {
      setErrorMessage(`Error procesando clips: ${err.message}`);
      setIsGenerating(false);
      setProgressMsg(null);
    }
  };

  return (
    <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Top Header */}
      <div className="flex items-center justify-between border-b border-[var(--border)] pb-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/dashboard")}
            className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-2 text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition cursor-pointer"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-[var(--foreground)]">
              Configuración de Clips
            </h1>
            <p className="text-xs text-[var(--muted-foreground)] truncate max-w-lg">
              {draft.title || "Video seleccionado"}
            </p>
          </div>
        </div>

        <button
          onClick={handleStartProcessing}
          disabled={isGenerating}
          className="inline-flex items-center gap-2 rounded-xl bg-[var(--primary)] px-5 py-2.5 text-xs font-bold text-white shadow-xs hover:opacity-95 transition disabled:opacity-50 cursor-pointer"
        >
          <Sparkles className="h-4 w-4" />
          <span>{isGenerating ? progressMsg || "Generando..." : "Generar Clips"}</span>
        </button>
      </div>

      {errorMessage && (
        <div className="flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-600 dark:text-red-400">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Main 2-Column Creative Studio */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: Video Preview & Range Trimmer (5 cols) */}
        <div className="lg:col-span-5 rounded-3xl border border-[var(--border)] bg-[var(--card)] p-5 shadow-card space-y-4">
          <div className="text-xs font-bold text-[var(--foreground)] flex items-center justify-between">
            <span>Previsualización del Video</span>
            <span className="text-[var(--muted-foreground)] font-mono">
              {formatSecondsToTimecode(draft.rangeStartSec)} – {formatSecondsToTimecode(draft.rangeEndSec)}
            </span>
          </div>

          <div className="relative aspect-video rounded-2xl overflow-hidden bg-black border border-black/10 group">
            {resolvedStreamUrl ? (
              <>
                <video
                  ref={previewVideoRef}
                  src={`${resolvedStreamUrl}#t=${draft.rangeStartSec},${draft.rangeEndSec}`}
                  poster={draft.thumbnailUrl}
                  preload="metadata"
                  playsInline
                  muted={isMutedPreview}
                  onClick={handleTogglePreviewPlay}
                  onLoadedMetadata={(e) => {
                    const v = e.currentTarget;
                    if (v.currentTime < draft.rangeStartSec || v.currentTime > draft.rangeEndSec) {
                      v.currentTime = draft.rangeStartSec;
                    }
                  }}
                  onTimeUpdate={(e) => {
                    const v = e.currentTarget;
                    if (v.currentTime < draft.rangeStartSec - 0.25) {
                      v.currentTime = draft.rangeStartSec;
                      return;
                    }
                    if (v.currentTime >= draft.rangeEndSec) {
                      v.currentTime = draft.rangeStartSec;
                      setPreviewTime(draft.rangeStartSec);
                      if (!v.paused) v.play().catch(() => {});
                      return;
                    }
                    setPreviewTime(v.currentTime);
                  }}
                  onPlay={() => setIsPlayingPreview(true)}
                  onPause={() => setIsPlayingPreview(false)}
                  className="h-full w-full object-contain cursor-pointer"
                />

                {/* Glassmorphic Centered Play Overlay when paused */}
                {!isPlayingPreview && (
                  <button
                    type="button"
                    onClick={handleTogglePreviewPlay}
                    className="absolute inset-0 m-auto h-14 w-14 rounded-full bg-black/60 backdrop-blur-xs flex items-center justify-center text-white border border-white/20 shadow-xl hover:scale-110 hover:bg-[var(--primary)] hover:text-black transition cursor-pointer"
                    title="Reproducir fragmento seleccionado"
                  >
                    <Play className="h-6 w-6 fill-current ml-0.5" />
                  </button>
                )}

                {/* Sleek bottom control overlay */}
                <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 via-black/40 to-transparent p-3 pt-6 flex items-center justify-between text-xs text-white opacity-95 transition">
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={handleTogglePreviewPlay}
                      className="p-1 rounded-md hover:bg-white/20 transition cursor-pointer"
                    >
                      {isPlayingPreview ? (
                        <Pause className="h-4 w-4 fill-current" />
                      ) : (
                        <Play className="h-4 w-4 fill-current" />
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleSeekPreview(draft.rangeStartSec)}
                      className="p-1 rounded-md hover:bg-white/20 transition cursor-pointer text-white/80 hover:text-white"
                      title="Reiniciar al inicio del fragmento"
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                    </button>
                    <span className="font-mono text-[11px] text-white/90">
                      {formatSecondsToTimecode(Math.round(previewTime))} / {formatSecondsToTimecode(draft.rangeEndSec)}
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-[10px] uppercase font-bold tracking-wider text-emerald-400 bg-emerald-950/80 px-2 py-0.5 rounded border border-emerald-500/30">
                      Motor Nativo MP4
                    </span>
                    <button
                      type="button"
                      onClick={() => setIsMutedPreview((m) => !m)}
                      className="p-1 rounded-md hover:bg-white/20 transition cursor-pointer"
                    >
                      {isMutedPreview ? (
                        <VolumeX className="h-4 w-4 text-red-400" />
                      ) : (
                        <Volume2 className="h-4 w-4 text-white" />
                      )}
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <img
                src={draft.thumbnailUrl}
                alt={draft.title}
                className="h-full w-full object-cover"
              />
            )}
          </div>

          {/* Simple Range Slider */}
          <div className="space-y-2 pt-2">
            <div className="flex items-center justify-between text-xs text-[var(--muted-foreground)]">
              <span>Recortar fragmento a procesar</span>
              <span className="font-semibold text-[var(--primary)]">{rangeDuration}s de duración</span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[11px] text-[var(--muted-foreground)] mb-1">
                  Inicio ({formatSecondsToTimecode(draft.rangeStartSec)})
                </label>
                <input
                  type="range"
                  min={0}
                  max={Math.max(0, draft.rangeEndSec - 5)}
                  value={draft.rangeStartSec}
                  onChange={(e) => {
                    const newStart = Number(e.target.value);
                    setDraft((prev) => ({ ...prev, rangeStartSec: newStart }));
                    if (previewVideoRef.current) {
                      previewVideoRef.current.currentTime = newStart;
                      setPreviewTime(newStart);
                    }
                  }}
                  className="w-full accent-[var(--primary)]"
                />
              </div>
              <div>
                <label className="block text-[11px] text-[var(--muted-foreground)] mb-1">
                  Fin ({formatSecondsToTimecode(draft.rangeEndSec)})
                </label>
                <input
                  type="range"
                  min={draft.rangeStartSec + 5}
                  max={totalDuration}
                  value={draft.rangeEndSec}
                  onChange={(e) => {
                    const newEnd = Number(e.target.value);
                    setDraft((prev) => ({ ...prev, rangeEndSec: newEnd }));
                    if (previewVideoRef.current) {
                      previewVideoRef.current.currentTime = Math.max(draft.rangeStartSec, newEnd - 1);
                      setPreviewTime(Math.max(draft.rangeStartSec, newEnd - 1));
                    }
                  }}
                  className="w-full accent-[var(--primary)]"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Creative Parameters (7 cols) */}
        <div className="lg:col-span-7 rounded-3xl border border-[var(--border)] bg-[var(--card)] p-5 sm:p-6 shadow-card space-y-6">
          {/* 1. Aspect Ratio */}
          <div className="space-y-2">
            <label className="block text-xs font-bold text-[var(--foreground)]">
              Formato de Salida
            </label>
            <div className="grid grid-cols-3 gap-2.5">
              {(
                [
                  { id: "9:16", title: "9:16 Vertical", desc: "Shorts, TikTok, Reels" },
                  { id: "16:9", title: "16:9 Horizontal", desc: "YouTube, Podcasts" },
                  { id: "1:1", title: "1:1 Cuadrado", desc: "Feed, LinkedIn" },
                ] as const
              ).map((ar) => (
                <button
                  key={ar.id}
                  type="button"
                  onClick={() => setDraft((prev) => ({ ...prev, aspectRatio: ar.id }))}
                  className={`rounded-2xl border p-3 text-left transition cursor-pointer ${
                    draft.aspectRatio === ar.id
                      ? "border-[var(--primary)] bg-[var(--primary-subtle)]"
                      : "border-[var(--border)] bg-[var(--secondary)] hover:border-[var(--border-strong)]"
                  }`}
                >
                  <div
                    className={`text-xs font-bold ${
                      draft.aspectRatio === ar.id ? "text-[var(--primary)]" : "text-[var(--foreground)]"
                    }`}
                  >
                    {ar.title}
                  </div>
                  <div className="text-[10px] text-[var(--muted-foreground)] mt-0.5">
                    {ar.desc}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* 2. Desired Clip Length */}
          <div className="space-y-2">
            <label className="block text-xs font-bold text-[var(--foreground)]">
              Longitud Deseada de los Clips
            </label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {(
                [
                  { id: "Auto (<90s)", label: "Auto (<90s)" },
                  { id: "<30s", label: "<30s" },
                  { id: "30s~60s", label: "30s a 60s" },
                  { id: "60s~90s", label: "60s a 90s" },
                ] as const
              ).map((len) => (
                <button
                  key={len.id}
                  type="button"
                  onClick={() => setDraft((prev) => ({ ...prev, clipLengths: [len.id] }))}
                  className={`rounded-xl border py-2 px-3 text-xs font-semibold text-center transition cursor-pointer ${
                    draft.clipLengths?.includes(len.id)
                      ? "border-[var(--primary)] bg-[var(--primary)] text-white shadow-xs"
                      : "border-[var(--border)] bg-[var(--secondary)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                  }`}
                >
                  {len.label}
                </button>
              ))}
            </div>
          </div>

          {/* 3. Subtitle Template Preset */}
          <div className="space-y-2">
            <label className="block text-xs font-bold text-[var(--foreground)]">
              Estilo de Subtítulos Karaoke
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {brandTemplates.slice(0, 4).map((bt) => (
                <button
                  key={bt.id}
                  type="button"
                  onClick={() => setSelectedBrandId(bt.id)}
                  className={`flex items-center justify-between rounded-xl border p-2.5 text-left transition cursor-pointer ${
                    selectedBrandId === bt.id
                      ? "border-[var(--primary)] bg-[var(--primary-subtle)]"
                      : "border-[var(--border)] bg-[var(--secondary)] hover:border-[var(--border-strong)]"
                  }`}
                >
                  <div className="truncate">
                    <div
                      className={`text-xs font-bold truncate ${
                        selectedBrandId === bt.id ? "text-[var(--primary)]" : "text-[var(--foreground)]"
                      }`}
                    >
                      {bt.name}
                    </div>
                    <div className="text-[10px] text-[var(--muted-foreground)]">
                      {bt.fontFamily || "Josefin Sans"} · {bt.animationStyle}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0 ml-2">
                    <span
                      className="h-3 w-3 rounded-full border border-black/10"
                      style={{ backgroundColor: bt.highlightColor1 }}
                    />
                    <span
                      className="h-3 w-3 rounded-full border border-black/10"
                      style={{ backgroundColor: bt.highlightColor2 }}
                    />
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* 4. Topic Guidance (Optional Prompt) */}
          <div className="space-y-1.5">
            <label className="block text-xs font-bold text-[var(--foreground)]">
              Enfoque Temático (Prompt opcional)
            </label>
            <input
              type="text"
              value={draft.customPrompt}
              onChange={(e) => setDraft((prev) => ({ ...prev, customPrompt: e.target.value }))}
              placeholder="Ej: Momentos de humor, consejos financieros clave, conclusiones impactantes..."
              className="w-full rounded-xl border border-[var(--border)] bg-[var(--secondary)] px-3.5 py-2.5 text-xs text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:border-[var(--primary)] focus:bg-[var(--card)] focus:outline-none"
            />
          </div>

          {/* 5. Toggles (Clean, No pricing) */}
          <div className="space-y-2 pt-2 border-t border-[var(--border)]">
            <label className="flex items-center justify-between text-xs cursor-pointer">
              <span className="font-semibold text-[var(--foreground)]">
                Subtítulos automáticos sincronizados
              </span>
              <input
                type="checkbox"
                checked={draft.enableCaptions}
                onChange={(e) =>
                  setDraft((prev) => ({ ...prev, enableCaptions: e.target.checked }))
                }
                className="h-4 w-4 accent-[var(--primary)] rounded"
              />
            </label>

            <label className="flex items-center justify-between text-xs cursor-pointer">
              <span className="font-semibold text-[var(--foreground)]">
                Auto-Hook (Título gancho superior en primeros 3s)
              </span>
              <input
                type="checkbox"
                checked={draft.enableAutoHook}
                onChange={(e) =>
                  setDraft((prev) => ({ ...prev, enableAutoHook: e.target.checked }))
                }
                className="h-4 w-4 accent-[var(--primary)] rounded"
              />
            </label>
          </div>

          {/* Submit Action */}
          <div className="pt-4">
            <button
              type="button"
              onClick={handleStartProcessing}
              disabled={isGenerating}
              className="w-full inline-flex items-center justify-center gap-2 rounded-2xl bg-[var(--primary)] px-6 py-3.5 text-sm font-bold text-white shadow-xs hover:opacity-95 transition disabled:opacity-50 cursor-pointer"
            >
              <Sparkles className="h-4 w-4" />
              <span>{isGenerating ? progressMsg || "Generando..." : "Generar Clips con IA"}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
