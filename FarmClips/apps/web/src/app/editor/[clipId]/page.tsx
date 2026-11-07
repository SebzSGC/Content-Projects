"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  Camera,
  Check,
  Download,
  Film,
  Loader2,
  Maximize2,
  Pause,
  Play,
  Plus,
  Save,
  Scissors,
  Sparkles,
  Trash2,
  Type,
  Volume2,
  Zap,
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
  type CropKeyframe,
  type EaseKind,
  type EditPlan,
} from "@/lib/api/editplan";

function dbToLinear(db: number): number {
  return Math.pow(10, db / 20);
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
  const emojiCacheRef = useRef<Record<string, HTMLImageElement>>({});
  const clipTimeRef = useRef(0);
  const playingRef = useRef(false);
  const planRef = useRef<EditPlan | null>(null);
  const sessionRef = useRef<SessionSummary | null>(null);
  const syncRef = useRef<{ shift: number; scale: number }>({ shift: 0, scale: 1 });

  // Web Audio API refs (real-time mic_gain_db, sidechain ducking, and boom.wav SFX)
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
      const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
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
      // Store highpass input on micGain node reference helper
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
        // Ignore if unsupported in headless test
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

  // Preload emoji PNGs whenever captions change
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

  // Draw Canvas Overlay + Apply CSS Camera Crop/Layout at 60fps
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

      if (camVideoRef.current) {
        const tx = (0.5 - crop.cx) * 100 * (crop.zoom - 0.15);
        const ty = (0.44 - crop.cy) * 100 * (crop.zoom - 0.15);
        camVideoRef.current.style.transform = `scale(${crop.zoom.toFixed(4)}) translate(${tx.toFixed(2)}%, ${ty.toFixed(2)}%)`;
      }

      // 2. Render Hormozi Captions + Color Emojis + Seam Title on <canvas>
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const W = canvas.width; // 540
      const H = canvas.height; // 960
      ctx.clearRect(0, 0, W, H);

      const splitRatio = p.layout.find((l) => l.kind === "split")?.camera_ratio ?? 0.4;
      const seamY = H * splitRatio;
      const gameH = H - seamY;

      // 2a. Seam Title Overlay (first 3 seconds)
      for (const ov of p.overlays) {
        if (ov.kind === "title" && t >= ov.start && t <= ov.end && ov.text.trim()) {
          ctx.save();
          ctx.font = '800 24px "Montserrat ExtraBold", Inter, sans-serif';
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          const txt = ov.text.trim();
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
      }

      // 2b. Active Caption Group
      const activeGroup = p.captions.groups.find((g) => {
        if (!g.words.length) return false;
        const gs = g.words[0].s;
        const ge = g.words[g.words.length - 1].e;
        return t >= gs && t <= ge + 0.04;
      });

      if (activeGroup && activeGroup.words.length > 0) {
        const capY = seamY + gameH * (preset?.captions.gameplay_top_third_ratio ?? 0.28);
        const baseFontPx = 39;

        // Emoji PNG above active emphasis word
        if (activeGroup.emoji && t >= activeGroup.emoji.at) {
          const img = emojiCacheRef.current[activeGroup.emoji.id];
          if (img && img.complete && img.naturalWidth > 0) {
            const elapsed = Math.min(1, (t - activeGroup.emoji.at) / 0.14);
            const pop = elapsed < 0.6 ? 1 + 0.22 * (elapsed / 0.6) : 1.22 - 0.22 * ((elapsed - 0.6) / 0.4);
            const size = 62 * pop;
            ctx.drawImage(img, (W - size) / 2, capY - size - 26, size, size);
          }
        }

        // Measure each word (cached by fontPx + word) to render multi-colored inline words centered cleanly
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
          wordSpecs.reduce((acc, ws) => acc + ws.width, 0) + Math.max(0, wordSpecs.length - 1) * spaceW;
        let cursorX = (W - totalW) / 2;

        for (const ws of wordSpecs) {
          ctx.font = `800 ${ws.fontPx}px "Montserrat ExtraBold", Impact, sans-serif`;
          ctx.textAlign = "left";
          ctx.textBaseline = "middle";
          ctx.lineJoin = "round";
          ctx.miterLimit = 2;

          // Drop shadow + thick black stroke
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
    [preset]
  );

  // Sync <video> elements to virtual clipTime
  const syncVideosToClipTime = useCallback((t: number, forceSeek: boolean) => {
    const p = planRef.current;
    if (!p) return;
    const { masterTime } = clipToMasterTime(p, t);
    const camTime = Math.max(0, masterTime * syncRef.current.scale + syncRef.current.shift);

    const gv = gameVideoRef.current;
    const cv = camVideoRef.current;
    if (gv && gv.readyState >= 1 && (forceSeek || Math.abs(gv.currentTime - masterTime) > 0.24)) {
      gv.currentTime = masterTime;
    }
    if (cv && cv.readyState >= 1 && (forceSeek || Math.abs(cv.currentTime - camTime) > 0.24)) {
      cv.currentTime = camTime;
    }
  }, []);

  // 60 fps requestAnimationFrame loop (Video Sync + Canvas + Web Audio Sidechain & SFX)
  useEffect(() => {
    let rafId = 0;
    let lastTs = performance.now();
    let frameCount = 0;

    const tick = (now: number) => {
      const dt = Math.min(0.1, (now - lastTs) / 1000);
      lastTs = now;
      frameCount += 1;

      const p = planRef.current;
      if (p) {
        // Real-time Web Audio gain & sidechain ducking update
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

      if (p && playingRef.current) {
        const prevT = clipTimeRef.current;
        const total = getTotalClipDuration(p);
        let nextT = prevT + dt;
        if (nextT >= total) {
          nextT = 0;
          syncVideosToClipTime(0, true);
        } else {
          syncVideosToClipTime(nextT, false);
          for (const cue of p.audio.sfx) {
            if (prevT < cue.t && nextT >= cue.t && nextT - prevT < 0.2) {
              fireSfx(cue.id, cue.gain_db);
            }
          }
        }
        clipTimeRef.current = nextT;
        // Direct 60fps DOM updates without triggering full React Virtual DOM reconciliation on every frame
        if (scrubberInputRef.current) {
          scrubberInputRef.current.value = String(nextT);
        }
        if (timeLabelRef.current) {
          timeLabelRef.current.textContent = `${nextT.toFixed(2)}s / ${total.toFixed(1)}s`;
        }
        if (playheadBarRef.current) {
          playheadBarRef.current.style.left = `${(nextT / Math.max(0.1, total)) * 100}%`;
        }
        if (now - lastReactTimeSyncRef.current >= 120 || nextT === 0) {
          lastReactTimeSyncRef.current = now;
          setClipTime(nextT);
        }
      }

      renderFrameAt(clipTimeRef.current);
      rafId = requestAnimationFrame(tick);
    };

    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [fireSfx, renderFrameAt, syncVideosToClipTime]);

  function togglePlay() {
    const next = !playing;
    setPlaying(next);
    const gv = gameVideoRef.current;
    const cv = camVideoRef.current;
    if (next) {
      ensureWebAudio().catch(() => null);
      syncVideosToClipTime(clipTimeRef.current, true);
      gv?.play().catch(() => null);
      cv?.play().catch(() => null);
    } else {
      gv?.pause();
      cv?.pause();
      setClipTime(clipTimeRef.current);
    }
  }

  function seekTo(newT: number) {
    const total = plan ? getTotalClipDuration(plan) : 0;
    const clamped = Math.max(0, Math.min(total, newT));
    clipTimeRef.current = clamped;
    if (scrubberInputRef.current) scrubberInputRef.current.value = String(clamped);
    if (timeLabelRef.current) timeLabelRef.current.textContent = `${clamped.toFixed(2)}s / ${total.toFixed(1)}s`;
    if (playheadBarRef.current) playheadBarRef.current.style.left = `${(clamped / Math.max(0.1, total)) * 100}%`;
    setClipTime(clamped);
    syncVideosToClipTime(clamped, true);
    renderFrameAt(clamped);
  }

  function mutatePlan(updater: (draft: EditPlan) => EditPlan) {
    setPlan((prev) => {
      if (!prev) return prev;
      const updated = updater(structuredClone(prev));
      setDirty(true);
      return updated;
    });
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
      setStatusMsg("EditPlan v2 guardado sin re-renderizar.");
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
          ? "MP4 1080p exportado y reemplazado en Salidas/."
          : "Borrador rápido 540p listo."
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

  function addFullscreenReactionAtPlayhead() {
    if (!plan) return;
    const total = getTotalClipDuration(plan);
    const t0 = Number(Math.max(0.1, Math.min(total - 1.2, clipTime)).toFixed(2));
    const until = Number(Math.min(total, t0 + 2.0).toFixed(2));
    mutatePlan((d) => {
      d.layout.push({ t: t0, kind: "camera_full", until });
      d.layout.sort((a, b) => a.t - b.t);
      return d;
    });
  }

  if (!clip || !session || !plan) {
    return (
      <div className="flex items-center justify-center py-24 text-zinc-400">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Cargando Editor EditPlan v2…
      </div>
    );
  }

  const totalDur = getTotalClipDuration(plan);
  const renderedUrl = clip.has_final
    ? `${API_PREFIX}/clips/${clip.id}/file?quality=final&t=${Math.floor(clip.updated_at)}`
    : clip.has_draft
      ? `${API_PREFIX}/clips/${clip.id}/file?quality=draft&t=${Math.floor(clip.updated_at)}`
      : null;

  return (
    <div className="space-y-5">
      {/* Studio Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-zinc-800 bg-[#0E1017] px-5 py-3.5">
        <div className="flex items-center gap-3">
          <Link
            href={`/sessions/${session.id}`}
            className="inline-flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-950 px-2.5 py-1.5 text-xs text-zinc-300 hover:text-white"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Sesión
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-extrabold text-white">{clip.overlay_title}</h1>
              <span className="rounded bg-[#FFD400]/15 px-2 py-0.5 font-mono text-[11px] font-bold text-[#FFD400]">
                {clip.final_score.toFixed(0)}/100
              </span>
              {dirty && (
                <span className="rounded bg-amber-500/20 px-2 py-0.5 text-[10px] font-semibold text-amber-300">
                  Cambios sin guardar
                </span>
              )}
            </div>
            <p className="text-[11px] text-zinc-400">
              Reproducción instantánea sobre fuentes originales (0 s de espera) · {plan.source.ranges.length} tramos
              activos ({totalDur.toFixed(1)}s)
              {statusMsg ? ` · ${statusMsg}` : ""}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-700 bg-zinc-900 px-3.5 py-2 text-xs font-bold text-white hover:bg-zinc-800 disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
            Guardar EditPlan
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
            Borrador 540p
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
            Exportar 1080p (+ Salidas/)
          </button>
        </div>
      </div>

      {renderProgress !== null && (
        <div className="rounded-xl border border-[#FFD400]/30 bg-[#FFD400]/10 px-4 py-2.5 text-xs text-[#FFD400]">
          <div className="flex justify-between font-bold">
            <span>Codificando con FFmpeg ({renderingQuality === "draft" ? "540p" : "1080p NVENC"})…</span>
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

      {/* Main Studio Grid: Left = 9:16 Live Preview, Right = Inspector Tabs */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left Column: Vertical 9:16 Stage + Timeline Scrubber */}
        <div className="flex flex-col items-center rounded-2xl border border-zinc-800 bg-[#0E1017] p-4 lg:col-span-5">
          <div className="mb-3 flex w-full items-center justify-between">
            <div className="inline-flex rounded-lg border border-zinc-800 bg-zinc-950 p-0.5 text-xs">
              <button
                type="button"
                onClick={() => setPreviewSource("live")}
                className={`rounded-md px-3 py-1 font-semibold transition ${
                  previewSource === "live" ? "bg-[#FFD400] text-black" : "text-zinc-400 hover:text-white"
                }`}
              >
                Vista Instantánea (CSS + Canvas)
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
                    previewSource === "rendered" ? "bg-[#39FF14] text-black" : "text-zinc-400 hover:text-white"
                  }`}
                >
                  MP4 Renderizado
                </button>
              )}
            </div>

            {renderedUrl && (
              <a
                href={`${API_PREFIX}/clips/${clip.id}/file?quality=final&download=true`}
                className="inline-flex items-center gap-1 text-xs font-semibold text-zinc-300 hover:text-[#FFD400]"
              >
                <Download className="h-3.5 w-3.5" /> MP4
              </a>
            )}
          </div>

          {/* 9:16 Viewport */}
          <div className="relative aspect-[9/16] w-full max-w-[330px] overflow-hidden rounded-2xl border border-zinc-700/80 bg-black shadow-2xl">
            {previewSource === "live" ? (
              <>
                {/* Top 40% (or 100% on camera_full): Streamer Camera */}
                <div ref={camWrapRef} className="relative h-[40%] w-full overflow-hidden bg-zinc-950">
                  <video
                    ref={camVideoRef}
                    src={`${API_PREFIX}/sessions/${session.id}/stream/camera`}
                    crossOrigin="anonymous"
                    playsInline
                    preload="auto"
                    className="h-full w-full origin-center object-cover will-change-transform"
                  />
                </div>

                {/* Bottom 60%: Gameplay */}
                <div ref={gameWrapRef} className="relative h-[60%] w-full overflow-hidden bg-black">
                  <video
                    ref={gameVideoRef}
                    src={`${API_PREFIX}/sessions/${session.id}/stream/gameplay`}
                    crossOrigin="anonymous"
                    playsInline
                    muted
                    preload="auto"
                    className="h-full w-full object-cover"
                  />
                </div>

                {/* 60fps Canvas for Hormozi Captions, Color Emoji PNGs, and Seam Title */}
                <canvas
                  ref={canvasRef}
                  width={540}
                  height={960}
                  onClick={togglePlay}
                  className=" absolute inset-0 h-full w-full cursor-pointer"
                />
              </>
            ) : (
              renderedUrl && (
                <video src={renderedUrl} controls autoPlay className="h-full w-full object-contain" />
              )
            )}
          </div>

          {/* Scrubber & Event Markers (only for Live Preview) */}
          {previewSource === "live" && (
            <div className="mt-4 w-full space-y-2">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={togglePlay}
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-[#FFD400] text-black hover:bg-amber-300"
                >
                  {playing ? <Pause className="h-4 w-4 fill-black" /> : <Play className="h-4 w-4 fill-black" />}
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
                        title={`camera_full (${ev.t}s - ${ev.until}s)`}
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
                <span>Verde: Zoom outBack</span>
                <span>Morado: Cámara pantalla completa (2s)</span>
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Declarative EditPlan v2 Inspector */}
        <div className="flex flex-col rounded-2xl border border-zinc-800 bg-[#0E1017] p-5 lg:col-span-7">
          <div className="mb-4 flex flex-wrap gap-1.5 border-b border-zinc-800 pb-3 text-xs font-bold">
            <button
              type="button"
              onClick={() => setActiveTab("captions")}
              className={`inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 transition ${
                activeTab === "captions" ? "bg-[#FFD400] text-black" : "bg-zinc-900 text-zinc-300 hover:text-white"
              }`}
            >
              <Type className="h-3.5 w-3.5" /> Subtítulos y Emojis ({plan.captions.groups.length})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("camera")}
              className={`inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 transition ${
                activeTab === "camera" ? "bg-[#FFD400] text-black" : "bg-zinc-900 text-zinc-300 hover:text-white"
              }`}
            >
              <Camera className="h-3.5 w-3.5" /> Cámara y Zooms ({plan.camera_crop.length})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("cuts")}
              className={`inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 transition ${
                activeTab === "cuts" ? "bg-[#FFD400] text-black" : "bg-zinc-900 text-zinc-300 hover:text-white"
              }`}
            >
              <Scissors className="h-3.5 w-3.5" /> Título, Cortes y Audio
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("json")}
              className={`inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 font-mono transition ${
                activeTab === "json" ? "bg-[#FFD400] text-black" : "bg-zinc-900 text-zinc-300 hover:text-white"
              }`}
            >
              EditPlan JSON
            </button>
          </div>

          {/* TAB 1: CAPTIONS & EMOJIS */}
          {activeTab === "captions" && (
            <div className="max-h-[580px] space-y-2.5 overflow-y-auto pr-1">
              {plan.captions.groups.map((grp, gIdx) => {
                const gs = grp.words[0]?.s ?? 0;
                const ge = grp.words[grp.words.length - 1]?.e ?? 0;
                const isCurrent = clipTime >= gs && clipTime <= ge;

                return (
                  <div
                    key={gIdx}
                    className={`rounded-xl border p-3 transition ${
                      isCurrent ? "border-[#FFD400]/60 bg-[#FFD400]/5" : "border-zinc-800/90 bg-zinc-950/60"
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
                              {emojiCatalog.find((x) => x.id === grp.emoji?.id)?.name ?? grp.emoji.id}
                            </span>
                          </>
                        ) : (
                          <span className="text-zinc-400">+ Elegir Emoji ({emojiCatalog.length || 42})</span>
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
                            Sin emoji
                          </button>
                        </div>
                        <div className="grid max-h-40 grid-cols-7 gap-1.5 overflow-y-auto sm:grid-cols-10">
                          {emojiCatalog
                            .filter((em) => emojiCategoryFilter === "all" || em.category === emojiCategoryFilter)
                            .map((em) => (
                              <button
                                key={em.id}
                                type="button"
                                title={`${em.char} ${em.name} (${em.id})`}
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
                            title="Alternar énfasis verde (#39FF14)"
                            className={`rounded px-1.5 py-0.5 text-[10px] font-bold transition ${
                              w.emphasis ? "bg-[#39FF14] text-black" : "bg-zinc-800 text-zinc-400 hover:text-white"
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

          {/* TAB 2: CAMERA CROP KEYFRAMES & FULLSCREEN REACTIONS */}
          {activeTab === "camera" && (
            <div className="max-h-[580px] space-y-5 overflow-y-auto pr-1">
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={addImpactZoomAtPlayhead}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-[#39FF14]/15 px-3.5 py-2 text-xs font-bold text-[#39FF14] ring-1 ring-[#39FF14]/40 hover:bg-[#39FF14]/25"
                >
                  <Plus className="h-3.5 w-3.5" /> Zoom de impacto aquí ({clipTime.toFixed(2)}s)
                </button>
                <button
                  type="button"
                  onClick={addFullscreenReactionAtPlayhead}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-purple-500/15 px-3.5 py-2 text-xs font-bold text-purple-300 ring-1 ring-purple-500/40 hover:bg-purple-500/25"
                >
                  <Maximize2 className="h-3.5 w-3.5" /> Cámara pantalla completa 2s aquí
                </button>
              </div>

              {/* Layout overrides */}
              <div className="space-y-2">
                <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400">
                  Eventos de Layout (Split 40/60 vs Cámara Completa)
                </h3>
                {plan.layout.map((ev, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between rounded-xl border border-zinc-800 bg-zinc-950/70 px-3 py-2 text-xs"
                  >
                    <span className="font-mono text-zinc-200">
                      <strong>{ev.kind}</strong> · {ev.t.toFixed(2)}s
                      {ev.until != null ? ` → ${ev.until.toFixed(2)}s` : ` (ratio ${ev.camera_ratio ?? 0.4})`}
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

              {/* Camera Crop Keyframes */}
              <div className="space-y-2">
                <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400">
                  Keyframes de Encuadre y Zoom ({plan.camera_crop.length})
                </h3>
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
                    <label className="col-span-3 flex items-center gap-1 text-[11px] text-zinc-400">
                      cx
                      <input
                        type="number"
                        step="0.02"
                        min="0.1"
                        max="0.9"
                        value={kf.cx}
                        onChange={(e) =>
                          mutatePlan((d) => {
                            d.camera_crop[idx].cx = parseFloat(e.target.value) || 0.5;
                            return d;
                          })
                        }
                        className="w-14 rounded border border-zinc-800 bg-zinc-900 px-1.5 py-0.5 font-mono text-white"
                      />
                    </label>
                    <label className="col-span-3 flex items-center gap-1 text-[11px] text-zinc-400">
                      zoom
                      <input
                        type="number"
                        step="0.05"
                        min="1.0"
                        max="2.8"
                        value={kf.zoom}
                        onChange={(e) =>
                          mutatePlan((d) => {
                            d.camera_crop[idx].zoom = Math.max(1, parseFloat(e.target.value) || 1);
                            return d;
                          })
                        }
                        className="w-14 rounded border border-zinc-800 bg-zinc-900 px-1.5 py-0.5 font-mono text-white"
                      />
                    </label>
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
                      <option value="linear">linear</option>
                      <option value="outBack">outBack</option>
                      <option value="inOutSine">inOutSine</option>
                      <option value="outCubic">outCubic</option>
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

          {/* TAB 3: OVERLAY TITLE, JUMP CUT RANGES & AUDIO */}
          {activeTab === "cuts" && (
            <div className="space-y-5">
              <div>
                <label className="mb-1 block text-xs font-bold text-zinc-300">
                  Título en la unión 40/60 (primeros 3 segundos)
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

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-bold text-zinc-300">
                    Tramos de tiempo maestro activos — Jump Cuts ({plan.source.ranges.length})
                  </label>
                  <span className="text-[11px] text-zinc-500">Silencios &gt;0,7 s recortados automáticamente</span>
                </div>
                {plan.source.ranges.map(([a, b], idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between rounded-xl border border-zinc-800 bg-zinc-950/70 px-3 py-2 text-xs"
                  >
                    <span className="font-mono text-zinc-300">
                      Tramo #{idx + 1}: <strong>{a.toFixed(2)}s</strong> → <strong>{b.toFixed(2)}s</strong> (
                      {(b - a).toFixed(2)}s)
                    </span>
                    <Check className="h-3.5 w-3.5 text-[#39FF14]" />
                  </div>
                ))}
              </div>

              <div className="grid grid-cols-1 gap-4 border-t border-zinc-800 pt-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1 flex items-center gap-1.5 text-xs font-bold text-zinc-300">
                    <Volume2 className="h-3.5 w-3.5 text-[#FFD400]" /> Ganancia Micrófono (dB)
                  </label>
                  <input
                    type="number"
                    step="0.5"
                    value={plan.audio.mic_gain_db}
                    onChange={(e) =>
                      mutatePlan((d) => {
                        d.audio.mic_gain_db = parseFloat(e.target.value) || 0;
                        return d;
                      })
                    }
                    className="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 font-mono text-xs text-white"
                  />
                </div>
                <div>
                  <label className="mb-1 flex items-center gap-1.5 text-xs font-bold text-zinc-300">
                    <Volume2 className="h-3.5 w-3.5 text-[#39FF14]" /> Atenuación Sidechain Juego (dB)
                  </label>
                  <input
                    type="number"
                    step="0.5"
                    value={plan.audio.duck_game_db}
                    onChange={(e) =>
                      mutatePlan((d) => {
                        d.audio.duck_game_db = parseFloat(e.target.value) || -9;
                        return d;
                      })
                    }
                    className="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 font-mono text-xs text-white"
                  />
                </div>
              </div>

              {/* Web Audio API Real-Time Mixer Status & SFX Controls */}
              <div className="space-y-3 rounded-xl border border-zinc-800 bg-zinc-950/70 p-3.5 text-xs">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-bold text-white">
                    Mezclador Web Audio API en vivo ·{" "}
                    <span className="text-[#39FF14]">
                      {session.prepared?.gameplay_clean_audio_stream != null
                        ? "Sidechain activo sobre pista limpia"
                        : "Filtro Highpass 75 Hz + Ganancia Mic + SFX"}
                    </span>
                  </span>
                  <span className="font-mono text-[11px] text-zinc-400">
                    Ducking actual: <strong className="text-[#FFD400]">{liveDuckPct}%</strong>
                  </span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-900">
                  <div
                    className="h-full bg-[#39FF14] transition-all duration-75"
                    style={{ width: `${Math.min(100, liveDuckPct)}%` }}
                  />
                </div>

                <div className="flex flex-wrap items-center justify-between gap-2 border-t border-zinc-800/80 pt-3">
                  <span className="font-bold text-zinc-300">
                    Impactos de sonido SFX ({plan.audio.sfx.length})
                  </span>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => fireSfx("boom", -3)}
                      className="inline-flex items-center gap-1 rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-1 text-[11px] font-semibold text-zinc-200 hover:bg-zinc-800"
                    >
                      <Volume2 className="h-3 w-3 text-[#FFD400]" /> Probar Boom
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
                      <Plus className="h-3 w-3" /> Añadir Boom aquí ({clipTime.toFixed(2)}s)
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
                          🔊 {cue.id}.wav @ {cue.t.toFixed(2)}s ({cue.gain_db} dB)
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
