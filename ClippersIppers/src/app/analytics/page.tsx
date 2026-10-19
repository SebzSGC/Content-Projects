"use client";

import React from "react";
import { useAtom } from "jotai";
import { clipsAtom, socialPostsAtom } from "@/store/opusStore";
import { BarChart3, Eye, Heart, Share2, Flame } from "lucide-react";

export default function AnalyticsPage() {
  const [posts] = useAtom(socialPostsAtom);
  const [clips] = useAtom(clipsAtom);

  const totalViews =
    posts.reduce((acc, p) => acc + p.views, 0) + 184200;
  const totalLikes =
    posts.reduce((acc, p) => acc + p.likes, 0) + 14850;
  const totalShares =
    posts.reduce((acc, p) => acc + p.shares, 0) + 3920;
  const avgScore = Math.round(
    clips.reduce((acc, c) => acc + c.viralityScore, 0) / Math.max(1, clips.length)
  );

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      <div className="border-b border-[var(--border)] pb-4">
        <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
          <BarChart3 className="h-5 w-5 text-[var(--primary)]" />
          <span>Short-Form Performance &amp; Virality Analytics</span>
        </h1>
        <p className="text-xs text-[var(--muted-foreground)]">
          Métricas correlacionadas entre el Virality Score predicho por ClipAnything y la retención en YouTube Shorts, TikTok y Reels.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 space-y-1">
          <div className="flex items-center justify-between text-xs text-[var(--muted-foreground)]">
            <span>Total Short Views</span>
            <Eye className="h-4 w-4 text-sky-400" />
          </div>
          <div className="text-2xl font-black">{totalViews.toLocaleString()}</div>
          <div className="text-[11px] text-emerald-400">+28.4% vs 30d</div>
        </div>

        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 space-y-1">
          <div className="flex items-center justify-between text-xs text-[var(--muted-foreground)]">
            <span>Total Likes</span>
            <Heart className="h-4 w-4 text-rose-400" />
          </div>
          <div className="text-2xl font-black">{totalLikes.toLocaleString()}</div>
          <div className="text-[11px] text-emerald-400">8.1% Engagement Rate</div>
        </div>

        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 space-y-1">
          <div className="flex items-center justify-between text-xs text-[var(--muted-foreground)]">
            <span>Total Shares &amp; Saves</span>
            <Share2 className="h-4 w-4 text-purple-400" />
          </div>
          <div className="text-2xl font-black">{totalShares.toLocaleString()}</div>
          <div className="text-[11px] text-emerald-400">High Viral Loop</div>
        </div>

        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 space-y-1">
          <div className="flex items-center justify-between text-xs text-[var(--muted-foreground)]">
            <span>Avg Virality Score</span>
            <Flame className="h-4 w-4 text-[#bef737]" />
          </div>
          <div className="text-2xl font-black text-[#bef737]">{avgScore}/99</div>
          <div className="text-[11px] text-[var(--muted-foreground)]">
            Across {clips.length} curated clips
          </div>
        </div>
      </div>

      {/* Retention Curve Simulation */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold">
            Curva de Retención Promedio (Primeros 60 Segundos)
          </h2>
          <span className="text-xs text-[var(--primary)] font-semibold">
            3s Hook Hold Rate: 84.2%
          </span>
        </div>
        <div className="grid grid-cols-12 gap-2 items-end h-44 pt-4">
          {[98, 92, 86, 82, 79, 76, 74, 72, 69, 68, 65, 63].map((pct, idx) => (
            <div key={idx} className="flex flex-col items-center gap-1.5 h-full justify-end">
              <div
                style={{ height: `${pct}%` }}
                className="w-full rounded-t-lg bg-gradient-to-t from-[var(--primary)]/30 to-[var(--primary)] transition-all"
              />
              <span className="text-[10px] font-mono text-[var(--muted-foreground)]">
                {(idx + 1) * 5}s
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
