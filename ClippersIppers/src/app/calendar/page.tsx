"use client";

import React, { useState } from "react";
import { useAtom } from "jotai";
import {
  activeModalAtom,
  clipsAtom,
  socialAccountsAtom,
  socialPostsAtom,
} from "@/store/opusStore";
import { Calendar, Plus, Share2, CheckCircle2, Clock, Trash2 } from "lucide-react";

export default function SocialCalendarPage() {
  const [posts, setPosts] = useAtom(socialPostsAtom);
  const [clips] = useAtom(clipsAtom);
  const [accounts] = useAtom(socialAccountsAtom);
  const [, setActiveModal] = useAtom(activeModalAtom);

  const [selectedClipId, setSelectedClipId] = useState(
    clips[0]?.clipId || "clip-101"
  );
  const [captionText, setCaptionText] = useState(
    "The 3-second viral hook framework that tripled our short-form retention #shorts #ai #creator"
  );

  const handleScheduleNewPost = () => {
    const clip = clips.find((c) => c.clipId === selectedClipId) || clips[0];
    if (!clip) return;

    setPosts((prev) => [
      {
        id: `post-${Date.now()}`,
        clipId: clip.clipId,
        projectId: clip.projectId,
        clipTitle: clip.title,
        platforms: ["YOUTUBE", "TIKTOK", "INSTAGRAM"],
        scheduledAt: new Date(Date.now() + 3600 * 1000 * 18).toISOString(),
        status: "SCHEDULED",
        caption: captionText,
        aspectRatio: clip.aspectRatio,
        views: 0,
        likes: 0,
        shares: 0,
      },
      ...prev,
    ]);
  };

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[var(--border)] pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
            <Calendar className="h-5 w-5 text-[var(--primary)]" />
            <span>Social Publishing Calendar &amp; Scheduler</span>
          </h1>
          <p className="text-xs text-[var(--muted-foreground)]">
            Programa clips cortos para YouTube Shorts, TikTok, Instagram Reels, LinkedIn y X (Simulación Local).
          </p>
        </div>

        <button
          onClick={() => setActiveModal("social-accounts")}
          className="inline-flex items-center gap-1.5 rounded-xl border border-[var(--border)] bg-[var(--secondary)] px-3.5 py-2 text-xs font-semibold hover:border-[var(--primary)] transition"
        >
          <Share2 className="h-3.5 w-3.5 text-sky-400" />
          <span>
            Cuentas Conectadas ({accounts.filter((a) => a.connected).length}/
            {accounts.length})
          </span>
        </button>
      </div>

      {/* Quick Scheduler Form */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 space-y-3">
        <div className="text-xs font-bold uppercase tracking-wider text-[var(--muted-foreground)]">
          Programar Nueva Publicación Multicanal
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <select
            value={selectedClipId}
            onChange={(e) => setSelectedClipId(e.target.value)}
            className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-xs font-semibold"
          >
            {clips.map((c) => (
              <option key={c.clipId} value={c.clipId}>
                [Score {c.viralityScore}] {c.title}
              </option>
            ))}
          </select>

          <input
            type="text"
            value={captionText}
            onChange={(e) => setCaptionText(e.target.value)}
            placeholder="Caption y hashtags..."
            className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-xs"
          />

          <button
            onClick={handleScheduleNewPost}
            className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-[var(--primary)] px-4 py-2 text-xs font-bold text-black"
          >
            <Plus className="h-4 w-4" />
            <span>Agendar en Cola Local</span>
          </button>
        </div>
      </div>

      {/* Scheduled & Published Posts List */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {posts.map((post) => (
          <div
            key={post.id}
            className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-4 flex flex-col justify-between space-y-3"
          >
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span
                  className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] font-bold ${
                    post.status === "PUBLISHED"
                      ? "bg-emerald-500/20 text-emerald-400"
                      : "bg-amber-500/20 text-amber-300"
                  }`}
                >
                  {post.status === "PUBLISHED" ? (
                    <CheckCircle2 className="h-3 w-3" />
                  ) : (
                    <Clock className="h-3 w-3" />
                  )}
                  <span>{post.status}</span>
                </span>

                <button
                  onClick={() =>
                    setPosts((prev) => prev.filter((item) => item.id !== post.id))
                  }
                  className="text-red-400 hover:text-red-300 p-1"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>

              <h3 className="text-sm font-bold">{post.clipTitle}</h3>
              <p className="text-xs text-[var(--muted-foreground)]">{post.caption}</p>
            </div>

            <div className="border-t border-[var(--border)] pt-3 flex items-center justify-between text-[11px] text-[var(--muted-foreground)]">
              <div className="flex gap-1">
                {post.platforms.map((pl) => (
                  <span
                    key={pl}
                    className="rounded bg-[var(--secondary)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--foreground)]"
                  >
                    {pl}
                  </span>
                ))}
              </div>
              <span>{new Date(post.scheduledAt).toLocaleDateString()}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
