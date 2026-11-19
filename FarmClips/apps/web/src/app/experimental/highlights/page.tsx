"use client";

import { useEffect, useRef, useState } from "react";
import { API_PREFIX } from "@/lib/api/client";

const base = API_PREFIX + "/experimental/highlights/v1";
type Variant = "v1" | "v2";
type Bounds = [number, number];
type Job = { id: string; source: string; state: string; error?: string; elapsed?: number };
type Review = {
  seq: number;
  payload: { decision: string; notes: string; version: Variant; category?: string; segment?: { start: number; end: number } };
};
type HistoricalReview = {
  seq: number;
  provenance: "revision_exportada_v1" | "revision_exportada_v2";
  payload: { decision?: string; decision_v2?: string; nota_revision?: string };
};
type Candidate = {
  id: string; inicio_seg: number; fin_seg: number; v2_cut: Bounds; intervalo_v1_seg?: Bounds;
  puesto: number; puntuacion: number; tipo_momento: string; explicacion: string; confianza: string;
  senales: Record<string, number>; review?: Review; group?: { members: string[] };
  factores?: Record<string, number>; evidencia: { seg_solicitado: number; examinada_por_gpt: boolean }[];
  corte?: { metodo: string; justificacion?: string };
  ajuste_personalizado?: number;
  puesto_personalizado?: number;
};
type Result = {
  rows: Candidate[]; total: number; visible_groups: number; hidden_candidates: number;
  frozen?: Record<string, unknown>; duration: number; coverage: Record<string, string | null>;
};
type Profile = { id: string; weights: Record<string, number> };

async function api<T>(suffix: string, body?: object): Promise<T> {
  const res = await fetch(base + suffix, body ? {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  } : { cache: "no-store" });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    throw new Error(typeof payload.detail === "string" ? payload.detail : `Solicitud rechazada (${res.status})`);
  }
  return res.json();
}

const categoryNames: Record<string, string> = {
  cambio_visual_y_acustico: "Cambio de imagen y sonido", cambio_visual: "Cambio de imagen",
  actividad_acustica: "Actividad sonora",
};
const categories = ["llamada", "humor", "susto", "historia", "combate", "tarea", "resultado", "otro"];
const button = "rounded-md border border-current px-3 py-1.5 disabled:opacity-40";
const input = "rounded-md border border-[var(--color-border-default)] bg-[var(--color-background-body)] px-2 py-1.5";

export default function Highlights() {
  const [sources, setSources] = useState<string[]>([]);
  const [source, setSource] = useState("");
  const [runs, setRuns] = useState<Job[]>([]);
  const [job, setJob] = useState<Job>();
  const [fresh, setFresh] = useState(false);
  const [ranking, setRanking] = useState<Variant>("v1");
  const [variant, setVariant] = useState<Variant>("v1");
  const [budget, setBudget] = useState(12);
  const [all, setAll] = useState(false);
  const [result, setResult] = useState<Result>();
  const [selected, setSelected] = useState("");
  const [history, setHistory] = useState<Review[]>([]);
  const [historical, setHistorical] = useState<HistoricalReview[]>([]);
  const [importCount, setImportCount] = useState(0);
  const [decision, setDecision] = useState("interesante");
  const [category, setCategory] = useState("");
  const [notes, setNotes] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profile, setProfile] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const [preview, setPreview] = useState<Bounds>();
  const row = result?.rows.find(candidate => candidate.id === selected);
  const bounds = row && (variant === "v2" ? row.v2_cut : row.intervalo_v1_seg ?? [row.inicio_seg, row.fin_seg]);
  const root = job ? "/runs/" + job.id : "";
  const jobState = job?.state;

  function failure(err: unknown) {
    setError(err instanceof Error ? err.message : String(err));
  }

  useEffect(() => {
    api<{ sources: string[] }>("/sources").then(data => {
      setSources(data.sources);
      setSource(data.sources[0] || "");
      return Promise.all([api<Job[]>("/runs").then(setRuns), api<Profile[]>("/profiles").then(setProfiles)]);
    }).catch(failure);
  }, []);

  useEffect(() => {
    if (jobState !== "RUNNING") return;
    const timer = setInterval(() => api<Job>(root).then(setJob).catch(failure), 1500);
    return () => clearInterval(timer);
  }, [root, jobState]);

  useEffect(() => {
    if (jobState !== "DONE") return;
    let stale = false;
    const search = new URLSearchParams({ ranking, budget: String(budget), show_all: String(all) });
    if (profile) search.set("profile", profile);
    api<Result>(root + "/candidates?" + search).then(data => {
      if (stale) return;
      setResult(data);
      setSelected(id => data.rows.some(item => item.id === id) ? id : data.rows[0]?.id || "");
    }).catch(err => { if (!stale) failure(err); });
    return () => { stale = true; };
  }, [root, jobState, ranking, budget, all, profile]);

  function fill(review?: Review) {
    setDecision(review?.payload.decision ?? "interesante");
    setNotes(review?.payload.notes ?? "");
    setCategory(review?.payload.category ?? "");
    setStart(review?.payload.segment?.start.toString() ?? "");
    setEnd(review?.payload.segment?.end.toString() ?? "");
  }

  useEffect(() => {
    setPreview(undefined);
    setHistory([]);
    setHistorical([]);
    fill();
    if (!selected || jobState !== "DONE") return;
    let stale = false;
    Promise.all([
      api<Review[]>(root + "/history/" + selected),
      api<HistoricalReview[]>("/feedback?candidate=" + encodeURIComponent(selected)),
    ]).then(([data, imported]) => {
      if (stale) return;
      setHistory(data);
      setHistorical(imported);
      if (data.length) {
        const last = data[data.length - 1];
        fill(last);
        setVariant(last.payload.version);
      }
    }).catch(err => { if (!stale) failure(err); });
    return () => { stale = true; };
  }, [root, selected, jobState, importCount]);

  async function perform(action: () => Promise<void>) {
    setError("");
    setMessage("");
    setBusy(true);
    try { await action(); } catch (err) { failure(err); } finally { setBusy(false); }
  }

  function choose(job: Job) {
    setSelected("");
    setResult(undefined);
    setJob(job);
  }

  function play(interval: Bounds) {
    if (!video.current) return;
    if (interval[1] - interval[0] > 180) {
      setError("Para previsualizar, selecciona un tramo de hasta 180 segundos.");
      return;
    }
    const url = base + root + "/preview?" + new URLSearchParams({
      start: String(interval[0]), end: String(interval[1]),
    });
    setPreview(interval);
    if (video.current.getAttribute("src") !== url) video.current.src = url;
    video.current.currentTime = 0;
    video.current.play().catch(err => {
      if (err instanceof DOMException && err.name === "AbortError") return;
      failure(err);
    });
  }

  return (
    <main className="mx-auto max-w-7xl space-y-5 px-5 py-6">
      <h1 className="text-2xl font-semibold">Revisión experimental de highlights</h1>
      <div className="flex flex-wrap items-center gap-3">
        <label>VOD <select className={input} value={source} onChange={e => setSource(e.target.value)}>
          {sources.map(name => <option key={name}>{name}</option>)}
        </select></label>
        <label><input type="checkbox" checked={fresh} onChange={e => setFresh(e.target.checked)} /> Calcular desde el VOD</label>
        <button className={button} disabled={!source || busy || jobState === "RUNNING"} onClick={() => perform(async () => {
          const run = await api<Job>("/runs", { source, fresh });
          choose(run);
          setRuns(previous => [run, ...previous.filter(item => item.id !== run.id)]);
        })}>Analizar VOD</button>
        {!!runs.length && <label>Ejecución <select className={input} value={job?.id ?? ""} onChange={e => perform(async () => choose(await api<Job>("/runs/" + e.target.value)))}>
          <option disabled value="">Abrir historial</option>
          {runs.map(run => <option value={run.id} key={run.id}>{run.source} · {run.id.slice(0, 8)}</option>)}
        </select></label>}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button className={button} disabled={busy} onClick={() => perform(async () => {
          const report = await api<{ imported: number; available: number }>("/feedback/import", {});
          setImportCount(count => count + 1);
          setMessage(`Registros históricos nuevos: ${report.imported} de ${report.available}.`);
        })}>Importar feedback histórico</button>
        <button className={button} disabled={busy} onClick={() => perform(async () => {
          const created = await api<Profile & { reason?: string }>("/profiles", {});
          if (!created.id) { setMessage(created.reason || "Baseline disponible."); return; }
          setProfiles(await api<Profile[]>("/profiles"));
          setProfile(created.id);
          setMessage("Perfil guardado para comparación. Alcance: candidatos ya categorizados.");
        })}>Previsualizar calibración</button>
        <label>Perfil <select className={input} value={profile} onChange={e => setProfile(e.target.value)}>
          <option value="">Baseline</option>
          {profiles.map(item => <option key={item.id} value={item.id}>{item.id.slice(0, 8)} · {Object.keys(item.weights).join(", ")}</option>)}
        </select></label>
      </div>
      {error && <p role="alert" className="text-red-400">{error}</p>}
      {message && <p role="status">{message}</p>}
      {jobState === "RUNNING" && <p role="status">Analizando el VOD. El estado se actualiza automáticamente.</p>}
      {jobState === "FAILED" && <p role="alert">{job?.error}</p>}
      {result && <div className="grid gap-5 lg:grid-cols-[minmax(250px,1fr)_minmax(0,2fr)]">
        <section className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <label>Ranking <select aria-label="Ranking" value={ranking} className={input} onChange={e => setRanking(e.target.value as Variant)}>
              <option value="v1">V1</option><option value="v2">V2 experimental</option>
            </select></label>
            <label>Grupos/hora <input className={input + " w-20"} type="number" min="0" max="120" value={budget}
              onChange={e => setBudget(Math.max(0, Math.min(120, parseInt(e.target.value, 10) || 0)))} /></label>
            <label><input type="checkbox" checked={all} onChange={e => setAll(e.target.checked)} /> Ver todos</label>
          </div>
          <p>{result.total} candidatos · {result.visible_groups} grupos visibles · {result.hidden_candidates} fuera del presupuesto</p>
          <p>{result.frozen ? "Resultados congelados verificados por hash" : "Cálculo local"}{job?.elapsed != null && ` · ${job.elapsed.toFixed(1)} s`}</p>
          <ul className="max-h-[65vh] space-y-2 overflow-auto">
            {result.rows.map(item => <li key={item.id}>
              <button type="button" disabled={busy} aria-pressed={selected === item.id} className={button + " w-full text-left"}
                onClick={() => { setSelected(item.id); setVariant("v1"); }}>
                #{item.puesto_personalizado ?? item.puesto} · {(item.intervalo_v1_seg?.[0] ?? item.inicio_seg).toFixed(1)} s · {categoryNames[item.tipo_momento] || item.tipo_momento}
                {item.group && item.group.members.length > 1 ? ` (+${item.group.members.length - 1} solapados)` : ""}
                {item.review ? " · Revisado" : ""}
              </button>
            </li>)}
          </ul>
          <a className="underline" href={base + root + "/export"} download="farmclips-highlights-v1.json">Exportar candidatos y revisiones</a>
        </section>
        {row && bounds && <section className="min-w-0 space-y-4">
          <video ref={video} key={job?.id + selected} controls preload="none"
            className="aspect-video w-full rounded-lg bg-black" />
          {preview && <p>Vista previa de {preview[0]}–{preview[1]} s del VOD</p>}
          <a className="underline" href={base + root + "/media"} target="_blank" rel="noreferrer">Abrir el VOD completo</a>
          <div className="flex flex-wrap gap-2">
            {(["v1", "v2"] as const).map(value => {
              const cut: Bounds = value === "v2" ? row.v2_cut : row.intervalo_v1_seg ?? [row.inicio_seg, row.fin_seg];
              return <button key={value} className={button} aria-pressed={variant === value} onClick={() => {
                setVariant(value); play(cut);
              }}>Corte {value.toUpperCase()} · {cut[0]}–{cut[1]} s</button>;
            })}
          </div>
          <details open><summary>Señales y evidencia</summary>
            <p>{row.explicacion} · {row.puntuacion.toFixed(3)} · {row.confianza.replaceAll("_", " ")}</p>
            {row.ajuste_personalizado != null && <p>Ajuste del perfil {row.ajuste_personalizado.toFixed(4)} · puesto base {row.puesto}</p>}
            <p>{result.coverage.audio} · {result.coverage.video}. Diálogo y narrativa sin análisis en esta ejecución.</p>
            {row.corte?.justificacion && <p>{row.corte.justificacion}</p>}
            <dl>{Object.entries({ ...row.senales, ...row.factores }).map(([key, value]) =>
              <div key={key} className="flex gap-2"><dt>{key.replaceAll("_", " ")}</dt><dd>{value.toFixed(3)}</dd></div>)}</dl>
            <div className="flex flex-wrap gap-2">
              {row.evidencia.map(point => <button type="button" className={button} key={point.seg_solicitado}
                onClick={() => {
                  play([point.seg_solicitado, Math.min(result.duration, point.seg_solicitado + 2)]);
                }}>Ver evidencia a {point.seg_solicitado} s</button>)}
            </div>
          </details>
          <form className="space-y-3" onSubmit={event => {
            event.preventDefault();
            void perform(async () => {
              if ((start === "") !== (end === "")) throw new Error("Completa ambos límites o déjalos vacíos.");
              await api(root + "/reviews/" + row.id, {
                decision, category: category || null, notes, version: variant,
                segment: start === "" ? null : { start: Number(start), end: Number(end) },
                expected: history[history.length - 1]?.seq ?? null, operation: crypto.randomUUID(),
              });
              const data = await api<Review[]>(root + "/history/" + row.id);
              setHistory(data);
              setResult(current => current && ({ ...current, rows: current.rows.map(item =>
                item.id === row.id ? { ...item, review: data[data.length - 1] } : item) }));
              setMessage("Revisión guardada.");
            });
          }}>
            <div className="flex flex-wrap items-center gap-2">
              <label>Decisión <select value={decision} className={input} onChange={e => setDecision(e.target.value)}>
                <option value="interesante">Interesante</option><option value="no_interesante">No interesante</option><option value="dudoso">Dudoso</option>
              </select></label>
              <label>Categoría <select value={category} className={input} onChange={e => setCategory(e.target.value)}>
                <option value="">Sin categoría editorial</option>{categories.map(item => <option key={item}>{item}</option>)}
              </select></label>
              <label>Variante <select value={variant} className={input} onChange={e => setVariant(e.target.value as Variant)}>
                <option value="v1">V1</option><option value="v2">V2</option>
              </select></label>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <label>Inicio corregido <input className={input + " w-24"} value={start} type="number" min="0" max={result.duration} step="any" placeholder={String(bounds[0])} onChange={e => setStart(e.target.value)} /></label>
              <label>Fin corregido <input className={input + " w-24"} value={end} type="number" min="0" max={result.duration} step="any" placeholder={String(bounds[1])} onChange={e => setEnd(e.target.value)} /></label>
              <button className={button} type="button" disabled={start === "" || end === "" || Number(end) <= Number(start)}
                onClick={() => play([Number(start), Number(end)])}>Probar ajuste</button>
            </div>
            <label className="block">Nota <textarea className={input + " block w-full"} value={notes} maxLength={3000} onChange={e => setNotes(e.target.value)} /></label>
            <button className={button} disabled={busy}>Guardar revisión</button>
          </form>
          {historical.length > 0 && <details open><summary>Decisiones históricas importadas</summary>
            <ul>{historical.map(item => <li key={item.seq}>
              {item.provenance.endsWith("v1") ? "V1" : "V2"} · {(item.payload.decision_v2 ?? item.payload.decision)?.replaceAll("_", " ")}
              {item.payload.nota_revision && ` · ${item.payload.nota_revision}`}
            </li>)}</ul>
          </details>}
          <details><summary>Historial ({history.length})</summary>
            <ul>{history.map(item => <li key={item.seq}>
              {item.payload.version.toUpperCase()} · {item.payload.decision.replaceAll("_", " ")}
              {item.payload.segment ? ` · ${item.payload.segment.start}–${item.payload.segment.end} s` : ""} {item.payload.notes}
            </li>)}</ul>
          </details>
        </section>}
      </div>}
    </main>
  );
}
