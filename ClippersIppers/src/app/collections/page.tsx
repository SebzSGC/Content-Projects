"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { useAtom } from "jotai";
import { collectionsAtom, projectsAtom } from "@/store/opusStore";
import { Folders, Plus, Lock, Unlock, Trash2, FolderKanban } from "lucide-react";

export default function CollectionsPage() {
  const router = useRouter();
  const [collections, setCollections] = useAtom(collectionsAtom);
  const [projects] = useAtom(projectsAtom);
  const [newColName, setNewColName] = useState("");
  const [newColDesc, setNewColDesc] = useState("");
  const [isPrivate, setIsPrivate] = useState(false);

  const handleCreateCollection = () => {
    if (!newColName.trim()) return;
    setCollections((prev) => [
      ...prev,
      {
        id: `col-${Date.now()}`,
        name: newColName.trim(),
        description: newColDesc.trim() || "Colección personalizada de proyectos de video.",
        isPrivate,
        createdAt: new Date().toISOString(),
        projectIds: [projects[0]?.id].filter(Boolean) as string[],
      },
    ]);
    setNewColName("");
    setNewColDesc("");
  };

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[var(--border)] pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
            <Folders className="h-5 w-5 text-[var(--primary)]" />
            <span>Project Collections ({collections.length})</span>
          </h1>
          <p className="text-xs text-[var(--muted-foreground)]">
            Agrupa proyectos en carpetas temáticas públicas o privadas dentro del workspace.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={newColName}
            onChange={(e) => setNewColName(e.target.value)}
            placeholder="Nombre de colección..."
            className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] px-3 py-1.5 text-xs"
          />
          <input
            type="text"
            value={newColDesc}
            onChange={(e) => setNewColDesc(e.target.value)}
            placeholder="Descripción breve..."
            className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] px-3 py-1.5 text-xs"
          />
          <button
            onClick={() => setIsPrivate(!isPrivate)}
            className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] px-3 py-1.5 text-xs font-medium"
          >
            {isPrivate ? "Privada" : "Pública"}
          </button>
          <button
            onClick={handleCreateCollection}
            className="inline-flex items-center gap-1 rounded-xl bg-[var(--primary)] px-3.5 py-1.5 text-xs font-bold text-black"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>Crear Colección</span>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {collections.map((col) => {
          const linkedProjects = projects.filter((p) =>
            col.projectIds.includes(p.id)
          );
          return (
            <div
              key={col.id}
              className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 flex flex-col justify-between space-y-4"
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Folders className="h-4 w-4 text-[var(--primary)]" />
                    <h2 className="text-sm font-bold">{col.name}</h2>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {col.isPrivate ? (
                      <Lock className="h-3.5 w-3.5 text-amber-400" />
                    ) : (
                      <Unlock className="h-3.5 w-3.5 text-[var(--muted-foreground)]" />
                    )}
                    <button
                      onClick={() =>
                        setCollections((prev) =>
                          prev.filter((item) => item.id !== col.id)
                        )
                      }
                      className="text-red-400 hover:text-red-300 p-1"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
                <p className="text-xs text-[var(--muted-foreground)]">
                  {col.description}
                </p>
              </div>

              <div className="space-y-1.5 border-t border-[var(--border)] pt-3">
                <div className="text-[11px] font-semibold text-[var(--muted-foreground)]">
                  Proyectos asociados ({linkedProjects.length})
                </div>
                {linkedProjects.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => router.push(`/clip/${p.id}`)}
                    className="w-full flex items-center justify-between rounded-xl bg-[var(--secondary)]/60 px-3 py-1.5 text-xs hover:border-[var(--primary)] border border-transparent transition"
                  >
                    <span className="truncate font-medium">{p.title}</span>
                    <span className="text-[10px] text-[var(--primary)] shrink-0 ml-2">
                      {p.clipCount} clips
                    </span>
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
