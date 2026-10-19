import React, { useEffect, useState, useRef } from "react";
import {
  Sparkles,
  Image as ImageIcon,
  Mic,
  Layers,
  Play,
  Download,
  FolderKanban,
  Sliders,
  RefreshCw,
  FolderPlus,
  Wand2,
  FileCode2,
  Cpu,
  KeyRound,
  CheckCircle2,
  Video,
  Volume2,
  Sun,
  Moon,
  ChevronRight,
  ChevronDown,
  Upload,
  Scissors,
  SlidersHorizontal,
  Plus,
  Trash2,
  X,
  Film,
  Subtitles,
  Check,
  AlertCircle
} from "lucide-react";

async function api(path, options = {}) {
  const res = await fetch(`/api/v1${path}`, {
    headers: options.body instanceof FormData ? {} : { "Content-Type": "application/json" },
    ...options
  });
  if (!res.ok) {
    const errText = await res.text();
    let msg = errText || `HTTP ${res.status}`;
    try {
      const parsed = JSON.parse(errText);
      if (parsed.detail) msg = parsed.detail;
    } catch {}
    throw new Error(msg);
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res.text();
}

const NAV_GROUPS = [
  {
    label: "Producción",
    items: [
      { id: "prompts", label: "Guion y Director", icon: Sparkles, shortcut: "Alt+1" },
      { id: "multimedia", label: "Multimedia", icon: ImageIcon, shortcut: "Alt+2" },
      { id: "audios", label: "Locución y Audio", icon: Mic, shortcut: "Alt+3" }
    ]
  },
  {
    label: "Postproducción",
    items: [
      { id: "sync", label: "Sincronización SRT", icon: Layers, shortcut: "Alt+4" },
      { id: "studio", label: "Editor Studio", icon: Film, shortcut: "Alt+5" }
    ]
  },
  {
    label: "Sistema",
    items: [
      { id: "files", label: "Proyectos", icon: FolderKanban, shortcut: "Alt+6" },
      { id: "settings", label: "Preferencias", icon: Sliders, shortcut: "Alt+7" }
    ]
  }
];

const VIEW_LABELS = {
  prompts: "Guion y Director",
  multimedia: "Multimedia",
  audios: "Locución y Audio",
  sync: "Sincronización SRT",
  studio: "Editor Studio",
  files: "Proyectos",
  settings: "Preferencias"
};

export default function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem("vf_theme") || "dark");
  const [activeTab, setActiveTab] = useState("prompts");
  const [projects, setProjects] = useState([]);
  const [currentProject, setCurrentProject] = useState(null);
  const [scriptData, setScriptData] = useState({ text: "", beats: [], characters: [] });
  const [styleGuide, setStyleGuide] = useState("Cinematográfico, iluminación natural, alta definición");
  const [showStyleDrawer, setShowStyleDrawer] = useState(false);

  const [assets, setAssets] = useState([]);
  const [mediaFilter, setMediaFilter] = useState("all");
  const [showQuickGen, setShowQuickGen] = useState(false);
  const [quickPrompt, setQuickPrompt] = useState("");
  const [quickKind, setQuickKind] = useState("image");

  const [ttsSpeed, setTtsSpeed] = useState(1.0);
  const [transcript, setTranscript] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [hardware, setHardware] = useState(null);
  const [providers, setProviders] = useState([]);

  const [activeJob, setActiveJob] = useState(null);
  const [toast, setToast] = useState(null);
  const [playheadUs, setPlayheadUs] = useState(0);
  const [secretInputs, setSecretInputs] = useState({});

  const [selectedTemplate, setSelectedTemplate] = useState("stat-highlight");
  const [jsonMode, setJsonMode] = useState(false);
  const [templateProps, setTemplateProps] = useState({
    value: "90%",
    label: "Aceleración NVIDIA",
    sublabel: "Turing NVENC a 60 FPS",
    accent_color: "#5e6ad2"
  });

  // New Project Modal State
  const [showProjectModal, setShowProjectModal] = useState(false);
  const [newProjName, setNewProjName] = useState("");
  const [newProjPreset, setNewProjPreset] = useState("1080p_landscape");
  const [newProjFps, setNewProjFps] = useState(60);

  const currentProjectRef = useRef(null);
  currentProjectRef.current = currentProject;
  const toastTimerRef = useRef(null);

  function notify(message, type = "info") {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setToast({ message, type });
    toastTimerRef.current = setTimeout(() => setToast(null), 4200);
  }

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("vf_theme", theme);
  }, [theme]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.altKey && !e.ctrlKey && !e.metaKey) {
        const map = {
          "1": "prompts",
          "2": "multimedia",
          "3": "audios",
          "4": "sync",
          "5": "studio",
          "6": "files",
          "7": "settings"
        };
        if (map[e.key]) {
          e.preventDefault();
          setActiveTab(map[e.key]);
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  async function loadInitialData() {
    try {
      const [projs, tmpls, hw, provs] = await Promise.all([
        api("/projects"),
        api("/templates"),
        api("/system/hardware"),
        api("/providers")
      ]);
      setTemplates(tmpls);
      setHardware(hw);
      setProviders(provs);

      if (projs.length === 0) {
        const created = await api("/projects", {
          method: "POST",
          body: JSON.stringify({
            name: "Proyecto Principal",
            language: "es",
            width: 1920,
            height: 1080,
            fps: 60
          })
        });
        setProjects([created]);
        await selectProject(created);
      } else {
        setProjects(projs);
        // Prefer the real test project if present
        const preferred = projs.find((p) => p.name.includes("Collage")) || projs[0];
        await selectProject(preferred);
      }
    } catch (err) {
      notify(`Error al cargar datos iniciales: ${err.message}`, "error");
    }
  }

  async function selectProject(proj) {
    setCurrentProject(proj);
    try {
      const [scr, asts, tl] = await Promise.all([
        api(`/projects/${proj.id}/script`),
        api(`/projects/${proj.id}/assets`),
        api(`/projects/${proj.id}/timeline`)
      ]);
      setScriptData(scr);
      setStyleGuide(proj.style_guide || "Cinematográfico, iluminación natural, alta definición");
      setAssets(asts);
      setTimeline(tl);
      if (proj.active_transcript_id) {
        try {
          const tr = await api(`/transcripts/${proj.active_transcript_id}`);
          setTranscript(tr);
        } catch {
          setTranscript(null);
        }
      } else {
        setTranscript(null);
      }
    } catch (err) {
      notify(`No se pudo abrir el proyecto: ${err.message}`, "error");
    }
  }

  async function refreshProjectState() {
    const proj = currentProjectRef.current;
    if (!proj) return;
    const [updatedProj, projs] = await Promise.all([
      api(`/projects/${proj.id}`),
      api("/projects")
    ]);
    setProjects(projs);
    await selectProject(updatedProj);
  }

  useEffect(() => {
    loadInitialData();
    const es = new EventSource("/api/v1/events");
    const handleJobEvent = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.state === "running" || data.state === "queued") {
          setActiveJob({
            id: data.job_id,
            progress: data.progress ?? 0.08,
            stage: data.stage || "Procesando tarea..."
          });
        } else if (data.state === "succeeded" || data.type === "job.succeeded") {
          setActiveJob(null);
          notify("Proceso completado correctamente.", "ok");
          refreshProjectState();
        } else if (data.state === "failed" || data.type === "job.failed") {
          setActiveJob(null);
          notify(`Fallo en proceso: ${data.job?.error?.message || "Error inesperado"}`, "error");
        } else if (data.state === "cancelled" || data.type === "job.cancelled") {
          setActiveJob(null);
          notify("Tarea cancelada por el usuario.", "info");
        }
      } catch {}
    };
    es.addEventListener("job.queued", handleJobEvent);
    es.addEventListener("job.running", handleJobEvent);
    es.addEventListener("job.progress", handleJobEvent);
    es.addEventListener("job.succeeded", handleJobEvent);
    es.addEventListener("job.failed", handleJobEvent);
    es.addEventListener("job.cancelled", handleJobEvent);
    return () => es.close();
  }, []);

  async function handleCreateProjectSubmit(e) {
    e.preventDefault();
    const name = newProjName.trim() || `Proyecto ${projects.length + 1}`;
    const dims =
      newProjPreset === "1080p_vertical"
        ? { width: 1080, height: 1920 }
        : newProjPreset === "720p_landscape"
        ? { width: 1280, height: 720 }
        : { width: 1920, height: 1080 };

    try {
      const created = await api("/projects", {
        method: "POST",
        body: JSON.stringify({
          name,
          language: "es",
          width: dims.width,
          height: dims.height,
          fps: Number(newProjFps),
          style_guide: styleGuide
        })
      });
      setProjects((prev) => [created, ...prev]);
      await selectProject(created);
      setShowProjectModal(false);
      setNewProjName("");
      notify(`Proyecto "${created.name}" creado.`, "ok");
    } catch (err) {
      notify(err.message, "error");
    }
  }

  async function handleDeleteProject(projId, projName, e) {
    e.stopPropagation();
    if (projects.length <= 1) {
      notify("Debes conservar al menos un proyecto activo.", "error");
      return;
    }
    try {
      await api(`/projects/${projId}`, { method: "DELETE" });
      const remaining = projects.filter((p) => p.id !== projId);
      setProjects(remaining);
      if (currentProject?.id === projId && remaining.length > 0) {
        await selectProject(remaining[0]);
      }
      notify(`Proyecto "${projName}" eliminado.`, "info");
    } catch (err) {
      notify(err.message, "error");
    }
  }

  async function handleDeleteAsset(assetId, assetName, e) {
    if (e) e.stopPropagation();
    try {
      await api(`/assets/${assetId}`, { method: "DELETE" });
      setAssets((prev) => prev.filter((a) => a.id !== assetId));
      notify(`Recurso "${assetName || 'archivo'}" eliminado.`, "info");
    } catch (err) {
      notify(err.message, "error");
    }
  }

  async function handleBatchDeleteVisualAssets() {
    if (!visualAssets.length) return;
    if (!window.confirm("¿Deseas eliminar todas las imágenes y vídeos de la biblioteca multimedia?")) return;
    try {
      await api("/assets/batch-delete", {
        method: "POST",
        body: JSON.stringify({ asset_ids: visualAssets.map((a) => a.id) })
      });
      setAssets((prev) => prev.filter((a) => a.kind === "audio"));
      notify("Biblioteca multimedia vaciada.", "info");
    } catch (err) {
      notify(err.message, "error");
    }
  }

  async function handleCancelActiveJob() {
    if (!activeJob?.id) return;
    try {
      await api(`/jobs/${activeJob.id}/cancel`, { method: "POST" });
      setActiveJob(null);
      notify("Cancelando tarea...", "info");
    } catch {}
  }

  async function handleSegmentScript() {
    if (!currentProject) return;
    try {
      const res = await api(`/projects/${currentProject.id}/script/segment`, {
        method: "POST",
        body: JSON.stringify({ text: scriptData.text, style_guide: styleGuide, use_llm: false })
      });
      setScriptData(res);
      notify(`${res.beats.length} escenas estructuradas y ${res.characters.length} personajes detectados.`, "ok");
    } catch (err) {
      notify(err.message, "error");
    }
  }

  async function handleSaveScript() {
    if (!currentProject) return;
    try {
      await api(`/projects/${currentProject.id}/script`, {
        method: "PUT",
        body: JSON.stringify(scriptData)
      });
      notify("Guion guardado en el proyecto.", "ok");
    } catch (err) {
      notify(err.message, "error");
    }
  }

  async function handleAutopilot() {
    if (!currentProject) return;
    try {
      await api(`/projects/${currentProject.id}/script`, {
        method: "PUT",
        body: JSON.stringify(scriptData)
      });
      const job = await api(`/projects/${currentProject.id}/autopilot`, { method: "POST" });
      setActiveJob({ id: job.id, progress: 0.06, stage: "Ejecutando flujo Autopilot..." });
    } catch (err) {
      notify(err.message, "error");
    }
  }

  async function handleGenerateAllBeats() {
    if (!currentProject) return;
    try {
      const job = await api(`/projects/${currentProject.id}/generations`, {
        method: "POST",
        body: JSON.stringify({ kind: "batch_beats" })
      });
      setActiveJob({ id: job.id, progress: 0.05, stage: "Generando escenas del guion..." });
    } catch (err) {
      notify(err.message, "error");
    }
  }

  async function handleGenerateSingleBeat(beat, idx) {
    if (!currentProject) return;
    try {
      const job = await api(`/projects/${currentProject.id}/generations`, {
        method: "POST",
        body: JSON.stringify({
          kind: beat.media_kind === "video" ? "video" : "image",
          prompt: beat.visual_prompt || beat.text,
          beat_index: idx,
          tags: beat.tags || []
        })
      });
      setActiveJob({ id: job.id, progress: 0.1, stage: `Generando escena #${idx + 1}...` });
    } catch (err) {
      notify(err.message, "error");
    }
  }

  async function handleQuickGenerate(e) {
    e.preventDefault();
    if (!currentProject || !quickPrompt.trim()) return;
    try {
      const job = await api(`/projects/${currentProject.id}/generations`, {
        method: "POST",
        body: JSON.stringify({
          kind: quickKind,
          prompt: quickPrompt.trim(),
          beat_index: assets.length
        })
      });
      setActiveJob({ id: job.id, progress: 0.1, stage: "Generando recurso visual..." });
      setQuickPrompt("");
      setShowQuickGen(false);
    } catch (err) {
      notify(err.message, "error");
    }
  }

  async function handleGenerateTts() {
    if (!currentProject) return;
    try {
      const job = await api(`/projects/${currentProject.id}/generations`, {
        method: "POST",
        body: JSON.stringify({
          kind: "tts",
          prompt: scriptData.text,
          voice: "es-local",
          speed: Number(ttsSpeed)
        })
      });
      setActiveJob({ id: job.id, progress: 0.1, stage: "Sintetizando locución en español..." });
    } catch (err) {
      notify(err.message, "error");
    }
  }

  async function handleAudioLab(operation) {
    if (!currentProject) return;
    const audioAssets = assets.filter((a) => a.kind === "audio");
    if (audioAssets.length === 0) {
      notify("Primero genera o importa una pista de audio.", "error");
      return;
    }
    try {
      const job = await api(`/projects/${currentProject.id}/audio/process`, {
        method: "POST",
        body: JSON.stringify({
          operation,
          asset_ids: audioAssets.map((a) => a.id),
          target_lufs: -14.0
        })
      });
      setActiveJob({ id: job.id, progress: 0.12, stage: `AudioLab: ${operation}` });
    } catch (err) {
      notify(err.message, "error");
    }
  }

  async function handleUploadAsset(e) {
    const file = e.target.files?.[0];
    if (!file || !currentProject) return;
    try {
      const fd = new FormData();
      fd.append("file", file);
      await api(`/projects/${currentProject.id}/assets/upload`, {
        method: "POST",
        body: fd
      });
      await refreshProjectState();
      notify(`Archivo "${file.name}" añadido al proyecto.`, "ok");
    } catch (err) {
      notify(err.message, "error");
    }
  }

  async function handleAlignTranscript() {
    if (!currentProject) return;
    try {
      const job = await api(`/projects/${currentProject.id}/transcripts`, {
        method: "POST",
        body: JSON.stringify({ use_script_text: true, use_whisper: false })
      });
      setActiveJob({ id: job.id, progress: 0.15, stage: "Alineando palabras con audio..." });
    } catch (err) {
      notify(err.message, "error");
    }
  }

  async function handleAutoPlanTimeline() {
    if (!currentProject) return;
    try {
      const tl = await api(`/projects/${currentProject.id}/timeline/autoplan`, {
        method: "POST",
        body: JSON.stringify({
          default_transition: "fade",
          transition_duration_us: 400000,
          include_motion_scenes: true
        })
      });
      setTimeline(tl);
      notify("Línea de tiempo sincronizada sin huecos.", "ok");
    } catch (err) {
      notify(err.message, "error");
    }
  }

  function handleSelectTemplate(tmplId) {
    setSelectedTemplate(tmplId);
    const found = templates.find((t) => t.id === tmplId);
    if (found?.default_props) {
      setTemplateProps(found.default_props);
    }
  }

  async function handleRenderMotionScene() {
    if (!currentProject) return;
    try {
      const job = await api(`/projects/${currentProject.id}/motion-scenes/render`, {
        method: "POST",
        body: JSON.stringify({
          template_id: selectedTemplate,
          props: templateProps,
          duration_us: 3500000,
          spoken_text: scriptData.text,
          alpha: true
        })
      });
      setActiveJob({ id: job.id, progress: 0.12, stage: `Renderizando gráfico (${selectedTemplate})...` });
    } catch (err) {
      notify(err.message, "error");
    }
  }

  async function handleStartFinalRender() {
    if (!currentProject) return;
    try {
      const job = await api(`/projects/${currentProject.id}/renders`, {
        method: "POST",
        body: JSON.stringify({ burn_subtitles: true, render_motion_overlays: true })
      });
      setActiveJob({ id: job.id, progress: 0.05, stage: "Renderizando MP4 a 60 FPS (NVENC)..." });
    } catch (err) {
      notify(err.message, "error");
    }
  }

  async function handleExportProject(target) {
    if (!currentProject) return;
    try {
      const res = await api(`/projects/${currentProject.id}/exports`, {
        method: "POST",
        body: JSON.stringify({ target })
      });
      notify(`Exportado (${target.toUpperCase()}): ${res.draft_dir || res.path}`, "ok");
    } catch (err) {
      notify(err.message, "error");
    }
  }

  async function handleCleanupTemp() {
    try {
      const res = await api("/system/cleanup-temp", { method: "POST" });
      notify(`Caché temporal limpia (${res.cleaned_items} elementos eliminados).`, "ok");
    } catch (err) {
      notify(err.message, "error");
    }
  }

  async function handleSaveSecret(provider) {
    const val = secretInputs[provider];
    if (!val) return;
    try {
      await api(`/providers/${provider}/secret`, {
        method: "PUT",
        body: JSON.stringify({ secret: val })
      });
      const provs = await api("/providers");
      setProviders(provs);
      setSecretInputs((p) => ({ ...p, [provider]: "" }));
      notify(`Credencial de ${provider} cifrada con DPAPI.`, "ok");
    } catch (err) {
      notify(err.message, "error");
    }
  }

  async function handleDeleteSecret(provider) {
    try {
      await api(`/providers/${provider}/secret`, { method: "DELETE" });
      const provs = await api("/providers");
      setProviders(provs);
      notify(`Credencial de ${provider} eliminada.`, "info");
    } catch (err) {
      notify(err.message, "error");
    }
  }

  // Derived state
  const wordCount = scriptData.text.trim() ? scriptData.text.trim().split(/\s+/).length : 0;
  const estSeconds = Math.max(1, Math.round(wordCount / 2.5));
  const visualAssets = assets.filter((a) => a.kind !== "audio");
  const filteredVisualAssets =
    mediaFilter === "all" ? visualAssets : visualAssets.filter((a) => a.kind === mediaFilter);
  const audioAssets = assets.filter((a) => a.kind === "audio");
  const latestRenderAsset = assets.filter((a) => a.kind === "render").slice(-1)[0];
  const activeVideoClip = timeline?.tracks
    ?.find((t) => t.kind === "video")
    ?.clips?.find((c) => playheadUs >= c.start_us && playheadUs <= c.start_us + c.duration_us);
  const firstVisualAsset =
    assets.find((a) => a.id === activeVideoClip?.asset_id) ||
    assets.find((a) => a.kind === "image" || a.kind === "video");

  const activeSubtitle =
    timeline?.tracks
      ?.find((t) => t.kind === "subtitle")
      ?.clips?.find((c) => playheadUs >= c.start_us && playheadUs <= c.start_us + c.duration_us)
      ?.subtitle?.text ||
    transcript?.segments?.[0]?.text ||
    "Subtítulos dinámicos ASS sincronizados a 60 FPS";

  return (
    <div className="macos-shell">
      {/* ====================================================================
          SIDEBAR (macOS / Arc / Linear Navigation)
         ==================================================================== */}
      <aside className="sidebar" aria-label="Navegación principal">
        <div className="sidebar-brand">
          <div className="brand-identity">
            <img src="/logo.png" alt="Logo" className="brand-logo-img" />
            <span className="brand-wordmark">CREATOR·IA</span>
          </div>
          <span className="brand-tag">2.0</span>
        </div>

        {/* Project Switcher Button */}
        <button
          type="button"
          className="project-switcher"
          onClick={() => setShowProjectModal(true)}
          title="Cambiar o crear proyecto"
        >
          <div className="project-switcher-info">
            <span className="project-switcher-label">Espacio de trabajo</span>
            <span className="project-switcher-name">
              {currentProject?.name || "Cargando..."}
            </span>
          </div>
          <ChevronDown size={14} color="var(--text-muted)" />
        </button>

        {/* Grouped Navigation */}
        <nav className="nav-groups">
          {NAV_GROUPS.map((group) => (
            <div key={group.label} className="nav-group">
              <div className="nav-group-label">{group.label}</div>
              {group.items.map((item) => {
                const Icon = item.icon;
                const isActive = activeTab === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    className={`nav-item ${isActive ? "active" : ""}`}
                    onClick={() => setActiveTab(item.id)}
                  >
                    <span className="nav-item-left">
                      <Icon size={15} className="nav-item-icon" />
                      <span>{item.label}</span>
                    </span>
                    <span className="nav-shortcut">{item.shortcut}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </nav>

        {/* Sidebar Footer: Hardware & Theme */}
        <div className="sidebar-footer">
          <div className="hw-status-row">
            <span style={{ display: "inline-flex", alignItems: "center", gap: 7 }}>
              <span className="status-dot" />
              <span>{hardware?.gpu?.name ? "NVIDIA NVENC" : "Motor Local"}</span>
            </span>
            <span className="mono" style={{ fontSize: 10, color: "var(--text-muted)" }}>
              60 FPS
            </span>
          </div>

          <div className="segmented-control" style={{ width: "100%" }}>
            <button
              type="button"
              className={`segment-btn ${theme === "dark" ? "active" : ""}`}
              style={{ flex: 1, justifyContent: "center" }}
              onClick={() => setTheme("dark")}
            >
              <Moon size={12} /> Oscuro
            </button>
            <button
              type="button"
              className={`segment-btn ${theme === "light" ? "active" : ""}`}
              style={{ flex: 1, justifyContent: "center" }}
              onClick={() => setTheme("light")}
            >
              <Sun size={12} /> Claro
            </button>
          </div>
        </div>
      </aside>

      {/* ====================================================================
          INSET WORKSPACE WINDOW
         ==================================================================== */}
      <div className="workspace-window">
        {/* Translucent Topbar */}
        <header className="window-topbar">
          <div className="topbar-breadcrumbs">
            <span className="crumb-project">{currentProject?.name || "Proyecto"}</span>
            <ChevronRight size={13} className="crumb-sep" />
            <span className="crumb-current">{VIEW_LABELS[activeTab]}</span>
            {currentProject?.canvas && (
              <span className="pill mono" style={{ marginLeft: 6 }}>
                {currentProject.canvas.width}×{currentProject.canvas.height} · {currentProject.canvas.fps?.num || 60}p
              </span>
            )}
          </div>

          <div className="topbar-right">
            {activeJob && (
              <div className="job-pill">
                <RefreshCw size={12} className="spin" />
                <span>{activeJob.stage}</span>
                <div className="job-bar">
                  <div
                    className="job-bar-fill"
                    style={{ width: `${Math.max(8, Math.round((activeJob.progress || 0.1) * 100))}%` }}
                  />
                </div>
                <button
                  type="button"
                  className="btn-ghost"
                  style={{ border: "none", background: "transparent", cursor: "pointer", padding: 2, color: "inherit" }}
                  onClick={handleCancelActiveJob}
                  title="Cancelar tarea"
                >
                  <X size={12} />
                </button>
              </div>
            )}

            <button type="button" className="btn btn-secondary btn-sm" onClick={handleAutopilot}>
              <Wand2 size={13} /> Autopilot 1-Click
            </button>
          </div>
        </header>

        {/* Scrollable View Content */}
        <main className="view-canvas">
          {/* ----------------------------------------------------------------
              1. GUION Y DIRECTOR (PROMPTS)
             ---------------------------------------------------------------- */}
          {activeTab === "prompts" && (
            <div className="view-container">
              <div className="page-header">
                <div className="page-header-copy">
                  <h1 className="page-title">Guion y Dirección Escénica</h1>
                  <p className="page-subtitle">
                    Redacta la narrativa principal. Utiliza <code className="mono">@Nombre</code> para fijar la identidad de personajes y cifras para disparar infografías automáticas.
                  </p>
                </div>
                <div className="page-actions">
                  <button type="button" className="btn btn-secondary" onClick={handleSaveScript}>
                    Guardar borrador
                  </button>
                  <button type="button" className="btn btn-primary" onClick={handleSegmentScript}>
                    <Sparkles size={14} /> Segmentar Escenas
                  </button>
                </div>
              </div>

              <div className="workspace-split">
                {/* Left Column: Editorial Script Writer */}
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
                  <div className="editorial-writer">
                    <div className="surface-header">
                      <span style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: "var(--text-secondary)" }}>
                        NARRATIVA DEL PROYECTO
                      </span>
                      <div style={{ display: "flex", gap: 6 }}>
                        {scriptData.characters?.map((ch) => (
                          <span key={ch.tag} className="pill pill-accent">
                            {ch.tag}
                          </span>
                        ))}
                      </div>
                    </div>

                    <textarea
                      className="editorial-textarea"
                      placeholder="Escribe o pega aquí el guion de tu vídeo..."
                      value={scriptData.text}
                      onChange={(e) => setScriptData({ ...scriptData, text: e.target.value })}
                    />

                    <div className="editorial-footer">
                      <div style={{ display: "flex", gap: 14 }}>
                        <span className="mono">{wordCount} palabras</span>
                        <span className="mono">~{estSeconds} s locución</span>
                      </div>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => setShowStyleDrawer((v) => !v)}
                      >
                        <SlidersHorizontal size={13} />
                        Dirección visual y @Personajes ({scriptData.characters?.length || 0})
                      </button>
                    </div>
                  </div>

                  {/* Collapsible Secondary Panel: Style Guide & Characters */}
                  {(showStyleDrawer || (scriptData.characters && scriptData.characters.length > 0)) && (
                    <div className="surface-panel">
                      <div className="field-group">
                        <label className="field-label">
                          <span>Guía de Estilo Fotográfico</span>
                          <span style={{ color: "var(--text-muted)" }}>Aplicada a todas las escenas</span>
                        </label>
                        <input
                          className="input"
                          value={styleGuide}
                          onChange={(e) => setStyleGuide(e.target.value)}
                          placeholder="Ej. Cinematográfico, lente 35mm, iluminación dramática..."
                        />
                      </div>

                      {scriptData.characters?.length > 0 && (
                        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                          <span className="field-label">Consistencia de Personajes (@tags)</span>
                          <div className="divided-list">
                            {scriptData.characters.map((ch, idx) => (
                              <div key={ch.tag} className="list-row" style={{ paddingLeft: 0, paddingRight: 0 }}>
                                <span className="pill pill-accent" style={{ marginTop: 4 }}>
                                  {ch.tag}
                                </span>
                                <div className="beat-body">
                                  <input
                                    className="input"
                                    value={ch.description}
                                    placeholder={`Rasgos visuales permanentes para ${ch.name}...`}
                                    onChange={(e) => {
                                      const next = [...scriptData.characters];
                                      next[idx] = { ...ch, description: e.target.value };
                                      setScriptData({ ...scriptData, characters: next });
                                    }}
                                  />
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Right Column: Hairline Beat Sequence */}
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
                  <div className="surface-header" style={{ paddingBottom: 4 }}>
                    <h2 className="section-title">
                      Secuencia de Escenas ({scriptData.beats?.length || 0})
                    </h2>
                    {scriptData.beats?.length > 0 && (
                      <button type="button" className="btn btn-secondary btn-sm" onClick={handleGenerateAllBeats}>
                        <ImageIcon size={13} /> Generar lote visual
                      </button>
                    )}
                  </div>

                  {!scriptData.beats || scriptData.beats.length === 0 ? (
                    <div className="empty-state">
                      <h3 className="empty-state-title">Sin escenas segmentadas</h3>
                      <p style={{ fontSize: "var(--text-sm)", maxWidth: 340 }}>
                        Pulsa «Segmentar Escenas» para dividir el guion en bloques visuales y extraer etiquetas de personajes.
                      </p>
                      <button type="button" className="btn btn-primary btn-sm" onClick={handleSegmentScript}>
                        Segmentar ahora
                      </button>
                    </div>
                  ) : (
                    <div className="divided-list">
                      {scriptData.beats.map((beat, idx) => (
                        <div key={beat.id || idx} className="list-row">
                          <span className="beat-index">
                            {String(idx + 1).padStart(2, "0")}
                          </span>
                          <div className="beat-body">
                            <p className="beat-narrative">{beat.text}</p>
                            <input
                              className="beat-prompt-input"
                              value={beat.visual_prompt}
                              title="Haz clic para editar el prompt visual de esta escena"
                              onChange={(e) => {
                                const next = [...scriptData.beats];
                                next[idx] = { ...beat, visual_prompt: e.target.value };
                                setScriptData({ ...scriptData, beats: next });
                              }}
                            />
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                              <span className="pill mono">{beat.media_kind?.toUpperCase() || "IMAGE"}</span>
                              {beat.tags?.map((t) => (
                                <span key={t} className="pill pill-accent">
                                  {t}
                                </span>
                              ))}
                            </div>
                          </div>
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm"
                            onClick={() => handleGenerateSingleBeat(beat, idx)}
                            title="Generar recurso visual para esta escena"
                          >
                            Generar
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* ----------------------------------------------------------------
              2. MULTIMEDIA (VISUAL ASSETS)
             ---------------------------------------------------------------- */}
          {activeTab === "multimedia" && (
            <div className="view-container">
              <div className="page-header">
                <div className="page-header-copy">
                  <h1 className="page-title">Biblioteca Multimedia</h1>
                  <p className="page-subtitle">
                    Recursos gráficos, clips de vídeo y capas animadas generadas o importadas en el espacio de trabajo.
                  </p>
                </div>
                <div className="page-actions">
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => setShowQuickGen((v) => !v)}
                  >
                    <Plus size={14} /> Creación rápida
                  </button>
                  <label className="btn btn-secondary" style={{ cursor: "pointer" }}>
                    <Upload size={14} /> Importar archivo
                    <input type="file" hidden onChange={handleUploadAsset} />
                  </label>
                  <button type="button" className="btn btn-primary" onClick={handleGenerateAllBeats}>
                    <Sparkles size={14} /> Generar escenas del guion
                  </button>
                </div>
              </div>

              {/* Optional Quick Single Asset Generator */}
              {showQuickGen && (
                <form className="surface-panel" onSubmit={handleQuickGenerate}>
                  <div className="surface-header">
                    <span className="section-title" style={{ fontSize: "var(--text-base)" }}>
                      Generar recurso individual
                    </span>
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => setShowQuickGen(false)}>
                      Cerrar
                    </button>
                  </div>
                  <div style={{ display: "flex", gap: 10 }}>
                    <select
                      className="select"
                      style={{ width: 150 }}
                      value={quickKind}
                      onChange={(e) => setQuickKind(e.target.value)}
                    >
                      <option value="image">Imagen 16:9</option>
                      <option value="video">Clip de Vídeo</option>
                    </select>
                    <input
                      className="input"
                      style={{ flex: 1 }}
                      placeholder="Describe la escena visual que deseas generar..."
                      value={quickPrompt}
                      onChange={(e) => setQuickPrompt(e.target.value)}
                    />
                    <button type="submit" className="btn btn-primary">
                      Generar
                    </button>
                  </div>
                </form>
              )}

              {/* Filter Bar */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                <div className="segmented-control">
                  <button
                    type="button"
                    className={`segment-btn ${mediaFilter === "all" ? "active" : ""}`}
                    onClick={() => setMediaFilter("all")}
                  >
                    Todos ({visualAssets.length})
                  </button>
                  <button
                    type="button"
                    className={`segment-btn ${mediaFilter === "image" ? "active" : ""}`}
                    onClick={() => setMediaFilter("image")}
                  >
                    Imágenes ({visualAssets.filter((a) => a.kind === "image").length})
                  </button>
                  <button
                    type="button"
                    className={`segment-btn ${mediaFilter === "video" ? "active" : ""}`}
                    onClick={() => setMediaFilter("video")}
                  >
                    Vídeos ({visualAssets.filter((a) => a.kind === "video").length})
                  </button>
                  <button
                    type="button"
                    className={`segment-btn ${mediaFilter === "motion" ? "active" : ""}`}
                    onClick={() => setMediaFilter("motion")}
                  >
                    Motion Alpha ({visualAssets.filter((a) => a.kind === "motion").length})
                  </button>
                </div>

                {visualAssets.length > 0 && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    style={{ color: "var(--status-danger)" }}
                    onClick={handleBatchDeleteVisualAssets}
                    title="Eliminar todas las imágenes y vídeos"
                  >
                    <Trash2 size={13} /> Vaciar multimedia
                  </button>
                )}
              </div>

              {filteredVisualAssets.length === 0 ? (
                <div className="empty-state">
                  <h3 className="empty-state-title">No hay recursos en esta vista</h3>
                  <p style={{ fontSize: "var(--text-sm)", maxWidth: 380 }}>
                    Importa imágenes o vídeos desde tu equipo, o genera automáticamente las escenas a partir del guion.
                  </p>
                  <div style={{ display: "flex", gap: 10, marginTop: 4 }}>
                    <label className="btn btn-secondary btn-sm" style={{ cursor: "pointer" }}>
                      Importar desde disco
                      <input type="file" hidden onChange={handleUploadAsset} />
                    </label>
                    <button type="button" className="btn btn-primary btn-sm" onClick={handleGenerateAllBeats}>
                      Generar desde el guion
                    </button>
                  </div>
                </div>
              ) : (
                <div className="media-gallery">
                  {filteredVisualAssets.map((a) => (
                    <div key={a.id} className="media-item">
                      <div className="media-frame">
                        <img
                          src={`/api/v1/assets/${a.id}/thumbnail`}
                          alt={a.name}
                          loading="lazy"
                        />
                      </div>
                      <div className="media-meta">
                        <span className="media-title" title={a.name}>
                          {a.name}
                        </span>
                        <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
                          <span className="pill mono">
                            {a.width ? `${a.width}×${a.height}` : a.kind.toUpperCase()}
                          </span>
                          <a
                            href={`/api/v1/assets/${a.id}/file`}
                            target="_blank"
                            rel="noreferrer"
                            className="btn btn-ghost btn-sm"
                            style={{ padding: "0 6px" }}
                            title="Abrir / Descargar archivo"
                          >
                            <Download size={12} />
                          </a>
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm"
                            style={{ padding: "0 6px", color: "var(--status-danger)" }}
                            onClick={(e) => handleDeleteAsset(a.id, a.name, e)}
                            title="Eliminar este recurso"
                          >
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ----------------------------------------------------------------
              3. LOCUCIÓN Y AUDIOLAB (AUDIOS)
             ---------------------------------------------------------------- */}
          {activeTab === "audios" && (
            <div className="view-container">
              <div className="page-header">
                <div className="page-header-copy">
                  <h1 className="page-title">Locución y Masterización</h1>
                  <p className="page-subtitle">
                    Síntesis de voz local en español y procesamiento acústico con estándar broadcast EBU R128.
                  </p>
                </div>
                <div className="page-actions">
                  <label className="btn btn-secondary" style={{ cursor: "pointer" }}>
                    <Upload size={14} /> Importar audio
                    <input type="file" accept="audio/*" hidden onChange={handleUploadAsset} />
                  </label>
                  <button type="button" className="btn btn-primary" onClick={handleGenerateTts}>
                    <Mic size={14} /> Sintetizar Locución
                  </button>
                </div>
              </div>

              {/* AudioLab Precision Strip */}
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
                <span className="field-label">HERRAMIENTAS DE MASTERIZACIÓN (AUDIOLAB)</span>
                <div className="audiolab-strip">
                  <button type="button" className="tool-tile" onClick={() => handleAudioLab("normalize")}>
                    <div className="tool-tile-title">
                      <Volume2 size={15} color="var(--accent)" />
                      <span>Normalizar Loudnorm</span>
                    </div>
                    <p className="tool-tile-desc">
                      Ajusta la sonoridad integrada a -14.0 LUFS para plataformas digitales.
                    </p>
                  </button>

                  <button type="button" className="tool-tile" onClick={() => handleAudioLab("trim_silence")}>
                    <div className="tool-tile-title">
                      <Scissors size={15} color="var(--accent)" />
                      <span>Recortar Silencios (VAD)</span>
                    </div>
                    <p className="tool-tile-desc">
                      Elimina pausas muertas al inicio, final y entre frases manteniendo cadencia natural.
                    </p>
                  </button>

                  <button type="button" className="tool-tile" onClick={() => handleAudioLab("join")}>
                    <div className="tool-tile-title">
                      <Layers size={15} color="var(--accent)" />
                      <span>Unir Pistas de Audio</span>
                    </div>
                    <p className="tool-tile-desc">
                      Concatena múltiples tomas del proyecto en una única pista maestra continua.
                    </p>
                  </button>
                </div>
              </div>

              <div className="workspace-split">
                {/* TTS Script Input */}
                <div className="surface-panel">
                  <div className="surface-header">
                    <h2 className="section-title">Texto de Locución</h2>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>Velocidad:</span>
                      <select
                        className="select"
                        style={{ width: 90, padding: "4px 8px", fontSize: "var(--text-xs)" }}
                        value={ttsSpeed}
                        onChange={(e) => setTtsSpeed(Number(e.target.value))}
                      >
                        <option value={0.9}>0.9×</option>
                        <option value={1.0}>1.0×</option>
                        <option value={1.1}>1.1×</option>
                      </select>
                    </div>
                  </div>
                  <textarea
                    className="textarea"
                    style={{ minHeight: 160 }}
                    value={scriptData.text}
                    onChange={(e) => setScriptData({ ...scriptData, text: e.target.value })}
                  />
                </div>

                {/* Audio Tracks List */}
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
                  <h2 className="section-title">Pistas en el Proyecto ({audioAssets.length})</h2>
                  {audioAssets.length === 0 ? (
                    <div className="empty-state">
                      <h3 className="empty-state-title">Sin pistas de audio</h3>
                      <p style={{ fontSize: "var(--text-sm)" }}>
                        Pulsa «Sintetizar Locución» o importa un archivo WAV/MP3.
                      </p>
                    </div>
                  ) : (
                    <div className="divided-list">
                      {audioAssets.map((a) => (
                        <div key={a.id} className="list-row" style={{ flexDirection: "column", gap: 10 }}>
                          <div style={{ display: "flex", justifyContent: "space-between", width: "100%", alignItems: "center" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <strong style={{ fontSize: "var(--text-sm)" }}>{a.name}</strong>
                              {currentProject?.narration_asset_id === a.id && (
                                <span className="pill pill-ok">Pista Maestra</span>
                              )}
                            </div>
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <span className="pill mono">{(a.duration_us / 1_000_000).toFixed(2)} s</span>
                              <button
                                type="button"
                                className="btn btn-ghost btn-sm"
                                style={{ color: "var(--status-danger)", padding: "0 6px" }}
                                onClick={(e) => handleDeleteAsset(a.id, a.name, e)}
                                title="Eliminar pista de audio"
                              >
                                <Trash2 size={12} />
                              </button>
                            </div>
                          </div>
                          <audio
                            controls
                            src={`/api/v1/assets/${a.id}/file`}
                            style={{ width: "100%", height: 34 }}
                          />
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* ----------------------------------------------------------------
              4. SINCRONIZACIÓN SRT Y MOTION GRAPHICS (SYNC)
             ---------------------------------------------------------------- */}
          {activeTab === "sync" && (
            <div className="view-container">
              <div className="page-header">
                <div className="page-header-copy">
                  <h1 className="page-title">Sincronización y Gráficos</h1>
                  <p className="page-subtitle">
                    Alineación forzada a nivel de palabra y renderizado de infografías animadas HTML/CSS/SVG con canal alfa.
                  </p>
                </div>
                <div className="page-actions">
                  <button type="button" className="btn btn-secondary" onClick={handleAlignTranscript}>
                    1. Alinear Palabras
                  </button>
                  <button type="button" className="btn btn-primary" onClick={handleAutoPlanTimeline}>
                    <Layers size={14} /> 2. Construir Timeline
                  </button>
                </div>
              </div>

              <div className="workspace-split">
                {/* Word-Level Alignment Map */}
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
                  <div className="surface-header">
                    <h2 className="section-title">Mapa Temporal de Palabras</h2>
                    {transcript && (
                      <div style={{ display: "flex", gap: 6 }}>
                        <span className="pill pill-ok mono">
                          {(transcript.duration_us / 1_000_000).toFixed(2)}s
                        </span>
                        <span className="pill mono">{transcript.words?.length || 0} palabras</span>
                      </div>
                    )}
                  </div>

                  {!transcript ? (
                    <div className="empty-state">
                      <h3 className="empty-state-title">Alineación pendiente</h3>
                      <p style={{ fontSize: "var(--text-sm)", maxWidth: 340 }}>
                        Una vez generada la locución, ejecuta «1. Alinear Palabras» para obtener las marcas de tiempo exactas.
                      </p>
                      <button type="button" className="btn btn-primary btn-sm" onClick={handleAlignTranscript}>
                        Alinear con el audio ahora
                      </button>
                    </div>
                  ) : (
                    <>
                      <div className="word-stream">
                        {transcript.words?.map((w) => (
                          <button
                            key={w.i}
                            type="button"
                            className="word-token"
                            onClick={() => setPlayheadUs(w.start_us)}
                            title={`${(w.start_us / 1_000_000).toFixed(2)}s → ${(w.end_us / 1_000_000).toFixed(2)}s`}
                          >
                            <span>{w.text}</span>
                            <span className="word-time">{(w.start_us / 1_000_000).toFixed(1)}s</span>
                          </button>
                        ))}
                      </div>
                      <div style={{ display: "flex", gap: 8 }}>
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => handleExportProject("srt")}>
                          Exportar .SRT
                        </button>
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => handleExportProject("ass")}>
                          Exportar Karaoke .ASS
                        </button>
                      </div>
                    </>
                  )}
                </div>

                {/* Motion Graphics Studio */}
                <div className="surface-panel">
                  <div className="surface-header">
                    <h2 className="section-title">Gráficos Animados (Alpha)</h2>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => setJsonMode((v) => !v)}
                    >
                      {jsonMode ? "Formulario" : "JSON"}
                    </button>
                  </div>

                  <div className="field-group">
                    <label className="field-label">Plantilla de Composición</label>
                    <select
                      className="select"
                      value={selectedTemplate}
                      onChange={(e) => handleSelectTemplate(e.target.value)}
                    >
                      {templates.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name} — {t.category}
                        </option>
                      ))}
                    </select>
                  </div>

                  {jsonMode ? (
                    <div className="field-group">
                      <label className="field-label">Parámetros JSON</label>
                      <textarea
                        className="textarea mono"
                        style={{ fontSize: "var(--text-xs)", minHeight: 150 }}
                        value={JSON.stringify(templateProps, null, 2)}
                        onChange={(e) => {
                          try {
                            setTemplateProps(JSON.parse(e.target.value));
                          } catch {}
                        }}
                      />
                    </div>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                      {Object.entries(templateProps).map(([key, val]) => (
                        <div key={key} className="field-group">
                          <label className="field-label" style={{ textTransform: "capitalize" }}>
                            {key.replace(/_/g, " ")}
                          </label>
                          {typeof val === "string" || typeof val === "number" ? (
                            <input
                              className="input"
                              value={val}
                              onChange={(e) =>
                                setTemplateProps({ ...templateProps, [key]: e.target.value })
                              }
                            />
                          ) : (
                            <input
                              className="input mono"
                              style={{ fontSize: "var(--text-xs)" }}
                              value={JSON.stringify(val)}
                              onChange={(e) => {
                                try {
                                  setTemplateProps({
                                    ...templateProps,
                                    [key]: JSON.parse(e.target.value)
                                  });
                                } catch {}
                              }}
                            />
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: 4 }}>
                    <button type="button" className="btn btn-primary" onClick={handleRenderMotionScene}>
                      <Sparkles size={14} /> Renderizar Overlay WebM Alpha
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ----------------------------------------------------------------
              5. EDITOR STUDIO (MONITOR & TIMELINE)
             ---------------------------------------------------------------- */}
          {activeTab === "studio" && (
            <div className="view-container">
              <div className="page-header">
                <div className="page-header-copy">
                  <h1 className="page-title">Estudio de Composición</h1>
                  <p className="page-subtitle">
                    Previsualización multipista con subtítulos ASS, codificación por hardware NVENC a 60 FPS y exportación nativa a CapCut.
                  </p>
                </div>
                <div className="page-actions">
                  <button type="button" className="btn btn-secondary" onClick={() => handleExportProject("capcut")}>
                    <FileCode2 size={14} /> Exportar a CapCut
                  </button>
                  <button type="button" className="btn btn-primary" onClick={handleStartFinalRender}>
                    <Play size={14} /> Renderizar Vídeo Final (MP4)
                  </button>
                </div>
              </div>

              <div className="studio-upper">
                {/* 16:9 Cinema Monitor */}
                <div className="cinema-stage-wrapper">
                  <div className="cinema-monitor">
                    {latestRenderAsset ? (
                      <video
                        controls
                        src={`/api/v1/assets/${latestRenderAsset.id}/file`}
                        style={{ width: "100%", height: "100%" }}
                      />
                    ) : firstVisualAsset ? (
                      <>
                        <img
                          src={`/api/v1/assets/${firstVisualAsset.id}/file`}
                          alt="Monitor Preview"
                          style={{ width: "100%", height: "100%", objectFit: "cover" }}
                        />
                        <div className="cinema-subtitle-overlay">{activeSubtitle}</div>
                      </>
                    ) : (
                      <div className="cinema-subtitle-overlay">{activeSubtitle}</div>
                    )}
                  </div>

                  <div className="transport-bar">
                    <span className="mono" style={{ fontSize: "var(--text-xs)", minWidth: 110 }}>
                      {(playheadUs / 1_000_000).toFixed(2)}s / {((timeline?.duration_us || 6000000) / 1_000_000).toFixed(2)}s
                    </span>
                    <input
                      type="range"
                      className="scrubber-input"
                      min={0}
                      max={timeline?.duration_us || 6000000}
                      value={playheadUs}
                      onChange={(e) => setPlayheadUs(Number(e.target.value))}
                    />
                    <span className="pill mono">ASS Karaoke</span>
                  </div>
                </div>

                {/* Delivery & Export Inspector */}
                <div className="surface-panel">
                  <h2 className="section-title">Entrega y Exportación</h2>

                  <div className="divided-list">
                    <div className="list-row" style={{ paddingLeft: 0, paddingRight: 0 }}>
                      <div className="beat-body">
                        <strong style={{ fontSize: "var(--text-sm)" }}>CapCut Desktop Draft</strong>
                        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
                          Genera draft_content.json con pistas editables
                        </span>
                      </div>
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => handleExportProject("capcut")}>
                        Exportar
                      </button>
                    </div>

                    <div className="list-row" style={{ paddingLeft: 0, paddingRight: 0 }}>
                      <div className="beat-body">
                        <strong style={{ fontSize: "var(--text-sm)" }}>OpenTimelineIO (.otio)</strong>
                        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
                          Intercambio estándar para DaVinci Resolve / Premiere
                        </span>
                      </div>
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => handleExportProject("otio")}>
                        Exportar
                      </button>
                    </div>

                    <div className="list-row" style={{ paddingLeft: 0, paddingRight: 0 }}>
                      <div className="beat-body">
                        <strong style={{ fontSize: "var(--text-sm)" }}>Subtítulos (.ASS y .SRT)</strong>
                        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
                          Karaoke dinámico por palabra y subtítulo estándar
                        </span>
                      </div>
                      <div style={{ display: "flex", gap: 6 }}>
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => handleExportProject("srt")}>
                          .SRT
                        </button>
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => handleExportProject("ass")}>
                          .ASS
                        </button>
                      </div>
                    </div>
                  </div>

                  {latestRenderAsset && (
                    <div
                      style={{
                        padding: 14,
                        borderRadius: "var(--radius-sm)",
                        background: "var(--status-ok-bg)",
                        border: "1px solid rgba(16, 185, 129, 0.25)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: 12
                      }}
                    >
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: "var(--status-ok)" }}>
                          ÚLTIMO RENDER DISPONIBLE
                        </div>
                        <div
                          className="mono"
                          style={{
                            fontSize: "var(--text-xs)",
                            color: "var(--text-primary)",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap"
                          }}
                        >
                          {latestRenderAsset.name} ({(latestRenderAsset.duration_us / 1_000_000).toFixed(2)}s)
                        </div>
                      </div>
                      <a
                        className="btn btn-primary btn-sm"
                        href={`/api/v1/assets/${latestRenderAsset.id}/file`}
                        download={latestRenderAsset.name}
                        style={{ textDecoration: "none" }}
                      >
                        <Download size={13} /> Descargar
                      </a>
                    </div>
                  )}
                </div>
              </div>

              {/* Precision Multi-Track Timeline */}
              <div className="timeline-dock">
                <div className="timeline-dock-header">
                  <span className="section-title" style={{ fontSize: "var(--text-base)" }}>
                    Línea de Tiempo Multipista
                  </span>
                  <span className="pill mono">
                    Duración Total: {((timeline?.duration_us || 0) / 1_000_000).toFixed(2)} s
                  </span>
                </div>

                {!timeline?.tracks || timeline.tracks.length === 0 ? (
                  <div style={{ padding: "var(--space-6)", textAlign: "center", color: "var(--text-muted)", fontSize: "var(--text-sm)" }}>
                    La línea de tiempo está vacía. Ve a «Sincronización SRT» y pulsa «Construir Timeline» o usa «Autopilot 1-Click».
                  </div>
                ) : (
                  timeline.tracks.map((trk) => (
                    <div key={trk.id} className="track-lane">
                      <div className="track-label-col">
                        <span className="track-name">{trk.name}</span>
                        <span className="track-meta">
                          {trk.kind.toUpperCase()} · {trk.clips?.length || 0} clips
                        </span>
                      </div>
                      <div className="track-clips-strip">
                        {trk.clips?.map((c) => {
                          const isCurrent =
                            playheadUs >= c.start_us && playheadUs <= c.start_us + c.duration_us;
                          return (
                            <div
                              key={c.id}
                              className={`timeline-clip ${isCurrent ? "active-clip" : ""}`}
                              onClick={() => setPlayheadUs(c.start_us)}
                            >
                              <div className="clip-title">
                                {c.motion?.template_id || c.subtitle?.text || c.id}
                              </div>
                              <div className="clip-time">
                                {(c.start_us / 1_000_000).toFixed(2)}s · {(c.duration_us / 1_000_000).toFixed(2)}s
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {/* ----------------------------------------------------------------
              6. PROYECTOS (FILES)
             ---------------------------------------------------------------- */}
          {activeTab === "files" && (
            <div className="view-container">
              <div className="page-header">
                <div className="page-header-copy">
                  <h1 className="page-title">Espacios de Trabajo</h1>
                  <p className="page-subtitle">
                    Proyectos locales autocontenidos (<code className="mono">.vfproj</code>) con activos, transcripciones y borradores de exportación.
                  </p>
                </div>
                <div className="page-actions">
                  <button type="button" className="btn btn-primary" onClick={() => setShowProjectModal(true)}>
                    <FolderPlus size={14} /> Nuevo Proyecto
                  </button>
                </div>
              </div>

              <div className="divided-list">
                {projects.map((p) => {
                  const isCurrent = p.id === currentProject?.id;
                  return (
                    <div
                      key={p.id}
                      className="list-row"
                      style={{ cursor: "pointer", alignItems: "center" }}
                      onClick={() => selectProject(p)}
                    >
                      <div className="beat-body">
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <strong style={{ fontSize: "var(--text-md)" }}>{p.name}</strong>
                          {isCurrent && <span className="pill pill-ok">Activo</span>}
                        </div>
                        <div style={{ display: "flex", gap: 16, fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
                          <span className="mono">
                            {p.canvas?.width}×{p.canvas?.height} · {p.canvas?.fps?.num || 60} FPS
                          </span>
                          <span>Actualizado: {new Date(p.updated_at || p.created_at).toLocaleString()}</span>
                        </div>
                      </div>

                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        {!isCurrent && (
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              selectProject(p);
                            }}
                          >
                            Abrir
                          </button>
                        )}
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={(e) => handleDeleteProject(p.id, p.name, e)}
                          title="Eliminar proyecto"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* ----------------------------------------------------------------
              7. PREFERENCIAS DEL SISTEMA (SETTINGS)
             ---------------------------------------------------------------- */}
          {activeTab === "settings" && (
            <div className="view-container">
              <div className="page-header">
                <div className="page-header-copy">
                  <h1 className="page-title">Preferencias del Sistema</h1>
                  <p className="page-subtitle">
                    Apariencia de la interfaz, telemetría de aceleración por hardware y bóveda local cifrada con Windows DPAPI.
                  </p>
                </div>
                <div className="page-actions">
                  <button type="button" className="btn btn-secondary" onClick={handleCleanupTemp}>
                    Limpiar caché temporal
                  </button>
                </div>
              </div>

              <div className="workspace-split">
                {/* Left Column: Appearance & Hardware */}
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-6)" }}>
                  <div className="surface-panel">
                    <h2 className="section-title">Apariencia</h2>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <div>
                        <div style={{ fontWeight: 500, fontSize: "var(--text-sm)" }}>Tema de color</div>
                        <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
                          Adapta la superficie del estudio a la iluminación de tu entorno
                        </div>
                      </div>
                      <div className="segmented-control">
                        <button
                          type="button"
                          className={`segment-btn ${theme === "dark" ? "active" : ""}`}
                          onClick={() => setTheme("dark")}
                        >
                          <Moon size={13} /> Oscuro Grafito
                        </button>
                        <button
                          type="button"
                          className={`segment-btn ${theme === "light" ? "active" : ""}`}
                          onClick={() => setTheme("light")}
                        >
                          <Sun size={13} /> Claro Alabastro
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="surface-panel">
                    <h2 className="section-title">Motor de Hardware</h2>
                    {hardware && (
                      <div className="divided-list">
                        <div className="list-row" style={{ paddingLeft: 0, paddingRight: 0 }}>
                          <span style={{ color: "var(--text-secondary)", fontSize: "var(--text-sm)" }}>
                            Unidad Gráfica (GPU)
                          </span>
                          <strong className="mono" style={{ fontSize: "var(--text-xs)" }}>
                            {hardware.gpu ? `${hardware.gpu.name} (${hardware.gpu.vram})` : "CPU Fallback"}
                          </strong>
                        </div>
                        <div className="list-row" style={{ paddingLeft: 0, paddingRight: 0 }}>
                          <span style={{ color: "var(--text-secondary)", fontSize: "var(--text-sm)" }}>
                            Codificador de Vídeo
                          </span>
                          <span className="pill pill-ok mono">{hardware.preferred_encoder}</span>
                        </div>
                        <div className="list-row" style={{ paddingLeft: 0, paddingRight: 0 }}>
                          <span style={{ color: "var(--text-secondary)", fontSize: "var(--text-sm)" }}>
                            Procesador y Memoria
                          </span>
                          <span className="mono" style={{ fontSize: "var(--text-xs)" }}>
                            {hardware.cpu_cores_physical}C / {hardware.cpu_cores_logical}T · {hardware.ram_total_gb} GB RAM
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Right Column: Encrypted API Vault */}
                <div className="surface-panel">
                  <div>
                    <h2 className="section-title">Bóveda de Proveedores Externos</h2>
                    <p style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", marginTop: 4 }}>
                      El motor funciona 100% en local sin claves externas. Si deseas conectar APIs opcionales, se almacenan cifradas con DPAPI + AES-256-GCM.
                    </p>
                  </div>

                  <div className="divided-list">
                    {providers.map((p) => (
                      <div key={p.provider} className="list-row" style={{ flexDirection: "column", gap: 8, paddingLeft: 0, paddingRight: 0 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", width: "100%", alignItems: "center" }}>
                          <strong className="mono" style={{ fontSize: "var(--text-xs)", textTransform: "uppercase" }}>
                            {p.provider}
                          </strong>
                          {p.configured ? (
                            <span className="pill pill-ok mono">
                              <Check size={11} /> Configurada (••{p.last4})
                            </span>
                          ) : (
                            <span className="pill">Modo Local</span>
                          )}
                        </div>
                        <div style={{ display: "flex", gap: 8, width: "100%" }}>
                          <input
                            type="password"
                            className="input"
                            style={{ fontSize: "var(--text-xs)", padding: "6px 10px" }}
                            placeholder={`Introducir clave para ${p.provider}...`}
                            value={secretInputs[p.provider] || ""}
                            onChange={(e) =>
                              setSecretInputs({ ...secretInputs, [p.provider]: e.target.value })
                            }
                          />
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => handleSaveSecret(p.provider)}
                          >
                            Guardar
                          </button>
                          {p.configured && (
                            <button
                              type="button"
                              className="btn btn-ghost btn-sm"
                              onClick={() => handleDeleteSecret(p.provider)}
                              title="Eliminar credencial"
                            >
                              <Trash2 size={13} />
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* ====================================================================
          MODAL: SWITCH OR CREATE PROJECT (Replaces browser window.prompt)
         ==================================================================== */}
      {showProjectModal && (
        <div className="modal-backdrop" onClick={() => setShowProjectModal(false)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="surface-header">
              <h2 className="section-title">Espacios de Trabajo</h2>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setShowProjectModal(false)}>
                <X size={14} />
              </button>
            </div>

            {/* Quick Switch Existing */}
            {projects.length > 0 && (
              <div className="field-group">
                <label className="field-label">Cambiar a proyecto existente</label>
                <div className="divided-list" style={{ maxHeight: 160, overflowY: "auto" }}>
                  {projects.map((p) => (
                    <div
                      key={p.id}
                      className="list-row"
                      style={{ cursor: "pointer", padding: "8px 6px", alignItems: "center" }}
                      onClick={() => {
                        selectProject(p);
                        setShowProjectModal(false);
                      }}
                    >
                      <span style={{ fontWeight: p.id === currentProject?.id ? 600 : 400, fontSize: "var(--text-sm)" }}>
                        {p.name}
                      </span>
                      {p.id === currentProject?.id && <span className="pill pill-ok">Activo</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Create New Project Form */}
            <form onSubmit={handleCreateProjectSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div className="field-group">
                <label className="field-label">Crear nuevo proyecto</label>
                <input
                  className="input"
                  placeholder="Nombre del proyecto..."
                  value={newProjName}
                  onChange={(e) => setNewProjName(e.target.value)}
                  autoFocus
                />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 10 }}>
                <div className="field-group">
                  <label className="field-label">Formato de Lienzo</label>
                  <select
                    className="select"
                    value={newProjPreset}
                    onChange={(e) => setNewProjPreset(e.target.value)}
                  >
                    <option value="1080p_landscape">1920×1080 (Horizontal 16:9)</option>
                    <option value="1080p_vertical">1080×1920 (Vertical 9:16)</option>
                    <option value="720p_landscape">1280×720 (HD Ligero)</option>
                  </select>
                </div>

                <div className="field-group">
                  <label className="field-label">Cadencia</label>
                  <select
                    className="select"
                    value={newProjFps}
                    onChange={(e) => setNewProjFps(Number(e.target.value))}
                  >
                    <option value={60}>60 FPS</option>
                    <option value={30}>30 FPS</option>
                  </select>
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, paddingTop: 6 }}>
                <button type="button" className="btn btn-ghost" onClick={() => setShowProjectModal(false)}>
                  Cancelar
                </button>
                <button type="submit" className="btn btn-primary">
                  Crear proyecto
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ====================================================================
          FLOATING NOTIFICATION TOAST
         ==================================================================== */}
      {toast && (
        <div className="floating-toast" role="status">
          {toast.type === "ok" ? (
            <CheckCircle2 size={16} color="var(--status-ok)" />
          ) : toast.type === "error" ? (
            <AlertCircle size={16} color="var(--status-danger)" />
          ) : (
            <Sparkles size={16} color="var(--accent)" />
          )}
          <span>{toast.message}</span>
          <button
            type="button"
            className="btn-ghost"
            style={{ border: "none", background: "transparent", cursor: "pointer", padding: 2, color: "var(--text-muted)" }}
            onClick={() => setToast(null)}
          >
            <X size={13} />
          </button>
        </div>
      )}
    </div>
  );
}
