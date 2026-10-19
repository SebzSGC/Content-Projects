"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { useAtom } from "jotai";
import { clipsAtom, projectsAtom } from "@/store/opusStore";
import { Star, ThumbsUp, Scissors, FolderKanban } from "lucide-react";

export default function FavoritesPage() {
  const router = useRouter();
  const [projects, setProjects] = useAtom(projectsAtom);
  const [clips, setClips] = useAtom(clipsAtom);

  const favoriteProjects = projects.filter((p) => p.isFavorite);
  const likedClips = clips.filter((c) => c.like);

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-6 space-y-8">
      <div className="border-b border-[var(--border)] pb-4">
        <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
          <Star className="h-5 w-5 text-amber-400 fill-amber-400" />
          <span>Favorites &amp; Liked Viral Clips</span>
        </h1>
        <p className="text-xs text-[var(--muted-foreground)]">
          Acceso rápido a tus proyectos destacados con estrella y a los clips con voto positivo (`Like`).
        </p>
      </div>

      {/* Starred Projects */}
      <section className="space-y-3">
        <h2 className="text-sm font-bold flex items-center gap-2">
          <FolderKanban className="h-4 w-4 text-[var(--primary)]" />
          <span>Proyectos Destacados ({favoriteProjects.length})</span>
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {favoriteProjects.map((proj) => (
            <div
              key={proj.id}
              className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-4 flex items-center justify-between gap-3"
            >
              <div
                onClick={() => router.push(`/clip/${proj.id}`)}
                className="flex items-center gap-3 cursor-pointer min-w-0"
              >
                <img
                  src={proj.sourceInfo.thumbnailUrl}
                  alt={proj.title}
                  className="h-12 w-20 rounded-lg object-cover shrink-0"
                />
                <div className="min-w-0">
                  <div className="text-xs font-bold truncate">{proj.title}</div>
                  <div className="text-[11px] text-[var(--muted-foreground)]">
                    {proj.clipCount} clips · {proj.stage}
                  </div>
                </div>
              </div>
              <button
                onClick={() =>
                  setProjects((prev) =>
                    prev.map((p) =>
                      p.id === proj.id ? { ...p, isFavorite: false } : p
                    )
                  )
                }
                className="text-amber-400 p-1"
              >
                <Star className="h-4 w-4 fill-current" />
              </button>
            </div>
          ))}
        </div>
      </section>

      {/* Liked Clips */}
      <section className="space-y-3">
        <h2 className="text-sm font-bold flex items-center gap-2">
          <ThumbsUp className="h-4 w-4 text-emerald-400" />
          <span>Clips Virales con Like ({likedClips.length})</span>
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {likedClips.map((clip) => (
            <div
              key={clip.clipId}
              className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-4 flex flex-col justify-between space-y-3"
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="rounded bg-[#bef737]/20 px-2 py-0.5 text-xs font-bold text-[#bef737]">
                    Score {clip.viralityScore}
                  </span>
                  <button
                    onClick={() =>
                      setClips((prev) =>
                        prev.map((c) =>
                          c.clipId === clip.clipId ? { ...c, like: false } : c
                        )
                      )
                    }
                    className="text-emerald-400 text-xs font-semibold"
                  >
                    Quitar Like
                  </button>
                </div>
                <h3 className="text-sm font-bold">{clip.title}</h3>
                <p className="text-xs text-[var(--muted-foreground)] line-clamp-2">
                  {clip.viralityExplanation}
                </p>
              </div>

              <button
                onClick={() => router.push(`/editor-ux/${clip.clipId}`)}
                className="w-full inline-flex items-center justify-center gap-1.5 rounded-xl bg-[var(--primary)] py-2 text-xs font-bold text-black"
              >
                <Scissors className="h-3.5 w-3.5" />
                <span>Abrir en Editor NLE</span>
              </button>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
