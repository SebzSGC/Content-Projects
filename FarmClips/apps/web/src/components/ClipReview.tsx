"use client";

import { useState, type FormEvent } from "react";
import { API_PREFIX, type ClipItem } from "@/lib/api/client";
import { btnSecondary, inputBase } from "@/components/ui";

type Decision = "interesante" | "no_interesante" | "dudoso";
type Revision = {
  seq: number;
  payload: { decision: Decision; category?: string; notes: string; proposal: [number, number] };
};
const labels: Record<Decision, string> = {
  interesante: "Interesante",
  no_interesante: "No interesante",
  dudoso: "Dudoso",
};
const categories = ["llamada", "humor", "susto", "historia", "combate", "tarea", "resultado", "otro"];

export function ClipReview({ clip }: { clip: ClipItem }) {
  const [history, setHistory] = useState<Revision[]>();
  const [decision, setDecision] = useState<Decision>("interesante");
  const [category, setCategory] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const url = `${API_PREFIX}/experimental/highlights/v1/generated-clips/${clip.id}/reviews`;

  async function load() {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error("No se pudo cargar el historial.");
    const revisions: Revision[] = await response.json();
    setHistory(revisions);
    const previous = revisions.at(-1)?.payload;
    if (previous?.proposal[0] === clip.start && previous.proposal[1] === clip.end) {
      setDecision(previous.decision);
      setCategory(previous.category ?? "");
      setNotes(previous.notes);
    }
  }

  async function perform(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function save(event: FormEvent) {
    event.preventDefault();
    setSaved(false);
    void perform(async () => {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          decision, category: category || null, notes,
          proposal: { start: clip.start, end: clip.end },
          operation: crypto.randomUUID(),
          expected: history?.at(-1)?.seq ?? null,
        }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        if (response.status === 409) await load();
        throw new Error(typeof body.detail === "string" ? body.detail : "No se pudo guardar la valoración.");
      }
      await load();
      setSaved(true);
    });
  }

  return (
    <details onToggle={event => {
      if (event.currentTarget.open && !history && !busy) void perform(load);
    }}>
      <summary className="cursor-pointer text-sm font-medium text-slate-200">Valorar clip</summary>
      {history && <form className="mt-2 space-y-2" onSubmit={save}>
        <label className="block text-xs">Decisión
          <select className={`${inputBase} mt-1 w-full`} value={decision}
            onChange={event => setDecision(event.target.value as Decision)}>
            {Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className="block text-xs">Categoría
          <select className={`${inputBase} mt-1 w-full`} value={category} onChange={event => setCategory(event.target.value)}>
            <option value="">Sin categoría</option>
            {categories.map(value => <option key={value}>{value}</option>)}
          </select>
        </label>
        <label className="block text-xs">Nota
          <textarea className={`${inputBase} mt-1 w-full`} value={notes} maxLength={3000}
            onChange={event => setNotes(event.target.value)} />
        </label>
        <button className={btnSecondary} disabled={busy}>Guardar valoración</button>
        {history.length > 0 && <details>
          <summary className="cursor-pointer text-xs">Historial ({history.length})</summary>
          <ul className="mt-1 space-y-1 text-xs">
            {history.map(({ seq, payload }) => <li key={seq}>
              {labels[payload.decision]} · {payload.proposal[0].toFixed(1)}–{payload.proposal[1].toFixed(1)} s
              {payload.notes && ` · ${payload.notes}`}
            </li>)}
          </ul>
        </details>}
      </form>}
      {busy && !history && <p role="status" className="text-xs">Cargando valoraciones…</p>}
      {saved && <p role="status" className="text-xs">Valoración guardada.</p>}
      {error && <p role="alert" className="text-xs text-red-400">{error}</p>}
    </details>
  );
}
