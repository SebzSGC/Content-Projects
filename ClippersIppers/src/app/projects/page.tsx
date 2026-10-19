"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { useAtom } from "jotai";
import { clipsAtom, projectsAtom } from "@/store/opusStore";
import { formatSecondsToTimecode } from "@/lib/multipartUploader";
import {
  LayoutGrid,
  Search,
  Trash2,
  Film,
  Play,
  ArrowRight,
  Sparkles,
} from "lucide-react";

export default function AllProjectsPage() {
  const router = useRouter();
  const [projects, setProjects] = useAtom(projectsAtom);
  const [, setClips] = useAtom(clipsAtom);
  const [search, setSearch] = useState("");

  const filtered = projects.filter((p) => {
    if (search.trim() && !p.title.toLowerCase().includes(search.toLowerCase()))
      return false;
    return true;
  });

  const handleDelete = (projectId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setProjects((prev) => prev.filter((p) => p.id !== projectId));
    setClips((prev) => prev.filter((c) => c.projectId !== projectId));
  };

  return (
    <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[var(--border)] pb-5">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[var(--foreground)] flex items-center gap-2.5">
            <LayoutGrid className="h-5 w-5 text-[var(--primary)]" />
            <span>Biblioteca de Proyectos ({filtered.length})</span>
          </h1>
          <p className="text-xs text-[var(--muted-foreground)] mt-0.5">
            Todos tus videos y colecciones de clips guardados en tu equipo local.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-[var(--muted-foreground)]" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar por título..."
              className="w-full rounded-xl border border-[var(--border)] bg-[var(--card)] pl-8 pr-3 py-1.5 text-xs text-[var(--foreground)] focus:border-[var(--primary)] focus:outline-none"
            />
          </div>

          <button
            onClick={() => router.push("/dashboard")}
            className="inline-flex items-center gap-1.5 rounded-xl bg-[var(--primary)] px-3.5 py-1.5 text-xs font-bold text-white shadow-xs hover:opacity-95 transition cursor-pointer shrink-0"
          >
            <Sparkles className="h-3.5 w-3.5" />
            <span>Nuevo Clip</span>
          </button>
        </div>
      </div>

      {/* Projects Grid */}
      {filtered.length === 0 ? (
        <div className="rounded-3xl border border-[var(--border)] bg-[var(--card)] p-12 text-center space-y-3">
          <Film className="h-10 w-10 text-[var(--muted-foreground)] mx-auto opacity-40" />
          <h3 className="text-sm font-bold text-[var(--foreground)]">
            No se encontraron proyectos
          </h3>
          <p className="text-xs text-[var(--muted-foreground)] max-w-sm mx-auto">
            {search.trim()
              ? "Prueba con otra palabra clave en el buscador."
              : "Aún no has creado proyectos. Ve al Studio para comenzar con tu primer video."}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filtered.map((proj) => {
            const durationSec = Math.round((proj.sourceInfo.durationMs || 0) / 1000);
            return (
              <div
                key={proj.id}
                onClick={() => router.push(`/clip/${proj.id}`)}
                className="group rounded-2xl border border-[var(--border)] bg-[var(--card)] overflow-hidden hover:border-[var(--primary)]/60 hover:shadow-card transition flex flex-col justify-between cursor-pointer"
              >
                <div className="relative aspect-video bg-black/10 overflow-hidden">
                  <img
                    src={proj.sourceInfo.thumbnailUrl}
                    alt={proj.title}
                    className="h-full w-full object-cover group-hover:scale-103 transition duration-300"
                  />
                  <div className="absolute bottom-2 right-2 rounded-md bg-black/80 backdrop-blur-xs px-2 py-0.5 text-[10px] font-mono text-white">
                    {formatSecondsToTimecode(durationSec)}
                  </div>
                  <div className="absolute top-2 left-2 rounded-md bg-[var(--card)]/90 backdrop-blur-xs px-2 py-0.5 text-[10px] font-bold text-[var(--foreground)]">
                    {proj.sourceInfo.type}
                  </div>
                </div>

                <div className="p-4 space-y-3 flex-1 flex flex-col justify-between">
                  <div className="space-y-1">
                    <div className="text-[11px] text-[var(--muted-foreground)]">
                      {new Date(proj.createdAt).toLocaleDateString("es-ES", {
                        day: "numeric",
                        month: "short",
                        year: "numeric",
                      })}
                    </div>
                    <h3 className="text-sm font-bold text-[var(--foreground)] line-clamp-2 leading-snug">
                      {proj.title}
                    </h3>
                  </div>

                  <div className="flex items-center justify-between pt-3 border-t border-[var(--border)]">
                    <span className="text-xs font-semibold text-[var(--primary)] inline-flex items-center gap-1 group-hover:translate-x-0.5 transition">
                      <span>Ver {proj.clipCount} clips</span>
                      <ArrowRight className="h-3 w-3" />
                    </span>
                    <button
                      onClick={(e) => handleDelete(proj.id, e)}
                      className="rounded-lg p-1.5 text-[var(--muted-foreground)] hover:text-red-500 hover:bg-red-500/10 transition"
                      title="Eliminar proyecto"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
