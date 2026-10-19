"use client";

import React, { use, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAtom } from "jotai";
import {
  aiConfigAtom,
  brandTemplatesAtom,
  clipsAtom,
  projectsAtom,
} from "@/store/opusStore";
import { AspectRatioOption, CuratedClip } from "@/types/opus";
import { formatSecondsToTimecode } from "@/lib/multipartUploader";
import { getCleanVisibleWords, getNaturalSubtitlePhrase } from "@/lib/transcriptUtils";
import { exportAndDownloadClip, ClipExportProgress } from "@/lib/clipExporter";
import {
  ArrowLeft,
  Play,
  Pause,
  ThumbsUp,
  ThumbsDown,
  Scissors,
  Download,
  Search,
  Check,
  FileCode2,
  FileText,
  SlidersHorizontal,
  Flame,
  RefreshCw,
  Volume2,
  VolumeX,
  Sparkles,
} from "lucide-react";

function extractYouTubeIdFromProject(url?: string, thumb?: string): string | null {
  const fromUrl = url?.match(/(?:v=|youtu\.be\/|embed\/|shorts\/)([a-zA-Z0-9_-]{11})/)?.[1];
  if (fromUrl) return fromUrl;
  const fromThumb = thumb?.match(/\/vi(?:_webp)?\/([a-zA-Z0-9_-]{11})\//)?.[1];
  return fromThumb || null;
}

export default function ProjectClipsResultPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: projectId } = use(params);
  const router = useRouter();
  const [projects] = useAtom(projectsAtom);
  const [clips, setClips] = useAtom(clipsAtom);
  const [brandTemplates] = useAtom(brandTemplatesAtom);
  const [aiConfig] = useAtom(aiConfigAtom);

  const [sortBy, setSortBy] = useState<"score" | "chronological">("score");
  const [filterMode, setFilterMode] = useState<"all" | "liked" | "edited">("all");
  const [searchKeyword, setSearchKeyword] = useState("");
  const [playingClipId, setPlayingClipId] = useState<string | null>(null);
  const [clipPlayheads, setClipPlayheads] = useState<Record<string, number>>({});
  const [isMuted, setIsMuted] = useState(false);
  const [isSyncingRealData, setIsSyncingRealData] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [autoZoomActive, setAutoZoomActive] = useState<Record<string, boolean>>({});
  const [autoReframeActive, setAutoReframeActive] = useState<Record<string, boolean>>({});
  const [exportingClipId, setExportingClipId] = useState<string | null>(null);
  const [exportProgress, setExportProgress] = useState<ClipExportProgress | null>(null);

  const videoRefs = useRef<Record<string, HTMLVideoElement | null>>({});
  const autoUpgradedRef = useRef<Record<string, boolean>>({});

  const project =
    projects.find((p) => p.id === projectId || p.projectId === projectId) ||
    projects[0];

  const projectClips = clips.filter((c) => c.projectId === project?.id);

  const projectYtId = extractYouTubeIdFromProject(
    project?.sourceInfo?.videoUrl,
    projectClips[0]?.thumbnailUrl || project?.sourceInfo?.thumbnailUrl
  );

  // Sync function to upgrade any YouTube project to real Innertube MP4 stream + real ASR word-by-word captions
  const handleSyncRealTranscriptAndStream = async (silent = false) => {
    if (!project || !projectYtId || isSyncingRealData) return;
    setIsSyncingRealData(true);
    if (!silent) {
      setToastMessage("Extrayendo flujo MP4 directo y transcripción real palabra por palabra desde YouTube...");
    }

    try {
      const durationSec = Math.max(
        30,
        Math.round((project.sourceInfo.durationMs || 600000) / 1000)
      );
      const res = await fetch("/api/ai-curate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: aiConfig.isConnected ? aiConfig.provider : "local",
          apiKey: aiConfig.isConnected ? aiConfig.apiKey : "",
          videoData: {
            url: project.sourceInfo.videoUrl || `https://www.youtube.com/watch?v=${projectYtId}`,
            title: project.title,
            author: "",
            durationSec,
            keywords: project.curationPref?.keywords || [],
            customPrompt: project.curationPref?.customPrompt || "",
            modelChoice: project.curationPref?.model || "ClipAnything",
            aspectRatio: project.renderPref?.aspectRatio || "9:16",
          },
        }),
      });

      const data = await res.json();
      if (res.ok && data.success && Array.isArray(data.clips) && data.clips.length > 0) {
        const updatedClips: CuratedClip[] = data.clips.map((c: any, index: number) => {
          const existing = projectClips[index];
          return {
            clipId: existing?.clipId || `clip-${project.id}-${c.rank}`,
            projectId: project.id,
            rank: c.rank,
            title: c.title,
            viralityScore: c.viralityScore,
            scoreBreakdown: c.scoreBreakdown,
            viralityExplanation: c.viralityExplanation,
            duration: c.duration,
            startSec: c.startSec,
            endSec: c.endSec,
            aspectRatio: existing?.aspectRatio || project.renderPref?.aspectRatio || "9:16",
            layoutMode: existing?.layoutMode || project.renderPref?.layoutMode || "fill",
            transcriptWords: c.transcriptWords,
            like: existing?.like ?? c.rank === 1,
            dislike: existing?.dislike ?? false,
            isEdited: existing?.isEdited ?? false,
            hasAutoHook: existing?.hasAutoHook ?? true,
            hookText: c.hookText,
            brollSegments: existing?.brollSegments || [],
            captionPresetId: existing?.captionPresetId || project.brandTemplateId || "bt-1",
            keywords: existing?.keywords || project.curationPref?.keywords || ["viral"],
            videoUrl: c.videoStreamUrl || data.videoStreamUrl || `/api/video-stream?videoId=${projectYtId}`,
            thumbnailUrl: existing?.thumbnailUrl || project.sourceInfo.thumbnailUrl,
            cropX: existing?.cropX ?? 50,
            zoom: existing?.zoom ?? 1,
          };
        });

        setClips((prev) => [
          ...prev.filter((c) => c.projectId !== project.id),
          ...updatedClips,
        ]);

        setToastMessage(
          data.hasRealTranscript
            ? "Video MP4 directo y subtítulos reales sincronizados con éxito."
            : "Flujo de video MP4 directo sincronizado."
        );
        setTimeout(() => setToastMessage(null), 3500);
      }
    } catch (err) {
      console.error("Error sincronizando transcripción real:", err);
    } finally {
      setIsSyncingRealData(false);
    }
  };

  // Note: Resync is strictly user-initiated to save LLM tokens and API calls

  const handleTogglePlayClip = (clip: CuratedClip) => {
    const currentVideo = videoRefs.current[clip.clipId];

    if (playingClipId === clip.clipId) {
      if (currentVideo) currentVideo.pause();
      setPlayingClipId(null);
      return;
    }

    if (playingClipId && videoRefs.current[playingClipId]) {
      videoRefs.current[playingClipId]?.pause();
    }

    setPlayingClipId(clip.clipId);
    if (currentVideo) {
      const relPos = clipPlayheads[clip.clipId] || 0;
      const targetTime =
        relPos > 0 && relPos < clip.duration
          ? clip.startSec + relPos
          : clip.startSec;
      if (Math.abs(currentVideo.currentTime - targetTime) > 0.5) {
        currentVideo.currentTime = targetTime;
      }
      currentVideo.play().catch(() => {});
    }
  };

  const handleSeekToWord = (clip: CuratedClip, wordStartRelSec: number) => {
    if (playingClipId && playingClipId !== clip.clipId) {
      videoRefs.current[playingClipId]?.pause();
    }
    setPlayingClipId(clip.clipId);
    setClipPlayheads((prev) => ({ ...prev, [clip.clipId]: wordStartRelSec }));

    const videoEl = videoRefs.current[clip.clipId];
    if (videoEl) {
      videoEl.currentTime = clip.startSec + wordStartRelSec;
      videoEl.play().catch(() => {});
    }
  };

  const filteredClips = projectClips
    .filter((clip) => {
      if (filterMode === "liked" && !clip.like) return false;
      if (filterMode === "edited" && !clip.isEdited) return false;
      if (searchKeyword.trim()) {
        const q = searchKeyword.toLowerCase();
        const inTitle = clip.title.toLowerCase().includes(q);
        const inTranscript = clip.transcriptWords.some((w) =>
          w.word.toLowerCase().includes(q)
        );
        return inTitle || inTranscript;
      }
      return true;
    })
    .sort((a, b) =>
      sortBy === "score"
        ? b.viralityScore - a.viralityScore
        : a.startSec - b.startSec
    );

  const handleToggleLike = (clipId: string) => {
    setClips((prev) =>
      prev.map((c) =>
        c.clipId === clipId ? { ...c, like: !c.like, dislike: false } : c
      )
    );
  };

  const handleChangeAspect = (clipId: string, aspectRatio: AspectRatioOption) => {
    setClips((prev) =>
      prev.map((c) => (c.clipId === clipId ? { ...c, aspectRatio, isEdited: true } : c))
    );
  };

  const handleDownloadClip = async (clip: CuratedClip) => {
    const resolvedVideoId =
      projectYtId ||
      extractYouTubeIdFromProject(clip.videoUrl, clip.thumbnailUrl) ||
      extractYouTubeIdFromProject(project?.sourceInfo?.videoUrl, project?.sourceInfo?.thumbnailUrl);

    const streamUrl =
      clip.videoUrl ||
      (resolvedVideoId ? `/api/video-stream?videoId=${resolvedVideoId}` : undefined);

    if (!streamUrl && !resolvedVideoId) {
      alert("No se encontró el flujo de video para este clip.");
      return;
    }

    setExportingClipId(clip.clipId);
    setExportProgress({
      status: "preparing",
      progress: 8,
      message: `Iniciando descarga Full HD de ${clip.title || "Clip"}...`,
    });

    try {
      await exportAndDownloadClip({
        videoUrl: streamUrl || `/api/video-stream?videoId=${resolvedVideoId}`,
        videoId: resolvedVideoId || undefined,
        startSec: clip.startSec,
        endSec: clip.endSec,
        title: clip.title,
        transcriptWords: clip.transcriptWords,
        aspectRatio: clip.aspectRatio,
        cropX: clip.cropX ?? 50,
        zoom: clip.zoom ?? 1.0,
        hookText: clip.hasAutoHook ? clip.hookText : undefined,
        burnSubtitles: true,
        onProgress: (p) => setExportProgress(p),
      });
    } catch (err: any) {
      alert(`Error al descargar el clip: ${err?.message || "Desconocido"}`);
    } finally {
      setTimeout(() => {
        setExportingClipId(null);
        setExportProgress(null);
      }, 2000);
    }
  };

  const handleExportFile = (clip: CuratedClip, format: "srt" | "xml") => {
    let content = "";
    const filename = `${clip.clipId}.${format}`;
    let mime = "text/plain;charset=utf-8";

    if (format === "srt") {
      const activeWords = getCleanVisibleWords(clip.transcriptWords);
      const chunks: typeof activeWords[] = [];
      let currentChunk: typeof activeWords = [];

      for (let i = 0; i < activeWords.length; i++) {
        const w = activeWords[i];
        if (currentChunk.length === 0) {
          currentChunk.push(w);
        } else {
          const prev = currentChunk[currentChunk.length - 1];
          const gap = w.start - prev.end;
          const endsWithPunct = /[.!?;:¡¿]$/.test(prev.word.trim());
          if (gap > 0.45 || endsWithPunct || currentChunk.length >= 4) {
            chunks.push(currentChunk);
            currentChunk = [w];
          } else {
            currentChunk.push(w);
          }
        }
      }
      if (currentChunk.length > 0) chunks.push(currentChunk);
      content = chunks
        .map((group, idx) => {
          const start = group[0].start;
          const end = group[group.length - 1].end;
          const sMin = String(Math.floor(start / 60)).padStart(2, "0");
          const sSec = String(Math.floor(start % 60)).padStart(2, "0");
          const sMs = String(Math.round((start % 1) * 1000)).padStart(3, "0");
          const eMin = String(Math.floor(end / 60)).padStart(2, "0");
          const eSec = String(Math.floor(end % 60)).padStart(2, "0");
          const eMs = String(Math.round((end % 1) * 1000)).padStart(3, "0");
          return `${idx + 1}\n00:${sMin}:${sSec},${sMs} --> 00:${eMin}:${eSec},${eMs}\n${group
            .map((w) => w.word)
            .join(" ")}\n`;
        })
        .join("\n");
    } else {
      mime = "application/xml;charset=utf-8";
      content = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="5">
  <sequence id="${clip.clipId}">
    <name>${clip.title.replace(/&/g, "&amp;")}</name>
    <duration>${clip.duration * 30}</duration>
    <rate><timebase>30</timebase><ntsc>TRUE</ntsc></rate>
    <media>
      <video>
        <format>
          <samplecharacteristics>
            <width>${clip.aspectRatio === "9:16" ? 1080 : 1920}</width>
            <height>${clip.aspectRatio === "9:16" ? 1920 : 1080}</height>
          </samplecharacteristics>
        </format>
        <track>
          <clipitem id="master-${clip.clipId}">
            <name>${clip.title.replace(/&/g, "&amp;")}</name>
            <in>${clip.startSec * 30}</in>
            <out>${clip.endSec * 30}</out>
          </clipitem>
        </track>
      </video>
    </media>
  </sequence>
</xmeml>`;
    }

    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);

    setToastMessage(
      format === "xml"
        ? `Secuencia XML (${filename}) exportada para Premiere Pro / DaVinci Resolve.`
        : `Subtítulos SRT (${filename}) descargados correctamente.`
    );
    setTimeout(() => setToastMessage(null), 3500);
  };

  return (
    <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Top Project Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[var(--border)] pb-5">
        <div className="flex items-start gap-3">
          <button
            onClick={() => router.push("/dashboard")}
            className="mt-1 rounded-xl border border-[var(--border)] bg-[var(--card)] p-2 text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition cursor-pointer"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-md bg-[var(--primary-subtle)] px-2 py-0.5 text-[10px] font-bold text-[var(--primary)]">
                {filteredClips.length} Clips Curados
              </span>
              <span className="text-xs text-[var(--muted-foreground)]">
                {project.sourceInfo.type} · {project.sourceInfo.resolution}
              </span>
            </div>
            <h1 className="text-lg sm:text-xl font-bold tracking-tight text-[var(--foreground)]">
              {project.title}
            </h1>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-2.5">
          {projectYtId && (
            <button
              onClick={() => handleSyncRealTranscriptAndStream(false)}
              disabled={isSyncingRealData}
              className="inline-flex items-center gap-1.5 rounded-xl border border-[var(--primary-subtle-border)] bg-[var(--primary-subtle)] px-3 py-2 text-xs font-bold text-[var(--primary)] hover:opacity-90 transition disabled:opacity-50 cursor-pointer"
            >
              <RefreshCw
                className={`h-3.5 w-3.5 ${isSyncingRealData ? "animate-spin" : ""}`}
              />
              <span>
                {isSyncingRealData
                  ? "Sincronizando..."
                  : "Sincronizar Audio/Video Real"}
              </span>
            </button>
          )}

          <button
            onClick={() => router.push("/workflow")}
            className="inline-flex items-center gap-1.5 rounded-xl border border-[var(--border)] bg-[var(--card)] px-3.5 py-2 text-xs font-semibold text-[var(--foreground)] hover:border-[var(--primary)] transition cursor-pointer"
          >
            <SlidersHorizontal className="h-3.5 w-3.5" />
            <span>Reconfigurar</span>
          </button>
        </div>
      </div>

      {/* Toast Feedback */}
      {toastMessage && (
        <div className="flex items-center gap-2 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-xs text-emerald-700 dark:text-emerald-300">
          <Check className="h-4 w-4 shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Filter & Sort Controls Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-[var(--muted-foreground)]" />
            <input
              type="text"
              value={searchKeyword}
              onChange={(e) => setSearchKeyword(e.target.value)}
              placeholder="Buscar en subtítulos..."
              className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] pl-8 pr-3 py-1.5 text-xs text-[var(--foreground)] focus:border-[var(--primary)] focus:outline-none w-56"
            />
          </div>

          {(
            [
              { id: "all", label: `Todos (${projectClips.length})` },
              {
                id: "liked",
                label: `Favoritos (${projectClips.filter((c) => c.like).length})`,
              },
            ] as const
          ).map((f) => (
            <button
              key={f.id}
              onClick={() => setFilterMode(f.id)}
              className={`rounded-xl px-3 py-1.5 text-xs font-semibold transition cursor-pointer ${
                filterMode === f.id
                  ? "bg-[var(--primary)] text-white shadow-xs"
                  : "bg-[var(--card)] border border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-[var(--muted-foreground)]">Orden:</span>
          <button
            onClick={() => setSortBy("score")}
            className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition cursor-pointer ${
              sortBy === "score"
                ? "bg-[var(--card)] border border-[var(--border)] text-[var(--primary)] font-bold shadow-xs"
                : "text-[var(--muted-foreground)]"
            }`}
          >
            Puntuación Viral
          </button>
          <button
            onClick={() => setSortBy("chronological")}
            className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition cursor-pointer ${
              sortBy === "chronological"
                ? "bg-[var(--card)] border border-[var(--border)] text-[var(--primary)] font-bold shadow-xs"
                : "text-[var(--muted-foreground)]"
            }`}
          >
            Cronológico
          </button>
        </div>
      </div>

      {/* Curated Clips Feed */}
      <div className="space-y-6">
        {filteredClips.map((clip) => {
          const isPlaying = playingClipId === clip.clipId;
          const clipPlayhead = clipPlayheads[clip.clipId] ?? 0;
          const activeTemplate =
            brandTemplates.find((bt) => bt.id === clip.captionPresetId) ||
            brandTemplates[0];

          const resolvedStreamUrl =
            clip.videoUrl ||
            (projectYtId ? `/api/video-stream?videoId=${projectYtId}` : undefined);

          const visibleWords = getCleanVisibleWords(clip.transcriptWords);
          const activeWordIndex = visibleWords.findIndex(
            (w) => clipPlayhead >= w.start - 0.05 && clipPlayhead <= w.end + 0.15
          );

          // Natural coherent subtitle phrase (avoids gluing words from 5s ahead or across pauses)
          const phraseWords =
            activeWordIndex >= 0
              ? getNaturalSubtitlePhrase(visibleWords, activeWordIndex, clipPlayhead)
              : [];

          const isAutoZoom = autoZoomActive[clip.clipId] ?? true;
          const isAutoReframe = autoReframeActive[clip.clipId] ?? true;
          const activeWord = activeWordIndex >= 0 ? visibleWords[activeWordIndex] : null;

          // Dynamic Auto-Zoom: Punch-in on hook (1.12x), viral punchlines/emojis (1.18x), normal (1.0x)
          const isHookMoment = isPlaying && clipPlayhead < 3.2 && clip.hasAutoHook;
          const isPunchlineMoment =
            isPlaying &&
            Boolean(
              activeWord?.highlight === "color1" ||
                activeWord?.highlight === "color2" ||
                activeWord?.emoji
            );

          const currentDynamicZoom = isAutoZoom
            ? (clip.zoom ?? 1) * (isPunchlineMoment ? 1.18 : isHookMoment ? 1.12 : 1.0)
            : (clip.zoom ?? 1);

          // Dynamic Auto-Encuadre: Smart Speaker Tracking & Conversational Panning in 9:16
          let currentCropX = clip.cropX ?? 50;
          if (isAutoReframe && clip.aspectRatio === "9:16") {
            if (activeWord?.speaker === "Speaker 2") {
              currentCropX = 66; // Right speaker
            } else if (activeWord?.speaker === "Speaker 1") {
              currentCropX = 36; // Left speaker
            } else if (activeWordIndex >= 0) {
              currentCropX = activeWordIndex % 2 === 0 ? 48 : 52;
            }
          }

          return (
            <div
              key={clip.clipId}
              className="grid grid-cols-1 lg:grid-cols-12 gap-6 rounded-3xl border border-[var(--border)] bg-[var(--card)] p-5 sm:p-6 shadow-card"
            >
              {/* LEFT 4 COLS: Native Cropped Vertical Video Player */}
              <div className="lg:col-span-4 flex flex-col items-center justify-between space-y-3">
                <div
                  className={`relative overflow-hidden rounded-2xl border border-[var(--border)] bg-black shadow-card flex items-center justify-center group ${
                    clip.aspectRatio === "9:16"
                      ? "aspect-[9/16] w-full max-w-[250px]"
                      : clip.aspectRatio === "1:1"
                      ? "aspect-square w-full max-w-[270px]"
                      : "aspect-video w-full"
                  }`}
                >
                  {resolvedStreamUrl ? (
                    <video
                      ref={(el) => {
                        videoRefs.current[clip.clipId] = el;
                      }}
                      src={`${resolvedStreamUrl}#t=${clip.startSec},${clip.endSec}`}
                      poster={clip.thumbnailUrl}
                      preload="metadata"
                      playsInline
                      muted={isMuted}
                      onClick={() => handleTogglePlayClip(clip)}
                      onLoadedMetadata={(e) => {
                        const v = e.currentTarget;
                        if (v.currentTime < clip.startSec || v.currentTime > clip.endSec) {
                          v.currentTime = clip.startSec;
                        }
                      }}
                      onTimeUpdate={(e) => {
                        const v = e.currentTarget;
                        if (v.currentTime < clip.startSec - 0.25) {
                          v.currentTime = clip.startSec;
                          return;
                        }
                        if (v.currentTime >= clip.endSec) {
                          v.currentTime = clip.startSec;
                          setClipPlayheads((prev) => ({ ...prev, [clip.clipId]: 0 }));
                          if (!v.paused) v.play().catch(() => {});
                          return;
                        }
                        const relSec = Math.max(0, Number((v.currentTime - clip.startSec).toFixed(2)));

                        // Skip deleted words automatically
                        const hitDeletedWord = clip.transcriptWords.find(
                          (w) => w.deleted && relSec >= w.start && relSec < w.end - 0.05
                        );
                        if (hitDeletedWord) {
                          v.currentTime = clip.startSec + hitDeletedWord.end;
                          return;
                        }

                        setClipPlayheads((prev) => ({
                          ...prev,
                          [clip.clipId]: relSec,
                        }));
                      }}
                      onPlay={() => setPlayingClipId(clip.clipId)}
                      onPause={() => {
                        if (playingClipId === clip.clipId) {
                          setPlayingClipId(null);
                        }
                      }}
                      style={{
                        objectPosition: `${currentCropX}% 50%`,
                        transform: `scale(${currentDynamicZoom})`,
                        transition:
                          "transform 350ms cubic-bezier(0.25, 1, 0.5, 1), object-position 450ms ease",
                      }}
                      className={`h-full w-full cursor-pointer ${
                        clip.layoutMode === "fit" ? "object-contain" : "object-cover"
                      }`}
                    />
                  ) : (
                    <img
                      src={clip.thumbnailUrl}
                      alt={clip.title}
                      className="h-full w-full object-cover brightness-75"
                    />
                  )}

                  {/* Auto Hook Top Banner */}
                  {clip.hasAutoHook && (
                    <div
                      style={{ fontFamily: 'var(--font-josefin), "Josefin Sans", sans-serif' }}
                      className="absolute top-3 inset-x-3 rounded-lg bg-[var(--primary)] px-2.5 py-1 text-center text-[11px] font-black text-white shadow-xs uppercase tracking-tight z-10 pointer-events-none"
                    >
                      {clip.hookText}
                    </div>
                  )}

                  {/* Mute Button */}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setIsMuted((m) => !m);
                    }}
                    className="absolute top-12 right-2.5 z-20 rounded-full bg-black/60 p-1.5 text-white/80 hover:text-white border border-white/10 transition"
                  >
                    {isMuted ? <VolumeX className="h-3.5 w-3.5" /> : <Volume2 className="h-3.5 w-3.5" />}
                  </button>

                  {/* Center Play/Pause Button (Centered via absolute positioning) */}
                  <button
                    onClick={() => handleTogglePlayClip(clip)}
                    className={`absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-30 flex h-14 w-14 items-center justify-center rounded-full bg-black/75 backdrop-blur-xs text-white border border-white/30 shadow-2xl hover:scale-110 hover:bg-black/90 transition cursor-pointer ${
                      isPlaying
                        ? "opacity-0 group-hover:opacity-100 pointer-events-none group-hover:pointer-events-auto"
                        : "opacity-100"
                    }`}
                  >
                    {isPlaying ? (
                      <Pause className="h-5 w-5 fill-current" />
                    ) : (
                      <Play className="h-5 w-5 fill-current ml-0.5" />
                    )}
                  </button>

                  {/* Synchronized Multi-Word Karaoke Caption Overlay (Hides cleanly when speaker is silent) */}
                  {phraseWords.length > 0 && (
                    <div className="absolute bottom-5 inset-x-2.5 text-center pointer-events-none z-10 transition-opacity duration-150">
                      <div className="inline-flex flex-wrap items-center justify-center gap-x-1.5 gap-y-0.5 rounded-xl bg-black/85 backdrop-blur-xs px-3 py-1.5 border border-white/10 shadow-lg">
                        {phraseWords.map((w) => {
                          const isWordActive =
                            isPlaying &&
                            clipPlayhead >= w.start - 0.05 &&
                            clipPlayhead <= w.end + 0.12;
                          return (
                            <span
                              key={w.id}
                              style={{
                                fontFamily: 'var(--font-josefin), "Josefin Sans", sans-serif',
                                color: isWordActive ? "#FBBF24" : "#FFFFFF",
                                transform: isWordActive ? "scale(1.12)" : "scale(1)",
                              }}
                              className="inline-block text-xs sm:text-sm font-black uppercase tracking-wide drop-shadow-md transition-all duration-100"
                            >
                              {w.word}
                              {isWordActive && w.emoji ? ` ${w.emoji}` : ""}
                            </span>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Bottom Progress Bar */}
                  <div className="absolute bottom-0 inset-x-0 h-1 bg-white/20 z-20 pointer-events-none">
                    <div
                      className="h-full bg-[var(--primary)] transition-all duration-100"
                      style={{
                        width: `${Math.min(
                          100,
                          Math.max(0, (clipPlayhead / Math.max(1, clip.duration)) * 100)
                        )}%`,
                      }}
                    />
                  </div>
                </div>

                {/* Intelligence Controls: Auto-Zoom & Auto-Encuadre */}
                <div className="flex flex-wrap items-center justify-center gap-1.5">
                  <button
                    type="button"
                    onClick={() =>
                      setAutoZoomActive((prev) => ({
                        ...prev,
                        [clip.clipId]: !isAutoZoom,
                      }))
                    }
                    className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] font-semibold transition cursor-pointer ${
                      isAutoZoom
                        ? "bg-[var(--primary)] text-white shadow-xs"
                        : "bg-[var(--secondary)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                    }`}
                    title="Aplica zoom dinámico (punch-in) en ganchos y palabras de alto impacto"
                  >
                    <Sparkles className="h-3 w-3" />
                    <span>Auto-Zoom {isAutoZoom ? "ON" : "OFF"}</span>
                  </button>

                  <button
                    type="button"
                    onClick={() =>
                      setAutoReframeActive((prev) => ({
                        ...prev,
                        [clip.clipId]: !isAutoReframe,
                      }))
                    }
                    className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] font-semibold transition cursor-pointer ${
                      isAutoReframe
                        ? "bg-emerald-600 text-white shadow-xs"
                        : "bg-[var(--secondary)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                    }`}
                    title="Sigue automáticamente al hablante activo en formato 9:16 vertical"
                  >
                    <Scissors className="h-3 w-3" />
                    <span>Auto-Encuadre {isAutoReframe ? "ON" : "OFF"}</span>
                  </button>
                </div>

                {/* Aspect Switcher */}
                <div className="flex items-center gap-1">
                  {(["9:16", "16:9", "1:1"] as AspectRatioOption[]).map((ar) => (
                    <button
                      key={ar}
                      onClick={() => handleChangeAspect(clip.clipId, ar)}
                      className={`rounded-lg px-2.5 py-1 text-[11px] font-semibold transition cursor-pointer ${
                        clip.aspectRatio === ar
                          ? "bg-[var(--primary)] text-white shadow-xs"
                          : "bg-[var(--secondary)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                      }`}
                    >
                      {ar}
                    </button>
                  ))}
                </div>
              </div>

              {/* RIGHT 8 COLS: Score, Insight, Transcript & Action Toolbar */}
              <div className="lg:col-span-8 flex flex-col justify-between space-y-4">
                <div className="space-y-4">
                  {/* Rank + Title + Virality Badge */}
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="rounded-md bg-[var(--secondary)] px-2 py-0.5 text-xs font-bold text-[var(--muted-foreground)]">
                          Clip #{clip.rank}
                        </span>
                        <span className="text-xs text-[var(--muted-foreground)] font-mono">
                          {formatSecondsToTimecode(clip.startSec)} – {formatSecondsToTimecode(clip.endSec)} ({clip.duration}s)
                        </span>
                        {clip.transcriptWords?.[0]?.id?.startsWith("ytw-") && (
                          <span className="rounded bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold text-emerald-600 dark:text-emerald-400">
                            Audio Real
                          </span>
                        )}
                      </div>
                      <h2 className="text-base font-bold text-[var(--foreground)]">{clip.title}</h2>
                    </div>

                    {/* Virality Score Badge */}
                    <div className="flex items-center gap-2 shrink-0 rounded-2xl border border-[var(--primary-subtle-border)] bg-[var(--primary-subtle)] px-3.5 py-1.5">
                      <Flame className="h-4 w-4 text-[var(--primary)]" />
                      <div>
                        <div className="text-[10px] font-bold uppercase tracking-wider text-[var(--primary)]">
                          Virality Score
                        </div>
                        <div className="text-lg font-black text-[var(--foreground)] leading-none">
                          {clip.viralityScore}
                          <span className="text-xs font-normal text-[var(--muted-foreground)]">/99</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* AI Explanation */}
                  <div className="rounded-2xl border border-[var(--border)] bg-[var(--secondary)]/40 p-3.5 space-y-2">
                    <div className="grid grid-cols-4 gap-2 text-center">
                      {(
                        [
                          { label: "Gancho", val: clip.scoreBreakdown.hook },
                          { label: "Ritmo", val: clip.scoreBreakdown.flow },
                          { label: "Valor", val: clip.scoreBreakdown.value },
                          { label: "Tendencia", val: clip.scoreBreakdown.trend },
                        ] as const
                      ).map((m) => (
                        <div key={m.label} className="rounded-xl bg-[var(--card)] p-1.5 border border-[var(--border)]">
                          <div className="text-[10px] text-[var(--muted-foreground)]">{m.label}</div>
                          <div className="text-xs font-bold text-[var(--foreground)]">{m.val}</div>
                        </div>
                      ))}
                    </div>
                    <p className="text-xs text-[var(--muted-foreground)] leading-relaxed">
                      <strong className="text-[var(--foreground)]">Análisis de la IA:</strong>{" "}
                      {clip.viralityExplanation}
                    </p>
                  </div>

                  {/* Interactive Transcript */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-[var(--muted-foreground)]">
                        Transcripción (Haz clic para saltar al segundo exacto)
                      </span>
                      <span className="font-mono text-[11px] text-[var(--primary)]">
                        {isPlaying ? "▶ Reproduciendo:" : "Pausado:"}{" "}
                        {formatSecondsToTimecode(clip.startSec + clipPlayhead)}
                      </span>
                    </div>

                    <div className="rounded-2xl border border-[var(--border)] bg-[var(--secondary)]/30 p-3.5 flex flex-wrap gap-1.5 max-h-36 overflow-y-auto">
                      {getCleanVisibleWords(clip.transcriptWords).map((w) => {
                        const isCurrent =
                          isPlaying &&
                          clipPlayhead >= w.start &&
                          clipPlayhead <= w.end + 0.12;
                        return (
                          <button
                            key={w.id}
                            onClick={() => handleSeekToWord(clip, w.start)}
                            style={{ fontFamily: 'var(--font-josefin), "Josefin Sans", sans-serif' }}
                            className={`rounded px-1.5 py-0.5 text-xs transition cursor-pointer ${
                              w.deleted
                                ? "line-through opacity-35"
                                : isCurrent
                                ? "bg-[var(--primary)] text-white font-bold shadow-xs"
                                : "hover:bg-[var(--secondary)] text-[var(--foreground)]"
                            }`}
                          >
                            {w.word}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>

                {/* Bottom Action Toolbar */}
                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--border)] pt-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      onClick={() => handleToggleLike(clip.clipId)}
                      className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-semibold transition cursor-pointer ${
                        clip.like
                          ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                          : "border-[var(--border)] bg-[var(--card)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                      }`}
                    >
                      <ThumbsUp className="h-3.5 w-3.5" />
                      <span>Favorito</span>
                    </button>

                    <button
                      onClick={() => handleDownloadClip(clip)}
                      disabled={exportingClipId === clip.clipId}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-[var(--primary)] bg-[var(--primary)]/10 px-3 py-1.5 text-xs font-bold text-[var(--primary)] hover:bg-[var(--primary)] hover:text-white transition cursor-pointer disabled:opacity-50"
                      title="Descargar exactamente este clip recortado (9:16 con subtítulos)"
                    >
                      {exportingClipId === clip.clipId ? (
                        <>
                          <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                          <span>{exportProgress?.progress || 0}%</span>
                        </>
                      ) : (
                        <>
                          <Download className="h-3.5 w-3.5" />
                          <span>Descargar Clip</span>
                        </>
                      )}
                    </button>

                    {projectYtId && (
                      <a
                        href={`/api/video-stream?videoId=${projectYtId}&download=1`}
                        download={`${clip.clipId}-full.mp4`}
                        className="inline-flex items-center gap-1.5 rounded-xl border border-[var(--border)] bg-[var(--card)] px-2.5 py-1.5 text-xs font-semibold text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition"
                        title="Descargar el video original completo"
                      >
                        <Download className="h-3.5 w-3.5 opacity-60" />
                        <span>Video Completo</span>
                      </a>
                    )}

                    <button
                      onClick={() => handleExportFile(clip, "srt")}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-[var(--border)] bg-[var(--card)] px-3 py-1.5 text-xs font-semibold text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition cursor-pointer"
                    >
                      <FileText className="h-3.5 w-3.5" />
                      <span>Exportar .SRT</span>
                    </button>

                    <button
                      onClick={() => handleExportFile(clip, "xml")}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-[var(--border)] bg-[var(--card)] px-3 py-1.5 text-xs font-semibold text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition cursor-pointer"
                    >
                      <FileCode2 className="h-3.5 w-3.5" />
                      <span>Exportar XML (NLE)</span>
                    </button>
                  </div>

                  <button
                    onClick={() => router.push(`/editor-ux/${clip.clipId}`)}
                    className="inline-flex items-center gap-1.5 rounded-xl bg-[var(--primary)] px-4 py-2 text-xs font-bold text-white shadow-xs hover:opacity-95 transition cursor-pointer"
                  >
                    <Scissors className="h-3.5 w-3.5" />
                    <span>Abrir en Editor NLE</span>
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Floating Clip Export Progress Modal / Toast */}
      {exportingClipId && exportProgress && (
        <div className="fixed bottom-6 right-6 z-50 rounded-2xl border border-[var(--border)] bg-[var(--card)]/95 backdrop-blur-md p-4 shadow-2xl flex items-center gap-3.5 min-w-[320px] max-w-[420px] transition-all">
          <div className="h-10 w-10 rounded-xl bg-[var(--primary)]/15 flex items-center justify-center text-[var(--primary)] shrink-0">
            {exportProgress.status === "done" ? (
              <Check className="h-5 w-5 text-emerald-500" />
            ) : (
              <RefreshCw className="h-5 w-5 animate-spin" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-bold text-[var(--foreground)] truncate">
              {exportProgress.message}
            </div>
            <div className="w-full bg-[var(--secondary)] h-1.5 rounded-full mt-2 overflow-hidden">
              <div
                className="bg-[var(--primary)] h-full transition-all duration-200"
                style={{ width: `${exportProgress.progress}%` }}
              />
            </div>
          </div>
          <span className="text-xs font-extrabold text-[var(--primary)]">
            {exportProgress.progress}%
          </span>
        </div>
      )}
    </div>
  );
}
