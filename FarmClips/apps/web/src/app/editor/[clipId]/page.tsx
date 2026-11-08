"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  Camera,
  Check,
  Crosshair,
  Download,
  Film,
  Layers,
  Loader2,
  Maximize2,
  Move,
  Pause,
  Play,
  Plus,
  Redo2,
  Save,
  Scissors,
  Sliders,
  Sparkles,
  Trash2,
  Type,
  Undo2,
  Volume2,
  Zap,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import {
  API_PREFIX,
  fetchClipDetail,
  fetchEmojiCatalog,
  renderClip,
  saveClipEditPlan,
  useServerEvents,
  type ClipItem,
  type EmojiCatalogItem,
  type SessionSummary,
  type StylePreset,
} from "@/lib/api/client";
import {
  clipToMasterTime,
  evaluateCameraCrop,
  evaluateLayout,
  getTotalClipDuration,
  masterToClipTime,
  type CropKeyframe,
  type EaseKind,
  type EditPlan,
} from "@/lib/api/editplan";

function dbToLinear(db: number): number {
  return Math.pow(10, db / 20);
}

function dbToVoicePct(db: number): number {
  if (db <= 0) {
    return Math.max(0, Math.min(100, Math.round((1 - db / -24) * 100)));
  }
  return Math.min(150, Math.round(100 + (db / 6) * 50));
}

function voicePctToDb(pct: number): number {
  if (pct <= 100) {
    return Number((-24 * (1 - pct / 100)).toFixed(1));
  }
  return Number((((pct - 100) / 50) * 6).toFixed(1));
}

const DUCK_PRESETS = [
  { label: "Apagado", db: 0, desc: "Sin atenuar el juego" },
  { label: "Suave", db: -5, desc: "Atenúa un poco al hablar" },
  { label: "Normal", db: -9, desc: "Recomendado (YouTube/Twitch)" },
  { label: "Fuerte", db: -15, desc: "Máxima prioridad a tu voz" },
];

function applyCameraCoverTransform(
  videoEl: HTMLVideoElement,
  wrapEl: HTMLDivElement,
  cx: number,
  cy: number,
  zoom: number,
  anchorY = 0.44
) {
  const boxW = wrapEl.clientWidth || 330;
  const boxH = wrapEl.clientHeight || 235;
  const vw = videoEl.videoWidth > 0 ? videoEl.videoWidth : 1920;
  const vh = videoEl.videoHeight > 0 ? videoEl.videoHeight : 1080;

  // Escala base para cubrir exactamente la caja (cover)
  const baseScale = Math.max(boxW / vw, boxH / vh);
  const effectiveZoom = Math.max(1.0, zoom);
  const totalScale = baseScale * effectiveZoom;

  const scaledW = vw * totalScale;
  const scaledH = vh * totalScale;

  // Desplazamiento de recorte para centrar (cx, cy) en (boxW * 0.5, boxH * anchorY)
  let cropX = scaledW * cx - boxW * 0.5;
  let cropY = scaledH * cy - boxH * anchorY;

  // Clamp estricto idéntico a OpenCV compute_cover_affine_matrix:
  // La imagen NUNCA puede salirse de la caja ni dejar bandas negras
  const maxCropX = Math.max(0, scaledW - boxW);
  const maxCropY = Math.max(0, scaledH - boxH);

  cropX = Math.max(0, Math.min(cropX, maxCropX));
  cropY = Math.max(0, Math.min(cropY, maxCropY));

  // Aplicar posición y dimensiones directas al elemento de video
  videoEl.style.position = "absolute";
  videoEl.style.left = "0px";
  videoEl.style.top = "0px";
  videoEl.style.width = `${scaledW.toFixed(1)}px`;
  videoEl.style.height = `${scaledH.toFixed(1)}px`;
  videoEl.style.maxWidth = "none";
  videoEl.style.maxHeight = "none";
  videoEl.style.objectFit = "fill";
  videoEl.style.transformOrigin = "0 0";
  videoEl.style.transform = `translate3d(${-cropX.toFixed(1)}px, ${-cropY.toFixed(1)}px, 0)`;
}

export default function ClipEditorPage() {
  const params = useParams<{ clipId: string }>();
  const clipId = params.clipId;

  const [clip, setClip] = useState<ClipItem | null>(null);
  const [session, setSession] = useState<SessionSummary | null>(null);
  const [preset, setPreset] = useState<StylePreset | null>(null);
  const [plan, setPlan] = useState<EditPlan | null>(null);
  const [emojiCatalog, setEmojiCatalog] = useState<EmojiCatalogItem[]>([]);
  const [openEmojiPickerIdx, setOpenEmojiPickerIdx] = useState<number | null>(null);
  const [emojiCategoryFilter, setEmojiCategoryFilter] = useState<string>("all");
  const [liveDuckPct, setLiveDuckPct] = useState<number>(0);

  // Undo / Redo history stacks
  const [undoStack, setUndoStack] = useState<EditPlan[]>([]);
  const [redoStack, setRedoStack] = useState<EditPlan[]>([]);

  const [activeTab, setActiveTab] = useState<"captions" | "camera" | "cuts" | "json">("captions");
  const [previewSource, setPreviewSource] = useState<"live" | "rendered">("live");

  const [playing, setPlaying] = useState(false);
  const [clipTime, setClipTime] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [renderingQuality, setRenderingQuality] = useState<"draft" | "final" | null>(null);
  const [renderProgress, setRenderProgress] = useState<number | null>(null);
  const [statusMsg, setStatusMsg] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  // WYSIWYG Interactive states
  const [isDraggingCam, setIsDraggingCam] = useState(false);
  const [isSnappingCenterX, setIsSnappingCenterX] = useState(false);
  const [isDraggingCaptions, setIsDraggingCaptions] = useState(false);

  // Refs for 60fps zero-render preview + Web Audio API mixer
  const camVideoRef = useRef<HTMLVideoElement | null>(null);
  const gameVideoRef = useRef<HTMLVideoElement | null>(null);
  const camWrapRef = useRef<HTMLDivElement | null>(null);
  const gameWrapRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const scrubberInputRef = useRef<HTMLInputElement | null>(null);
  const timeLabelRef = useRef<HTMLSpanElement | null>(null);
  const playheadBarRef = useRef<HTMLDivElement | null>(null);
  const wordWidthCacheRef = useRef<Map<string, number>>(new Map());
  const lastReactTimeSyncRef = useRef<number>(0);
  const lastCanvasHashRef = useRef<string>("");
  const emojiCacheRef = useRef<Record<string, HTMLImageElement>>({});
  const clipTimeRef = useRef(0);
  const playingRef = useRef(false);
  const planRef = useRef<EditPlan | null>(null);
  const sessionRef = useRef<SessionSummary | null>(null);
  const syncRef = useRef<{ shift: number; scale: number }>({ shift: 0, scale: 1 });

  // Pointer drag trackers
  const dragCamStartRef = useRef<{
    clientX: number;
    clientY: number;
    cx: number;
    cy: number;
    zoom: number;
    initialPlan: EditPlan;
  } | null>(null);

  const dragCapStartRef = useRef<{
    clientY: number;
    initialRatio: number;
    initialPlan: EditPlan;
  } | null>(null);

  // Web Audio API refs
  const audioCtxRef = useRef<AudioContext | null>(null);
  const micGainNodeRef = useRef<GainNode | null>(null);
  const gameGainNodeRef = useRef<GainNode | null>(null);
  const micAnalyserRef = useRef<AnalyserNode | null>(null);
  const analyserBufRef = useRef<Float32Array<ArrayBuffer> | null>(null);
  const mediaSourceMapRef = useRef<WeakMap<HTMLMediaElement, MediaElementAudioSourceNode>>(new WeakMap());
  const sfxBuffersRef = useRef<Record<string, AudioBuffer>>({});
  const duckEnvRef = useRef<number>(1.0);

  planRef.current = plan;
  sessionRef.current = session;
  playingRef.current = playing;

  // Plan mutation with optional history capture
  const mutatePlan = useCallback(
    (updater: (draft: EditPlan) => EditPlan, options?: { skipHistory?: boolean }) => {
      setPlan((prev) => {
        if (!prev) return prev;
        const cloned = structuredClone(prev);
        const updated = updater(cloned);
        if (!options?.skipHistory) {
          setUndoStack((st) => [...st.slice(-30), prev]);
          setRedoStack([]);
        }
        setDirty(true);
        return updated;
      });
    },
    []
  );

  const handleUndo = useCallback(() => {
    if (undoStack.length === 0 || !plan) return;
    const previous = undoStack[undoStack.length - 1];
    const newUndo = undoStack.slice(0, -1);
    setRedoStack((r) => [...r, plan]);
    setUndoStack(newUndo);
    setPlan(previous);
    setDirty(true);
    setStatusMsg("Deshecho el último cambio.");
  }, [undoStack, plan]);

  const handleRedo = useCallback(() => {
    if (redoStack.length === 0 || !plan) return;
    const next = redoStack[redoStack.length - 1];
    const newRedo = redoStack.slice(0, -1);
    setUndoStack((u) => [...u, plan]);
    setRedoStack(newRedo);
    setPlan(next);
    setDirty(true);
    setStatusMsg("Rehecho el cambio.");
  }, [redoStack, plan]);

  // Global Keyboard Shortcuts (Ctrl+Z, Ctrl+Y, Ctrl+Shift+Z, Space to play/pause)
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const isInput =
        target &&
        (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);

      if ((e.ctrlKey || e.metaKey) && (e.key === "z" || e.key === "Z")) {
        if (e.shiftKey) {
          e.preventDefault();
          handleRedo();
        } else {
          if (!isInput) {
            e.preventDefault();
            handleUndo();
          }
        }
      } else if ((e.ctrlKey || e.metaKey) && (e.key === "y" || e.key === "Y")) {
        if (!isInput) {
          e.preventDefault();
          handleRedo();
        }
      } else if (e.code === "Space" && !isInput) {
        e.preventDefault();
        togglePlay();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [handleUndo, handleRedo]);

  const loadAll = useCallback(async () => {
    if (!clipId) return;
    try {
      const data = await fetchClipDetail(clipId);
      setClip(data.clip);
      setSession(data.session);
      setPreset(data.preset);
      if (data.clip.editplan) {
        setPlan(data.clip.editplan);
      }
      syncRef.current = {
        shift: data.session.sync?.shift_sec ?? 0,
        scale: data.session.sync?.scale ?? 1,
      };
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [clipId]);

  useEffect(() => {
    loadAll();
    fetchEmojiCatalog()
      .then(setEmojiCatalog)
      .catch(() => null);
  }, [loadAll]);

  const preloadSfxBuffer = useCallback(async (ctx: AudioContext, sfxId: string) => {
    if (sfxBuffersRef.current[sfxId]) return sfxBuffersRef.current[sfxId];
    try {
      const res = await fetch(`${API_PREFIX}/sfx/${encodeURIComponent(sfxId)}.wav`);
      if (!res.ok) return null;
      const arr = await res.arrayBuffer();
      const decoded = await ctx.decodeAudioData(arr);
      sfxBuffersRef.current[sfxId] = decoded;
      return decoded;
    } catch {
      return null;
    }
  }, []);

  const ensureWebAudio = useCallback(async () => {
    if (typeof window === "undefined") return null;
    let ctx = audioCtxRef.current;
    if (!ctx) {
      const AudioCtx =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      ctx = new AudioCtx();
      audioCtxRef.current = ctx;

      const micGain = ctx.createGain();
      const highpass = ctx.createBiquadFilter();
      highpass.type = "highpass";
      highpass.frequency.value = 75;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      highpass.connect(micGain);
      micGain.connect(analyser);
      analyser.connect(ctx.destination);

      const gameGain = ctx.createGain();
      gameGain.gain.value = 0;
      gameGain.connect(ctx.destination);

      micGainNodeRef.current = micGain;
      gameGainNodeRef.current = gameGain;
      micAnalyserRef.current = analyser;
      analyserBufRef.current = new Float32Array(new ArrayBuffer(analyser.fftSize * 4));
      (micGain as unknown as { _hpInput?: BiquadFilterNode })._hpInput = highpass;
    }

    if (ctx.state === "suspended") {
      await ctx.resume().catch(() => null);
    }

    const cv = camVideoRef.current;
    const gv = gameVideoRef.current;
    const micGain = micGainNodeRef.current;
    const gameGain = gameGainNodeRef.current;
    const hp = (micGain as unknown as { _hpInput?: BiquadFilterNode })?._hpInput;

    if (cv && hp && !mediaSourceMapRef.current.has(cv)) {
      try {
        const src = ctx.createMediaElementSource(cv);
        src.connect(hp);
        mediaSourceMapRef.current.set(cv, src);
      } catch {
        // Ignorar si no soportado
      }
    }
    if (gv && gameGain && !mediaSourceMapRef.current.has(gv)) {
      try {
        gv.muted = false;
        const src = ctx.createMediaElementSource(gv);
        src.connect(gameGain);
        mediaSourceMapRef.current.set(gv, src);
      } catch {
        gv.muted = true;
      }
    }

    await preloadSfxBuffer(ctx, "boom");
    if (planRef.current) {
      for (const cue of planRef.current.audio.sfx) {
        await preloadSfxBuffer(ctx, cue.id);
      }
    }
    return ctx;
  }, [preloadSfxBuffer]);

  const fireSfx = useCallback(
    async (sfxId: string, gainDb = -3) => {
      const ctx = await ensureWebAudio();
      if (!ctx) return;
      const buf = sfxBuffersRef.current[sfxId] || (await preloadSfxBuffer(ctx, sfxId));
      if (!buf) return;
      const src = ctx.createBufferSource();
      src.buffer = buf;
      const g = ctx.createGain();
      g.gain.value = dbToLinear(gainDb);
      src.connect(g);
      g.connect(ctx.destination);
      src.start(0);
    },
    [ensureWebAudio, preloadSfxBuffer]
  );

  useEffect(() => {
    return () => {
      audioCtxRef.current?.close().catch(() => null);
      audioCtxRef.current = null;
    };
  }, []);

  useServerEvents(session?.id, (ev) => {
    if (ev.clip_id === clipId) {
      if (ev.type === "render_progress" && typeof ev.progress === "number") {
        setRenderProgress(ev.progress);
        if (ev.message) setStatusMsg(ev.message);
      }
      if (ev.type === "clip_updated") {
        fetchClipDetail(clipId)
          .then((d) => setClip(d.clip))
          .catch(() => null);
      }
    }
  });

  // Preload emoji PNGs
  useEffect(() => {
    if (!plan) return;
    for (const grp of plan.captions.groups) {
      const eid = grp.emoji?.id;
      if (eid && !emojiCacheRef.current[eid]) {
        const img = new Image();
        img.src = `${API_PREFIX}/emojis/${encodeURIComponent(eid)}.png`;
        emojiCacheRef.current[eid] = img;
      }
    }
  }, [plan]);

  // Fast 60fps render on Canvas + CSS transforms with smart caching
  const renderFrameAt = useCallback(
    (t: number) => {
      const p = planRef.current;
      if (!p) return;

      // 1. Evaluate Layout & Camera Crop
      const layout = evaluateLayout(p.layout, t);
      const crop = evaluateCameraCrop(p.camera_crop, t);

      if (camWrapRef.current && gameWrapRef.current) {
        const camPct = Math.round(layout.cameraRatio * 100);
        camWrapRef.current.style.height = `${camPct}%`;
        camWrapRef.current.style.display = camPct === 0 ? "none" : "block";
        gameWrapRef.current.style.height = `${100 - camPct}%`;
        gameWrapRef.current.style.display = camPct === 100 ? "none" : "block";
      }

      if (camVideoRef.current && camWrapRef.current) {
        applyCameraCoverTransform(
          camVideoRef.current,
          camWrapRef.current,
          crop.cx,
          crop.cy,
          crop.zoom,
          0.44
        );
      }

      // 2. Render Subtitles & Title on Canvas with render-skip caching
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const W = canvas.width;
      const H = canvas.height;
      const splitRatio = p.layout.find((l) => l.kind === "split")?.camera_ratio ?? 0.4;
      const seamY = H * splitRatio;
      const gameH = H - seamY;
      const capRatio = p.captions.vertical_ratio ?? preset?.captions.gameplay_top_third_ratio ?? 0.28;
      const capY = seamY + gameH * capRatio;

      const activeTitle = p.overlays.find(
        (ov) => ov.kind === "title" && t >= ov.start && t <= ov.end && ov.text.trim()
      );

      const activeGroup = p.captions.groups.find((g) => {
        if (!g.words.length) return false;
        const gs = g.words[0].s;
        const ge = g.words[g.words.length - 1].e;
        return t >= gs && t <= ge + 0.04;
      });

      const activeWordIdx = activeGroup
        ? activeGroup.words.findIndex((w) => t >= w.s && t < w.e)
        : -1;
      const hasEmoji = Boolean(activeGroup?.emoji && t >= (activeGroup?.emoji?.at ?? 0));

      const renderHash = `${activeTitle?.text ?? ""}:${activeGroup ? p.captions.groups.indexOf(activeGroup) : -1}:${activeWordIdx}:${hasEmoji}:${Math.round(capY)}:${Math.round(seamY)}`;

      // Skip redrawing if identical to previous frame
      if (lastCanvasHashRef.current === renderHash && !isDraggingCam && !isDraggingCaptions) {
        return;
      }
      lastCanvasHashRef.current = renderHash;

      ctx.clearRect(0, 0, W, H);

      // 2a. Seam Title Overlay
      if (activeTitle) {
        ctx.save();
        ctx.font = '800 24px "Montserrat ExtraBold", Inter, sans-serif';
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        const txt = activeTitle.text.trim();
        const titleKey = `title:24:${txt}`;
        let titleW = wordWidthCacheRef.current.get(titleKey);
        if (titleW === undefined) {
          titleW = ctx.measureText(txt).width;
          wordWidthCacheRef.current.set(titleKey, titleW);
        }
        const padX = 20;
        const boxW = Math.min(W - 36, titleW + padX * 2);
        const boxH = 44;
        const bx = (W - boxW) / 2;
        const by = seamY - boxH / 2;

        ctx.shadowColor = "rgba(0,0,0,0.55)";
        ctx.shadowBlur = 12;
        ctx.fillStyle = "#FFFFFF";
        ctx.beginPath();
        ctx.roundRect(bx, by, boxW, boxH, 10);
        ctx.fill();

        ctx.shadowBlur = 0;
        ctx.fillStyle = "#090A0F";
        ctx.fillText(txt, W / 2, seamY + 1, boxW - 16);
        ctx.restore();
      }

      // 2b. Active Captions & Emojis
      if (activeGroup && activeGroup.words.length > 0) {
        const baseFontPx = 39;

        // Emoji PNG above active word
        if (activeGroup.emoji && t >= activeGroup.emoji.at) {
          const img = emojiCacheRef.current[activeGroup.emoji.id];
          if (img && img.complete && img.naturalWidth > 0) {
            const elapsed = Math.min(1, (t - activeGroup.emoji.at) / 0.14);
            const pop = elapsed < 0.6 ? 1 + 0.22 * (elapsed / 0.6) : 1.22 - 0.22 * ((elapsed - 0.6) / 0.4);
            const size = 62 * pop;
            ctx.drawImage(img, (W - size) / 2, capY - size - 26, size, size);
          }
        }

        // Measure words
        ctx.save();
        const wordSpecs = activeGroup.words.map((w) => {
          const isActive = t >= w.s && t < w.e;
          const isEmph = Boolean(w.emphasis);
          let scale = 1.0;
          let color = "#FFFFFF";

          if (isActive) {
            color = preset?.captions.active_word.color_hex ?? "#FFD400";
            const dtMs = (t - w.s) * 1000;
            const popDur = preset?.captions.active_word.pop_duration_ms ?? 120;
            const maxPop = (preset?.captions.active_word.pop_scale_pct ?? 115) / 100;
            if (dtMs >= 0 && dtMs <= popDur) {
              const half = popDur / 2;
              scale =
                dtMs <= half
                  ? 1 + (maxPop - 1) * (dtMs / half)
                  : maxPop - (maxPop - 1) * ((dtMs - half) / half);
            }
            if (isEmph) color = preset?.captions.emphasis_word.color_hex ?? "#39FF14";
          } else if (isEmph) {
            color = preset?.captions.emphasis_word.color_hex ?? "#39FF14";
            scale = (preset?.captions.emphasis_word.scale_pct ?? 110) / 100;
          }

          const fontPx = Math.round(baseFontPx * scale);
          const cacheKey = `${fontPx}:${w.w}`;
          let width = wordWidthCacheRef.current.get(cacheKey);
          if (width === undefined) {
            ctx.font = `800 ${fontPx}px "Montserrat ExtraBold", Impact, sans-serif`;
            width = ctx.measureText(w.w).width;
            wordWidthCacheRef.current.set(cacheKey, width);
          }
          return { text: w.w, color, fontPx, width };
        });

        const spaceW = 13;
        const totalW =
          wordSpecs.reduce((acc, ws) => acc + ws.width, 0) +
          Math.max(0, wordSpecs.length - 1) * spaceW;
        let cursorX = (W - totalW) / 2;

        for (const ws of wordSpecs) {
          ctx.font = `800 ${ws.fontPx}px "Montserrat ExtraBold", Impact, sans-serif`;
          ctx.textAlign = "left";
          ctx.textBaseline = "middle";
          ctx.lineJoin = "round";
          ctx.miterLimit = 2;

          ctx.shadowColor = "rgba(0,0,0,0.85)";
          ctx.shadowOffsetX = 0;
          ctx.shadowOffsetY = 4;
          ctx.shadowBlur = 6;
          ctx.lineWidth = 9;
          ctx.strokeStyle = "#000000";
          ctx.strokeText(ws.text, cursorX, capY);

          ctx.shadowBlur = 0;
          ctx.shadowOffsetY = 0;
          ctx.fillStyle = ws.color;
          ctx.fillText(ws.text, cursorX, capY);

          cursorX += ws.width + spaceW;
        }
        ctx.restore();
      }
    },
    [preset, isDraggingCam, isDraggingCaptions]
  );

  // Recalculate camera cover bounds on window resize
  useEffect(() => {
    const onResize = () => {
      renderFrameAt(clipTimeRef.current);
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [renderFrameAt]);

  // Synchronize videos only when drift exceeds 40 ms or on forced seek
  const syncVideosToClipTime = useCallback((t: number, forceSeek: boolean) => {
    const p = planRef.current;
    if (!p) return;
    const { masterTime } = clipToMasterTime(p, t);
    const camTime = Math.max(0, masterTime * syncRef.current.scale + syncRef.current.shift);

    const gv = gameVideoRef.current;
    const cv = camVideoRef.current;

    if (cv && cv.readyState >= 1) {
      if (forceSeek || Math.abs(cv.currentTime - camTime) > 0.04) {
        cv.currentTime = camTime;
      }
    }
    if (gv && gv.readyState >= 1) {
      if (forceSeek || Math.abs(gv.currentTime - masterTime) > 0.04) {
        gv.currentTime = masterTime;
      }
    }
  }, []);

  // 60 fps Animation Loop using Hardware Clock (cv.currentTime as Master)
  useEffect(() => {
    let animId = 0;
    let frameCount = 0;
    let rvfcId: number | null = null;

    const tick = () => {
      frameCount += 1;
      const p = planRef.current;
      const cv = camVideoRef.current;
      const gv = gameVideoRef.current;

      if (p) {
        // Real-time Web Audio sidechain ducking
        const micNode = micGainNodeRef.current;
        const gameNode = gameGainNodeRef.current;
        const analyser = micAnalyserRef.current;
        const pcm = analyserBufRef.current;
        if (micNode) {
          micNode.gain.value = dbToLinear(p.audio.mic_gain_db);
        }
        if (gameNode && analyser && pcm) {
          const hasCleanGame = sessionRef.current?.prepared?.gameplay_clean_audio_stream != null;
          if (playingRef.current && hasCleanGame) {
            analyser.getFloatTimeDomainData(pcm);
            let sumSq = 0;
            for (let i = 0; i < pcm.length; i++) sumSq += pcm[i] * pcm[i];
            const rms = Math.sqrt(sumSq / pcm.length);
            const targetDuck = rms > 0.024 ? dbToLinear(p.audio.duck_game_db) : 1.0;
            const coef = targetDuck < duckEnvRef.current ? 0.28 : 0.06;
            duckEnvRef.current += (targetDuck - duckEnvRef.current) * coef;
            gameNode.gain.value = duckEnvRef.current;
            if (frameCount % 6 === 0) {
              setLiveDuckPct(Math.round((1 - duckEnvRef.current) * 100));
            }
          } else {
            gameNode.gain.value = 0;
            if (frameCount % 15 === 0) setLiveDuckPct(0);
          }
        }
      }

      if (p && playingRef.current && cv && cv.readyState >= 2) {
        // Read directly from hardware video clock
        const camNow = cv.currentTime;
        const masterNow = (camNow - syncRef.current.shift) / (syncRef.current.scale || 1);
        const total = getTotalClipDuration(p);
        const currentClipT = masterToClipTime(p, masterNow);

        // Check if clip loop completed
        if (currentClipT >= total - 0.04 || cv.ended) {
          seekTo(0);
        } else {
          const prevT = clipTimeRef.current;
          clipTimeRef.current = currentClipT;

          // Check SFX cues
          for (const cue of p.audio.sfx) {
            if (prevT < cue.t && currentClipT >= cue.t && currentClipT - prevT < 0.25) {
              fireSfx(cue.id, cue.gain_db);
            }
          }

          // Slave sync for gameplay video only if drift > 40 ms
          if (gv && gv.readyState >= 1) {
            const drift = Math.abs(gv.currentTime - masterNow);
            if (drift > 0.04) {
              gv.currentTime = masterNow;
            }
          }

          // Direct DOM updates (no React render tree cost at 60 fps)
          if (scrubberInputRef.current) {
            scrubberInputRef.current.value = String(currentClipT);
          }
          if (timeLabelRef.current) {
            timeLabelRef.current.textContent = `${currentClipT.toFixed(2)}s / ${total.toFixed(1)}s`;
          }
          if (playheadBarRef.current) {
            playheadBarRef.current.style.left = `${(currentClipT / Math.max(0.1, total)) * 100}%`;
          }

          const now = performance.now();
          if (now - lastReactTimeSyncRef.current >= 120) {
            lastReactTimeSyncRef.current = now;
            setClipTime(currentClipT);
          }
        }
      }

      renderFrameAt(clipTimeRef.current);

      // Support requestVideoFrameCallback if available on browser for perfect frame rate sync
      if (
        cv &&
        "requestVideoFrameCallback" in cv &&
        typeof (cv as HTMLVideoElement & { requestVideoFrameCallback: (cb: () => void) => number })
          .requestVideoFrameCallback === "function"
      ) {
        rvfcId = (
          cv as HTMLVideoElement & { requestVideoFrameCallback: (cb: () => void) => number }
        ).requestVideoFrameCallback(tick);
      } else {
        animId = requestAnimationFrame(tick);
      }
    };

    animId = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(animId);
      if (
        rvfcId !== null &&
        camVideoRef.current &&
        "cancelVideoFrameCallback" in camVideoRef.current
      ) {
        (
          camVideoRef.current as HTMLVideoElement & {
            cancelVideoFrameCallback: (id: number) => void;
          }
        ).cancelVideoFrameCallback(rvfcId);
      }
    };
  }, [fireSfx, renderFrameAt]);

  function togglePlay() {
    const next = !playing;
    setPlaying(next);
    const gv = gameVideoRef.current;
    const cv = camVideoRef.current;
    if (next) {
      ensureWebAudio().catch(() => null);
      syncVideosToClipTime(clipTimeRef.current, true);
      cv?.play().catch(() => null);
      gv?.play().catch(() => null);
    } else {
      cv?.pause();
      gv?.pause();
      setClipTime(clipTimeRef.current);
    }
  }

  function seekTo(newT: number) {
    const total = plan ? getTotalClipDuration(plan) : 0;
    const clamped = Math.max(0, Math.min(total, newT));
    clipTimeRef.current = clamped;
    if (scrubberInputRef.current) scrubberInputRef.current.value = String(clamped);
    if (timeLabelRef.current)
      timeLabelRef.current.textContent = `${clamped.toFixed(2)}s / ${total.toFixed(1)}s`;
    if (playheadBarRef.current)
      playheadBarRef.current.style.left = `${(clamped / Math.max(0.1, total)) * 100}%`;
    setClipTime(clamped);
    syncVideosToClipTime(clamped, true);
    renderFrameAt(clamped);
  }

  // Camera Crop manipulation at playhead
  function applyCropAtPlayhead(
    newCx: number,
    newCy: number,
    newZoom: number,
    options?: { skipHistory?: boolean }
  ) {
    if (!plan) return;
    const t = Number(clipTime.toFixed(2));
    mutatePlan((d) => {
      const idx = d.camera_crop.findIndex((kf) => Math.abs(kf.t - t) < 0.25);
      if (idx >= 0) {
        d.camera_crop[idx].cx = Number(newCx.toFixed(3));
        d.camera_crop[idx].cy = Number(newCy.toFixed(3));
        d.camera_crop[idx].zoom = Number(newZoom.toFixed(3));
      } else {
        d.camera_crop.push({
          t,
          cx: Number(newCx.toFixed(3)),
          cy: Number(newCy.toFixed(3)),
          zoom: Number(newZoom.toFixed(3)),
          ease: "inOutSine",
        });
        d.camera_crop.sort((a, b) => a.t - b.t);
      }
      return d;
    }, options);
  }

  // Pointer drag for Camera WYSIWYG
  const handleCamPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!plan) return;
    const cur = evaluateCameraCrop(plan.camera_crop, clipTime);
    dragCamStartRef.current = {
      clientX: e.clientX,
      clientY: e.clientY,
      cx: cur.cx,
      cy: cur.cy,
      zoom: cur.zoom,
      initialPlan: structuredClone(plan),
    };
    setIsDraggingCam(true);
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      // Ignorar si el navegador restringe pointer capture
    }
  };

  const handleCamPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDraggingCam || !dragCamStartRef.current || !plan) return;
    const wrapEl = camWrapRef.current;
    const videoEl = camVideoRef.current;
    if (!wrapEl || !videoEl) return;

    const boxW = wrapEl.clientWidth || 330;
    const boxH = wrapEl.clientHeight || 235;
    const vw = videoEl.videoWidth > 0 ? videoEl.videoWidth : 1920;
    const vh = videoEl.videoHeight > 0 ? videoEl.videoHeight : 1080;

    const baseScale = Math.max(boxW / vw, boxH / vh);
    const totalScale = baseScale * Math.max(1.0, dragCamStartRef.current.zoom);
    const scaledW = vw * totalScale;
    const scaledH = vh * totalScale;

    const dx = e.clientX - dragCamStartRef.current.clientX;
    const dy = e.clientY - dragCamStartRef.current.clientY;

    // Arrastre 1:1 de la imagen: mover el ratón hacia la derecha mueve la imagen a la derecha
    let newCx = dragCamStartRef.current.cx - dx / scaledW;
    let newCy = dragCamStartRef.current.cy - dy / scaledH;

    newCx = Math.max(0.0, Math.min(1.0, newCx));
    newCy = Math.max(0.0, Math.min(1.0, newCy));

    // Guía magnética de centrado en X = 0.50
    let snapping = false;
    if (Math.abs(newCx - 0.5) < 0.02) {
      newCx = 0.5;
      snapping = true;
    }
    setIsSnappingCenterX(snapping);

    applyCropAtPlayhead(newCx, newCy, dragCamStartRef.current.zoom, { skipHistory: true });
    renderFrameAt(clipTime);
  };

  const handleCamPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    const startData = dragCamStartRef.current;
    if (isDraggingCam && startData && plan) {
      const initialPlan = startData.initialPlan;
      setUndoStack((s) => [...s.slice(-30), initialPlan]);
      setRedoStack([]);
      setDirty(true);
      dragCamStartRef.current = null;
      setIsDraggingCam(false);
      setIsSnappingCenterX(false);
    }
    try {
      if (e.currentTarget.hasPointerCapture(e.pointerId)) {
        e.currentTarget.releasePointerCapture(e.pointerId);
      }
    } catch {
      // Ignorar si el puntero se liberó
    }
  };

  // Wheel zoom over camera panel
  const handleCamWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (!plan) return;
    const cur = evaluateCameraCrop(plan.camera_crop, clipTime);
    const delta = -e.deltaY * 0.0015;
    const nextZoom = Math.max(1.0, Math.min(2.5, Number((cur.zoom + delta).toFixed(3))));
    applyCropAtPlayhead(cur.cx, cur.cy, nextZoom);
  };

  // Pointer drag for Subtitles Height Positioner
  const handleCapPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!plan) return;
    const curRatio =
      plan.captions.vertical_ratio ?? preset?.captions.gameplay_top_third_ratio ?? 0.28;
    dragCapStartRef.current = {
      clientY: e.clientY,
      initialRatio: curRatio,
      initialPlan: structuredClone(plan),
    };
    setIsDraggingCaptions(true);
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      // Ignorar
    }
  };

  const handleCapPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDraggingCaptions || !dragCapStartRef.current || !plan) return;
    const gameWrap = gameWrapRef.current;
    if (!gameWrap) return;
    const rect = gameWrap.getBoundingClientRect();
    const relY = e.clientY - rect.top;
    const nextRatio = Math.max(0.08, Math.min(0.92, relY / Math.max(1, rect.height)));
    const rounded = Number(nextRatio.toFixed(3));

    mutatePlan(
      (d) => {
        d.captions.vertical_ratio = rounded;
        return d;
      },
      { skipHistory: true }
    );
    if (preset) {
      preset.captions.gameplay_top_third_ratio = rounded;
    }
    renderFrameAt(clipTime);
  };

  const handleCapPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    const startData = dragCapStartRef.current;
    if (isDraggingCaptions && startData) {
      const initialPlan = startData.initialPlan;
      setUndoStack((s) => [...s.slice(-30), initialPlan]);
      setRedoStack([]);
      setDirty(true);
      dragCapStartRef.current = null;
      setIsDraggingCaptions(false);
    }
    try {
      if (e.currentTarget.hasPointerCapture(e.pointerId)) {
        e.currentTarget.releasePointerCapture(e.pointerId);
      }
    } catch {
      // Ignorar si el puntero se liberó
    }
  };

  // Layout Templates (1-Click Presets)
  function applyLayoutTemplate(
    template: "classic_gaming" | "gameplay_priority" | "reaction_full" | "gameplay_full"
  ) {
    if (!plan) return;
    const t = Number(clipTime.toFixed(2));
    const total = getTotalClipDuration(plan);

    mutatePlan((d) => {
      if (template === "classic_gaming") {
        const splitEv = d.layout.find((l) => l.kind === "split");
        if (splitEv) {
          splitEv.camera_ratio = 0.4;
        } else {
          d.layout.unshift({ t: 0, kind: "split", camera_ratio: 0.4 });
        }
      } else if (template === "gameplay_priority") {
        const splitEv = d.layout.find((l) => l.kind === "split");
        if (splitEv) {
          splitEv.camera_ratio = 0.25;
        } else {
          d.layout.unshift({ t: 0, kind: "split", camera_ratio: 0.25 });
        }
      } else if (template === "reaction_full") {
        const until = Number(Math.min(total, t + 2.0).toFixed(2));
        d.layout.push({ t, kind: "camera_full", until });
        d.layout.sort((a, b) => a.t - b.t);
      } else if (template === "gameplay_full") {
        const until = Number(Math.min(total, t + 2.5).toFixed(2));
        d.layout.push({ t, kind: "gameplay_full", until });
        d.layout.sort((a, b) => a.t - b.t);
      }
      return d;
    });
    setStatusMsg(`Plantilla aplicada con éxito.`);
  }

  async function handleSave(): Promise<EditPlan | null> {
    if (!plan) return null;
    setSaving(true);
    setError(null);
    try {
      const res = await saveClipEditPlan(clipId, plan);
      setClip(res.clip);
      setPlan(res.editplan);
      setDirty(false);
      setStatusMsg("Cambios guardados al instante.");
      return res.editplan;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      return null;
    } finally {
      setSaving(false);
    }
  }

  async function handleRender(quality: "draft" | "final") {
    if (!plan) return;
    setError(null);
    setRenderingQuality(quality);
    setRenderProgress(0.02);
    try {
      if (dirty) {
        await saveClipEditPlan(clipId, plan);
        setDirty(false);
      }
      const res = await renderClip(clipId, quality, quality === "final");
      setClip(res.clip);
      setStatusMsg(
        quality === "final"
          ? "Video final en alta definición (1080p) listo para descargar."
          : "Vista previa rápida lista."
      );
      setPreviewSource("rendered");
      setPlaying(false);
      gameVideoRef.current?.pause();
      camVideoRef.current?.pause();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRenderingQuality(null);
      setRenderProgress(null);
    }
  }

  function addImpactZoomAtPlayhead() {
    if (!plan) return;
    const total = getTotalClipDuration(plan);
    const t0 = Number(Math.max(0, Math.min(total - 0.8, clipTime)).toFixed(3));
    const base = evaluateCameraCrop(plan.camera_crop, t0);
    const kfs: CropKeyframe[] = [
      { t: t0, cx: base.cx, cy: base.cy, zoom: Number(base.zoom.toFixed(3)), ease: "linear" },
      {
        t: Number(Math.min(total, t0 + 0.14).toFixed(3)),
        cx: base.cx,
        cy: base.cy,
        zoom: Number(Math.min(2.5, base.zoom * 1.25).toFixed(3)),
        ease: "outBack",
      },
      {
        t: Number(Math.min(total, t0 + 0.54).toFixed(3)),
        cx: base.cx,
        cy: base.cy,
        zoom: Number(Math.min(2.5, base.zoom * 1.25).toFixed(3)),
        ease: "linear",
      },
      {
        t: Number(Math.min(total, t0 + 0.79).toFixed(3)),
        cx: base.cx,
        cy: base.cy,
        zoom: Number(base.zoom.toFixed(3)),
        ease: "inOutSine",
      },
    ];
    mutatePlan((d) => {
      const filtered = d.camera_crop.filter((k) => k.t < t0 - 0.05 || k.t > t0 + 0.85);
      d.camera_crop = [...filtered, ...kfs].sort((a, b) => a.t - b.t);
      return d;
    });
  }

  if (!clip || !session || !plan) {
    return (
      <div className="flex items-center justify-center py-24 text-zinc-400">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Abriendo el editor interactivo de tu clip…
      </div>
    );
  }

  const totalDur = getTotalClipDuration(plan);
  const curCrop = evaluateCameraCrop(plan.camera_crop, clipTime);
  const curCapRatio =
    plan.captions.vertical_ratio ?? preset?.captions.gameplay_top_third_ratio ?? 0.28;
  const renderedUrl = clip.has_final
    ? `${API_PREFIX}/clips/${clip.id}/file?quality=final&t=${Math.floor(clip.updated_at)}`
    : clip.has_draft
      ? `${API_PREFIX}/clips/${clip.id}/file?quality=draft&t=${Math.floor(clip.updated_at)}`
      : null;

  return (
    <div className="space-y-5">
      {/* Studio Header: Save, Undo/Redo & Export */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-zinc-800 bg-[#0E1017] px-5 py-3.5">
        <div className="flex items-center gap-3">
          <Link
            href={`/sessions/${session.id}`}
            className="inline-flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-950 px-2.5 py-1.5 text-xs text-zinc-300 hover:text-white"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Volver a la sesión
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-extrabold text-white">{clip.overlay_title}</h1>
              <span className="rounded bg-[#FFD400]/15 px-2 py-0.5 font-mono text-[11px] font-bold text-[#FFD400]">
                Nota {clip.final_score.toFixed(0)}/100
              </span>
              {dirty && (
                <span className="rounded bg-amber-500/20 px-2 py-0.5 text-[10px] font-semibold text-amber-300">
                  Cambios sin guardar
                </span>
              )}
            </div>
            <p className="text-[11px] text-zinc-400">
              Edición visual interactiva en tiempo real · 60 fps · Duración:{" "}
              <strong>{totalDur.toFixed(1)} s</strong>
              {statusMsg ? ` · ${statusMsg}` : ""}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Undo / Redo buttons */}
          <div className="mr-1 flex items-center rounded-xl border border-zinc-800 bg-zinc-950 p-0.5">
            <button
              type="button"
              onClick={handleUndo}
              disabled={undoStack.length === 0}
              title="Deshacer cambio (Ctrl+Z)"
              className="rounded-lg p-2 text-zinc-300 hover:bg-zinc-800 hover:text-white disabled:opacity-25"
            >
              <Undo2 className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={handleRedo}
              disabled={redoStack.length === 0}
              title="Rehacer cambio (Ctrl+Y)"
              className="rounded-lg p-2 text-zinc-300 hover:bg-zinc-800 hover:text-white disabled:opacity-25"
            >
              <Redo2 className="h-4 w-4" />
            </button>
          </div>

          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-700 bg-zinc-900 px-3.5 py-2 text-xs font-bold text-white hover:bg-zinc-800 disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
            Guardar cambios
          </button>

          <button
            type="button"
            onClick={() => handleRender("draft")}
            disabled={renderingQuality !== null}
            className="inline-flex items-center gap-1.5 rounded-xl border border-[#39FF14]/40 bg-[#39FF14]/10 px-3.5 py-2 text-xs font-bold text-[#39FF14] hover:bg-[#39FF14]/20 disabled:opacity-50"
          >
            {renderingQuality === "draft" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Zap className="h-3.5 w-3.5" />
            )}
            Prueba rápida
          </button>

          <button
            type="button"
            onClick={() => handleRender("final")}
            disabled={renderingQuality !== null}
            className="inline-flex items-center gap-1.5 rounded-xl bg-[#FFD400] px-4 py-2 text-xs font-extrabold text-black shadow hover:bg-amber-300 disabled:opacity-50"
          >
            {renderingQuality === "final" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Film className="h-3.5 w-3.5" />
            )}
            Exportar video final (1080p)
          </button>
        </div>
      </div>

      {renderProgress !== null && (
        <div className="rounded-xl border border-[#FFD400]/30 bg-[#FFD400]/10 px-4 py-2.5 text-xs text-[#FFD400]">
          <div className="flex justify-between font-bold">
            <span>
              Creando tu archivo de video (
              {renderingQuality === "draft" ? "prueba rápida" : "alta calidad 1080p"})…
            </span>
            <span>{Math.round(renderProgress * 100)}%</span>
          </div>
          <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-zinc-900">
            <div
              className="h-full bg-[#FFD400] transition-all"
              style={{ width: `${Math.max(3, Math.round(renderProgress * 100))}%` }}
            />
          </div>
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      )}

      {/* Main Studio Grid: Left = 9:16 WYSIWYG Stage, Right = Inspector Tabs */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left Column: Vertical 9:16 Interactive Stage */}
        <div className="flex flex-col items-center rounded-2xl border border-zinc-800 bg-[#0E1017] p-4 lg:col-span-5">
          <div className="mb-3 flex w-full items-center justify-between">
            <div className="inline-flex rounded-lg border border-zinc-800 bg-zinc-950 p-0.5 text-xs">
              <button
                type="button"
                onClick={() => setPreviewSource("live")}
                className={`rounded-md px-3 py-1 font-semibold transition ${
                  previewSource === "live"
                    ? "bg-[#FFD400] text-black"
                    : "text-zinc-400 hover:text-white"
                }`}
              >
                Vista interactiva en vivo
              </button>
              {renderedUrl && (
                <button
                  type="button"
                  onClick={() => {
                    setPlaying(false);
                    gameVideoRef.current?.pause();
                    camVideoRef.current?.pause();
                    setPreviewSource("rendered");
                  }}
                  className={`rounded-md px-3 py-1 font-semibold transition ${
                    previewSource === "rendered"
                      ? "bg-[#39FF14] text-black"
                      : "text-zinc-400 hover:text-white"
                  }`}
                >
                  Video exportado (MP4)
                </button>
              )}
            </div>

            {renderedUrl && (
              <a
                href={`${API_PREFIX}/clips/${clip.id}/file?quality=final&download=true`}
                className="inline-flex items-center gap-1 text-xs font-semibold text-zinc-300 hover:text-[#FFD400]"
              >
                <Download className="h-3.5 w-3.5" /> Descargar MP4
              </a>
            )}
          </div>

          {/* 9:16 Viewport with Interactive WYSIWYG Overlays */}
          <div
            className="group relative aspect-[9/16] w-full max-w-[330px] overflow-hidden rounded-2xl border border-zinc-700/80 bg-black shadow-2xl select-none"
            style={{ willChange: "transform", transform: "translateZ(0)" }}
          >
            {previewSource === "live" ? (
              <>
                {/* Top Section: Camera Streamer with Drag & Drop Crop */}
                <div
                  ref={camWrapRef}
                  onPointerDown={handleCamPointerDown}
                  onPointerMove={handleCamPointerMove}
                  onPointerUp={handleCamPointerUp}
                  onPointerCancel={handleCamPointerUp}
                  onWheel={handleCamWheel}
                  title="Arrastra para encuadrar tu rostro · Rueda del ratón para ajustar Zoom"
                  className={`relative h-[40%] w-full overflow-hidden bg-zinc-950 touch-none ${
                    isDraggingCam ? "cursor-grabbing" : "cursor-grab"
                  }`}
                  style={{ willChange: "transform", transform: "translateZ(0)" }}
                >
                  <video
                    ref={camVideoRef}
                    src={`${API_PREFIX}/sessions/${session.id}/stream/camera`}
                    crossOrigin="anonymous"
                    playsInline
                    preload="auto"
                    onLoadedMetadata={() => renderFrameAt(clipTimeRef.current)}
                    className="absolute pointer-events-none will-change-transform"
                    style={{ willChange: "transform", transform: "translateZ(0)" }}
                  />

                  {/* Visual Drag Hint & Zoom Floating Widget */}
                  <div className="absolute top-2 left-2 z-20 flex items-center gap-1.5 rounded-md bg-black/75 px-2 py-0.5 text-[10px] font-bold text-zinc-200 border border-zinc-700/80 backdrop-blur-sm pointer-events-none transition opacity-75 group-hover:opacity-100">
                    <Move className="h-3 w-3 text-[#FFD400]" />
                    <span>Cámara</span>
                  </div>

                  <div className="absolute top-2 right-2 z-20 flex items-center gap-1 rounded-lg bg-black/80 px-1.5 py-0.5 text-[10px] border border-zinc-700/80 backdrop-blur-sm">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        applyCropAtPlayhead(
                          curCrop.cx,
                          curCrop.cy,
                          Math.max(1.0, curCrop.zoom - 0.1)
                        );
                      }}
                      title="Reducir zoom"
                      className="p-1 text-zinc-300 hover:text-white"
                    >
                      <ZoomOut className="h-3 w-3" />
                    </button>
                    <span className="font-mono text-[10px] font-bold text-[#FFD400]">
                      {curCrop.zoom.toFixed(2)}x
                    </span>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        applyCropAtPlayhead(
                          curCrop.cx,
                          curCrop.cy,
                          Math.min(2.5, curCrop.zoom + 0.1)
                        );
                      }}
                      title="Aumentar zoom"
                      className="p-1 text-zinc-300 hover:text-white"
                    >
                      <ZoomIn className="h-3 w-3" />
                    </button>
                  </div>

                  {/* Magnetic Snapping Vertical Center Guide */}
                  {isSnappingCenterX && (
                    <div className="pointer-events-none absolute inset-y-0 left-1/2 w-[2px] -translate-x-1/2 bg-amber-400 shadow-[0_0_10px_rgba(251,191,36,0.9)] z-30">
                      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 rounded bg-amber-500 px-1.5 py-0.5 text-[9px] font-black text-black">
                        CENTRO
                      </div>
                    </div>
                  )}
                </div>

                {/* Bottom Section: Gameplay with Subtitles Vertical Positioner */}
                <div
                  ref={gameWrapRef}
                  className="relative h-[60%] w-full overflow-hidden bg-black"
                  style={{ willChange: "transform", transform: "translateZ(0)" }}
                >
                  <video
                    ref={gameVideoRef}
                    src={`${API_PREFIX}/sessions/${session.id}/stream/gameplay`}
                    crossOrigin="anonymous"
                    playsInline
                    muted
                    preload="auto"
                    className="h-full w-full object-cover pointer-events-none"
                    style={{ willChange: "transform", transform: "translateZ(0)" }}
                  />

                  {/* Interactive Subtitles Drag Handle */}
                  <div
                    onPointerDown={handleCapPointerDown}
                    onPointerMove={handleCapPointerMove}
                    onPointerUp={handleCapPointerUp}
                    onPointerCancel={handleCapPointerUp}
                    title="Arrastra verticalmente para mover la altura de los subtítulos y no tapar la mira del juego"
                    className="absolute inset-x-0 z-20 flex flex-col items-center cursor-ns-resize touch-none transition"
                    style={{ top: `${(curCapRatio * 100).toFixed(1)}%`, transform: "translateY(-50%)" }}
                  >
                    <div className="w-full border-t border-dashed border-[#FFD400]/40 shadow-sm" />
                    <div
                      className={`my-1 inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[10px] font-extrabold shadow-lg backdrop-blur-md transition ${
                        isDraggingCaptions
                          ? "bg-[#FFD400] text-black ring-2 ring-amber-300"
                          : "bg-black/80 text-[#FFD400] border border-[#FFD400]/60 hover:bg-black/95"
                      }`}
                    >
                      <Move className="h-2.5 w-2.5" />
                      <span>Subtítulos ({Math.round(curCapRatio * 100)}%)</span>
                    </div>
                    <div className="w-full border-b border-dashed border-[#FFD400]/40 shadow-sm" />
                  </div>
                </div>

                {/* 60fps Canvas for Hormozi Captions, Emojis, and Seam Title */}
                <canvas
                  ref={canvasRef}
                  width={540}
                  height={960}
                  onClick={togglePlay}
                  className="pointer-events-none absolute inset-0 h-full w-full"
                />
              </>
            ) : (
              renderedUrl && (
                <video src={renderedUrl} controls autoPlay className="h-full w-full object-contain" />
              )
            )}
          </div>

          {/* Scrubber & Timeline Controls */}
          {previewSource === "live" && (
            <div className="mt-4 w-full space-y-2">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={togglePlay}
                  title="Reproducir / Pausar (Barra espaciadora)"
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-[#FFD400] text-black hover:bg-amber-300 shadow-md"
                >
                  {playing ? (
                    <Pause className="h-4 w-4 fill-black" />
                  ) : (
                    <Play className="h-4 w-4 fill-black" />
                  )}
                </button>
                <input
                  ref={scrubberInputRef}
                  type="range"
                  min={0}
                  max={Math.max(0.1, totalDur)}
                  step={0.02}
                  defaultValue={clipTime}
                  onChange={(e) => seekTo(parseFloat(e.target.value))}
                  className="h-2 flex-1 cursor-pointer accent-[#FFD400]"
                />
                <span ref={timeLabelRef} className="w-24 text-right font-mono text-xs text-zinc-300">
                  {clipTime.toFixed(2)}s / {totalDur.toFixed(1)}s
                </span>
              </div>

              {/* Visual Markers Bar */}
              <div className="relative h-5 w-full overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950">
                {/* camera_full blocks */}
                {plan.layout
                  .filter((ev) => ev.kind === "camera_full")
                  .map((ev, i) => {
                    const left = (ev.t / Math.max(0.1, totalDur)) * 100;
                    const width = (((ev.until ?? ev.t + 2) - ev.t) / Math.max(0.1, totalDur)) * 100;
                    return (
                      <div
                        key={i}
                        style={{ left: `${left}%`, width: `${width}%` }}
                        className="absolute inset-y-0 bg-purple-500/35"
                        title={`Cámara completa (${ev.t}s - ${ev.until}s)`}
                      />
                    );
                  })}
                {/* Impact zoom ticks */}
                {plan.camera_crop
                  .filter((kf) => kf.ease === "outBack")
                  .map((kf, i) => (
                    <div
                      key={i}
                      style={{ left: `${(kf.t / Math.max(0.1, totalDur)) * 100}%` }}
                      className="absolute inset-y-0 w-1 bg-[#39FF14]"
                      title={`Zoom ${kf.zoom}x @ ${kf.t}s`}
                    />
                  ))}
                {/* Playhead */}
                <div
                  ref={playheadBarRef}
                  style={{ left: `${(clipTime / Math.max(0.1, totalDur)) * 100}%` }}
                  className="absolute inset-y-0 w-0.5 bg-[#FFD400]"
                />
              </div>
              <div className="flex justify-between text-[10px] text-zinc-500">
                <span>Verde: Zoom de reacción</span>
                <span>Morado: Tu cámara en pantalla completa</span>
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Declarative EditPlan v2 Inspector & Layout Templates */}
        <div className="flex flex-col rounded-2xl border border-zinc-800 bg-[#0E1017] p-5 lg:col-span-7">
          <div className="mb-4 flex flex-wrap gap-1.5 border-b border-zinc-800 pb-3 text-xs font-bold">
            <button
              type="button"
              onClick={() => setActiveTab("captions")}
              className={`inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 transition ${
                activeTab === "captions"
                  ? "bg-[#FFD400] text-black"
                  : "bg-zinc-900 text-zinc-300 hover:text-white"
              }`}
            >
              <Type className="h-3.5 w-3.5" /> Subtítulos y Emojis ({plan.captions.groups.length})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("camera")}
              className={`inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 transition ${
                activeTab === "camera"
                  ? "bg-[#FFD400] text-black"
                  : "bg-zinc-900 text-zinc-300 hover:text-white"
              }`}
            >
              <Camera className="h-3.5 w-3.5" /> Disposición y Cámara
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("cuts")}
              className={`inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 transition ${
                activeTab === "cuts"
                  ? "bg-[#FFD400] text-black"
                  : "bg-zinc-900 text-zinc-300 hover:text-white"
              }`}
            >
              <Scissors className="h-3.5 w-3.5" /> Mezclador de Sonido y Ritmo
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("json")}
              className={`inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 transition ${
                activeTab === "json"
                  ? "bg-[#FFD400] text-black"
                  : "bg-zinc-900 text-zinc-300 hover:text-white"
              }`}
            >
              Datos avanzados
            </button>
          </div>

          {/* TAB 1: CAPTIONS & EMOJIS */}
          {activeTab === "captions" && (
            <div className="max-h-[580px] space-y-2.5 overflow-y-auto pr-1">
              <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-3 text-xs text-zinc-400">
                <span className="font-bold text-zinc-200">Consejo visual: </span>
                Puedes arrastrar el tirador horizontal amarillo en el visor para subir o bajar los
                subtítulos según el HUD de tu juego.
              </div>

              {plan.captions.groups.map((grp, gIdx) => {
                const gs = grp.words[0]?.s ?? 0;
                const ge = grp.words[grp.words.length - 1]?.e ?? 0;
                const isCurrent = clipTime >= gs && clipTime <= ge;

                return (
                  <div
                    key={gIdx}
                    className={`rounded-xl border p-3 transition ${
                      isCurrent
                        ? "border-[#FFD400]/60 bg-[#FFD400]/5"
                        : "border-zinc-800/90 bg-zinc-950/60"
                    }`}
                  >
                    <div className="mb-2 flex items-center justify-between text-[11px]">
                      <button
                        type="button"
                        onClick={() => seekTo(gs + 0.02)}
                        className="font-mono font-semibold text-[#FFD400] hover:underline"
                      >
                        ▶ {gs.toFixed(2)}s – {ge.toFixed(2)}s
                      </button>

                      <button
                        type="button"
                        onClick={() =>
                          setOpenEmojiPickerIdx(openEmojiPickerIdx === gIdx ? null : gIdx)
                        }
                        className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-800 bg-zinc-900 px-2.5 py-1 text-[11px] font-semibold text-zinc-200 hover:border-[#FFD400]"
                      >
                        {grp.emoji?.id ? (
                          <>
                            <img
                              src={`${API_PREFIX}/emojis/${encodeURIComponent(grp.emoji.id)}.png`}
                              alt={grp.emoji.id}
                              className="h-4 w-4 object-contain"
                            />
                            <span>
                              {emojiCatalog.find((x) => x.id === grp.emoji?.id)?.name ??
                                grp.emoji.id}
                            </span>
                          </>
                        ) : (
                          <span className="text-zinc-400">+ Agregar emoji</span>
                        )}
                      </button>
                    </div>

                    {openEmojiPickerIdx === gIdx && (
                      <div className="mb-2.5 rounded-xl border border-zinc-700 bg-zinc-950 p-2.5">
                        <div className="mb-2 flex flex-wrap items-center justify-between gap-1 text-[10px]">
                          <div className="flex flex-wrap gap-1">
                            {[
                              { k: "all", lbl: "Todos" },
                              { k: "hype", lbl: "Hype" },
                              { k: "reaccion", lbl: "Reacción" },
                              { k: "humor", lbl: "Humor" },
                              { k: "gaming", lbl: "Gaming" },
                            ].map((cat) => (
                              <button
                                key={cat.k}
                                type="button"
                                onClick={() => setEmojiCategoryFilter(cat.k)}
                                className={`rounded px-2 py-0.5 font-bold ${
                                  emojiCategoryFilter === cat.k
                                    ? "bg-[#FFD400] text-black"
                                    : "bg-zinc-900 text-zinc-400 hover:text-white"
                                }`}
                              >
                                {cat.lbl}
                              </button>
                            ))}
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              mutatePlan((d) => {
                                d.captions.groups[gIdx].emoji = null;
                                return d;
                              });
                              setOpenEmojiPickerIdx(null);
                            }}
                            className="rounded bg-red-500/15 px-2 py-0.5 font-bold text-red-300 hover:bg-red-500/25"
                          >
                            Quitar emoji
                          </button>
                        </div>
                        <div className="grid max-h-40 grid-cols-7 gap-1.5 overflow-y-auto sm:grid-cols-10">
                          {emojiCatalog
                            .filter(
                              (em) => emojiCategoryFilter === "all" || em.category === emojiCategoryFilter
                            )
                            .map((em) => (
                              <button
                                key={em.id}
                                type="button"
                                title={`${em.char} ${em.name}`}
                                onClick={() => {
                                  mutatePlan((d) => {
                                    const target = d.captions.groups[gIdx];
                                    target.emoji = { id: em.id, at: target.words[0]?.s ?? gs };
                                    return d;
                                  });
                                  setOpenEmojiPickerIdx(null);
                                }}
                                className={`flex flex-col items-center justify-center rounded-lg border p-1.5 transition hover:border-[#FFD400] hover:bg-zinc-900 ${
                                  grp.emoji?.id === em.id
                                    ? "border-[#FFD400] bg-[#FFD400]/15"
                                    : "border-zinc-800/80 bg-zinc-900/40"
                                }`}
                              >
                                <img
                                  src={`${API_PREFIX}${em.url}`}
                                  alt={em.name}
                                  className="h-6 w-6 object-contain"
                                />
                              </button>
                            ))}
                        </div>
                      </div>
                    )}

                    <div className="flex flex-wrap gap-2">
                      {grp.words.map((w, wIdx) => (
                        <div
                          key={wIdx}
                          className="flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-900 px-2 py-1"
                        >
                          <input
                            type="text"
                            value={w.w}
                            onChange={(e) => {
                              const txt = e.target.value;
                              mutatePlan((d) => {
                                d.captions.groups[gIdx].words[wIdx].w = txt;
                                return d;
                              });
                            }}
                            className="w-24 bg-transparent font-extrabold text-xs text-white focus:outline-none"
                          />
                          <button
                            type="button"
                            onClick={() =>
                              mutatePlan((d) => {
                                const cur = d.captions.groups[gIdx].words[wIdx];
                                cur.emphasis = !cur.emphasis;
                                return d;
                              })
                            }
                            title="Resaltar esta palabra en verde"
                            className={`rounded px-1.5 py-0.5 text-[10px] font-bold transition ${
                              w.emphasis
                                ? "bg-[#39FF14] text-black"
                                : "bg-zinc-800 text-zinc-400 hover:text-white"
                            }`}
                          >
                            <Sparkles className="inline h-3 w-3" />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* TAB 2: CAMERA & LAYOUT TEMPLATES */}
          {activeTab === "camera" && (
            <div className="max-h-[580px] space-y-5 overflow-y-auto pr-1">
              {/* Module 2: Quick Layout Templates */}
              <div>
                <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-zinc-400">
                  Plantillas Rápidas de Disposición (1 Clic)
                </h3>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <button
                    type="button"
                    onClick={() => applyLayoutTemplate("classic_gaming")}
                    className="flex flex-col items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-3 text-center transition hover:border-[#FFD400] hover:bg-zinc-900"
                  >
                    <Layers className="mb-1.5 h-5 w-5 text-[#FFD400]" />
                    <span className="text-xs font-bold text-white">Clásico Gaming</span>
                    <span className="text-[10px] text-zinc-400">40% Cámara / 60% Juego</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => applyLayoutTemplate("gameplay_priority")}
                    className="flex flex-col items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-3 text-center transition hover:border-[#FFD400] hover:bg-zinc-900"
                  >
                    <Crosshair className="mb-1.5 h-5 w-5 text-emerald-400" />
                    <span className="text-xs font-bold text-white">Gameplay Prioritario</span>
                    <span className="text-[10px] text-zinc-400">25% Cámara / 75% Juego</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => applyLayoutTemplate("reaction_full")}
                    className="flex flex-col items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-3 text-center transition hover:border-[#FFD400] hover:bg-zinc-900"
                  >
                    <Maximize2 className="mb-1.5 h-5 w-5 text-purple-400" />
                    <span className="text-xs font-bold text-white">Reacción Total</span>
                    <span className="text-[10px] text-zinc-400">100% Cámara (2s)</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => applyLayoutTemplate("gameplay_full")}
                    className="flex flex-col items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-3 text-center transition hover:border-[#FFD400] hover:bg-zinc-900"
                  >
                    <Film className="mb-1.5 h-5 w-5 text-blue-400" />
                    <span className="text-xs font-bold text-white">Juego Completo</span>
                    <span className="text-[10px] text-zinc-400">100% Gameplay</span>
                  </button>
                </div>
              </div>

              {/* Action buttons at playhead */}
              <div>
                <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-zinc-400">
                  Efectos de Reacción en el Segundo Actual ({clipTime.toFixed(1)}s)
                </h3>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={addImpactZoomAtPlayhead}
                    className="inline-flex items-center gap-1.5 rounded-xl bg-[#39FF14]/15 px-3.5 py-2 text-xs font-bold text-[#39FF14] ring-1 ring-[#39FF14]/40 hover:bg-[#39FF14]/25"
                  >
                    <Plus className="h-3.5 w-3.5" /> Acercar cámara aquí ({clipTime.toFixed(1)}s)
                  </button>
                  <button
                    type="button"
                    onClick={() => applyLayoutTemplate("reaction_full")}
                    className="inline-flex items-center gap-1.5 rounded-xl bg-purple-500/15 px-3.5 py-2 text-xs font-bold text-purple-300 ring-1 ring-purple-500/40 hover:bg-purple-500/25"
                  >
                    <Maximize2 className="h-3.5 w-3.5" /> Cámara completa 2s aquí
                  </button>
                </div>
              </div>

              {/* Active Layout overrides list */}
              <div className="space-y-2">
                <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400">
                  Secuencia de Disposición ({plan.layout.length})
                </h3>
                {plan.layout.map((ev, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between rounded-xl border border-zinc-800 bg-zinc-950/70 px-3 py-2 text-xs"
                  >
                    <span className="text-zinc-200">
                      <strong>
                        {ev.kind === "camera_full"
                          ? "Cámara a pantalla completa"
                          : ev.kind === "gameplay_full"
                            ? "Juego a pantalla completa"
                            : `Pantalla dividida (${Math.round((ev.camera_ratio ?? 0.4) * 100)}% Cámara / ${Math.round((1 - (ev.camera_ratio ?? 0.4)) * 100)}% Juego)`}
                      </strong>{" "}
                      · desde {ev.t.toFixed(1)}s
                      {ev.until != null ? ` hasta ${ev.until.toFixed(1)}s` : ""}
                    </span>
                    {ev.kind !== "split" && (
                      <button
                        type="button"
                        onClick={() =>
                          mutatePlan((d) => {
                            d.layout.splice(idx, 1);
                            return d;
                          })
                        }
                        className="text-red-400 hover:text-red-300"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                ))}
              </div>

              {/* Camera Crop Keyframes list */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400">
                    Puntos de encuadre ({plan.camera_crop.length})
                  </h3>
                  <span className="text-[11px] text-zinc-500">
                    Arrastra directamente en el visor para mover
                  </span>
                </div>
                {plan.camera_crop.map((kf, idx) => (
                  <div
                    key={idx}
                    className="grid grid-cols-12 items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-950/70 p-2.5 text-xs"
                  >
                    <button
                      type="button"
                      onClick={() => seekTo(kf.t)}
                      className="col-span-2 text-left font-mono font-bold text-[#FFD400]"
                    >
                      {kf.t.toFixed(2)}s
                    </button>
                    <div className="col-span-3 text-[11px] text-zinc-300">
                      Centro: <strong>{(kf.cx * 100).toFixed(0)}%</strong>
                    </div>
                    <div className="col-span-3 text-[11px] text-zinc-300">
                      Zoom: <strong>{kf.zoom.toFixed(2)}x</strong>
                    </div>
                    <select
                      value={kf.ease ?? "linear"}
                      onChange={(e) =>
                        mutatePlan((d) => {
                          d.camera_crop[idx].ease = e.target.value as EaseKind;
                          return d;
                        })
                      }
                      className="col-span-3 rounded border border-zinc-800 bg-zinc-900 px-1.5 py-1 text-[11px] text-zinc-200"
                    >
                      <option value="linear">Directo</option>
                      <option value="outBack">Impacto rápido</option>
                      <option value="inOutSine">Suave</option>
                      <option value="outCubic">Natural</option>
                    </select>
                    <button
                      type="button"
                      disabled={plan.camera_crop.length <= 1}
                      onClick={() =>
                        mutatePlan((d) => {
                          d.camera_crop.splice(idx, 1);
                          return d;
                        })
                      }
                      className="col-span-1 flex justify-end text-zinc-500 hover:text-red-400 disabled:opacity-20"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB 3: SIMPLIFIED AUDIO MIXER, OVERLAY TITLE & JUMP CUTS */}
          {activeTab === "cuts" && (
            <div className="space-y-5">
              {/* Overlay Title */}
              <div>
                <label className="mb-1 block text-xs font-bold text-zinc-300">
                  Título llamativo inicial (se muestra los primeros 3 segundos)
                </label>
                <input
                  type="text"
                  value={plan.overlays[0]?.text ?? ""}
                  onChange={(e) => {
                    const txt = e.target.value;
                    mutatePlan((d) => {
                      if (d.overlays.length === 0) {
                        d.overlays = [{ kind: "title", text: txt, start: 0, end: 3.0 }];
                      } else {
                        d.overlays[0].text = txt;
                      }
                      return d;
                    });
                  }}
                  className="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3.5 py-2 text-sm font-bold text-white focus:border-[#FFD400] focus:outline-none"
                />
              </div>

              {/* Module 4: Intuitive Audio Controls */}
              <div className="rounded-xl border border-zinc-800 bg-zinc-950/70 p-4 space-y-4">
                <div className="flex items-center gap-2">
                  <Sliders className="h-4 w-4 text-[#FFD400]" />
                  <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-200">
                    Mezclador de Audio Intuitivo
                  </h3>
                </div>

                {/* Voice Volume Slider */}
                <div>
                  <div className="mb-1.5 flex justify-between text-xs">
                    <span className="flex items-center gap-1 font-bold text-zinc-300">
                      <Volume2 className="h-3.5 w-3.5 text-[#FFD400]" /> Volumen de tu Voz
                    </span>
                    <span className="font-mono font-bold text-[#FFD400]">
                      {dbToVoicePct(plan.audio.mic_gain_db)}%{" "}
                      <span className="text-[10px] text-zinc-500 font-normal">
                        ({plan.audio.mic_gain_db >= 0 ? "+" : ""}
                        {plan.audio.mic_gain_db.toFixed(1)} dB)
                      </span>
                    </span>
                  </div>
                  <input
                    type="range"
                    min={0}
                    max={150}
                    step={1}
                    value={dbToVoicePct(plan.audio.mic_gain_db)}
                    onChange={(e) => {
                      const pct = parseInt(e.target.value, 10);
                      const db = voicePctToDb(pct);
                      mutatePlan((d) => {
                        d.audio.mic_gain_db = db;
                        return d;
                      });
                    }}
                    className="h-2 w-full cursor-pointer accent-[#FFD400]"
                  />
                  <div className="mt-1 flex justify-between text-[10px] text-zinc-500">
                    <span>Silencio (0%)</span>
                    <span>Natural (100%)</span>
                    <span>Potenciado (150%)</span>
                  </div>
                </div>

                {/* Game Audio Ducking Selector */}
                <div>
                  <label className="mb-2 block text-xs font-bold text-zinc-300">
                    Atenuación del Juego al Hablar
                  </label>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                    {DUCK_PRESETS.map((presetItem) => {
                      const isSelected =
                        Math.abs(plan.audio.duck_game_db - presetItem.db) < 1.0;
                      return (
                        <button
                          key={presetItem.db}
                          type="button"
                          onClick={() => {
                            mutatePlan((d) => {
                              d.audio.duck_game_db = presetItem.db;
                              return d;
                            });
                          }}
                          className={`flex flex-col rounded-xl border p-2.5 text-left transition ${
                            isSelected
                              ? "border-[#39FF14] bg-[#39FF14]/10 ring-1 ring-[#39FF14]/50"
                              : "border-zinc-800 bg-zinc-900/60 hover:bg-zinc-800/80"
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <span
                              className={`text-xs font-bold ${
                                isSelected ? "text-[#39FF14]" : "text-white"
                              }`}
                            >
                              {presetItem.label}
                            </span>
                            {isSelected && <Check className="h-3.5 w-3.5 text-[#39FF14]" />}
                          </div>
                          <span className="text-[10px] text-zinc-400 mt-0.5">
                            {presetItem.desc}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Live Ducking meter */}
                <div className="pt-2 border-t border-zinc-800/80">
                  <div className="flex items-center justify-between text-[11px] mb-1">
                    <span className="text-zinc-400">
                      Atenuación reactiva del juego en tiempo real:
                    </span>
                    <span className="font-mono font-bold text-[#FFD400]">
                      {liveDuckPct}%
                    </span>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-900">
                    <div
                      className="h-full bg-[#39FF14] transition-all duration-75"
                      style={{ width: `${Math.min(100, liveDuckPct)}%` }}
                    />
                  </div>
                </div>
              </div>

              {/* Sound Effects & Hits */}
              <div className="space-y-3 rounded-xl border border-zinc-800 bg-zinc-950/70 p-3.5 text-xs">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-bold text-zinc-300">
                    Efectos de sonido ({plan.audio.sfx.length})
                  </span>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => fireSfx("boom", -3)}
                      className="inline-flex items-center gap-1 rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-1 text-[11px] font-semibold text-zinc-200 hover:bg-zinc-800"
                    >
                      <Volume2 className="h-3 w-3 text-[#FFD400]" /> Escuchar Boom
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        const tCue = Number(clipTime.toFixed(2));
                        mutatePlan((d) => {
                          d.audio.sfx.push({ t: tCue, id: "boom", gain_db: -3.0 });
                          d.audio.sfx.sort((a, b) => a.t - b.t);
                          return d;
                        });
                        fireSfx("boom", -3);
                      }}
                      className="inline-flex items-center gap-1 rounded-lg bg-[#FFD400]/15 px-2.5 py-1 text-[11px] font-bold text-[#FFD400] ring-1 ring-[#FFD400]/40 hover:bg-[#FFD400]/25"
                    >
                      <Plus className="h-3 w-3" /> Poner Boom aquí ({clipTime.toFixed(1)}s)
                    </button>
                  </div>
                </div>

                {plan.audio.sfx.length > 0 && (
                  <div className="space-y-1.5">
                    {plan.audio.sfx.map((cue, sIdx) => (
                      <div
                        key={sIdx}
                        className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/60 px-2.5 py-1.5"
                      >
                        <button
                          type="button"
                          onClick={() => {
                            seekTo(cue.t);
                            fireSfx(cue.id, cue.gain_db);
                          }}
                          className="font-mono text-[11px] font-semibold text-[#FFD400] hover:underline"
                        >
                          🔊 Efecto {cue.id} en el segundo {cue.t.toFixed(1)}s
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            mutatePlan((d) => {
                              d.audio.sfx.splice(sIdx, 1);
                              return d;
                            })
                          }
                          className="text-zinc-500 hover:text-red-400"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Jump cut ranges */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-bold text-zinc-300">
                    Tramos de partida incluidos ({plan.source.ranges.length})
                  </label>
                  <span className="text-[11px] text-zinc-500">Pausas largas eliminadas</span>
                </div>
                {plan.source.ranges.map(([a, b], idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between rounded-xl border border-zinc-800 bg-zinc-950/70 px-3 py-2 text-xs"
                  >
                    <span className="font-mono text-zinc-300">
                      Parte #{idx + 1}: del segundo <strong>{a.toFixed(1)}s</strong> al{" "}
                      <strong>{b.toFixed(1)}s</strong> ({(b - a).toFixed(1)}s)
                    </span>
                    <Check className="h-3.5 w-3.5 text-[#39FF14]" />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB 4: RAW EDITPLAN V2 JSON */}
          {activeTab === "json" && (
            <pre className="max-h-[580px] overflow-auto rounded-xl border border-zinc-800 bg-zinc-950 p-4 font-mono text-[11px] leading-relaxed text-zinc-300">
              {JSON.stringify(plan, null, 2)}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
