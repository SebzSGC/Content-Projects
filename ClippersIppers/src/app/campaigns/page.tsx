"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { useAtom } from "jotai";
import { campaignsAtom, draftSubmissionAtom } from "@/store/opusStore";
import { Trophy, DollarSign, Film, Check, Sparkles } from "lucide-react";

export default function CampaignsPage() {
  const router = useRouter();
  const [campaigns, setCampaigns] = useAtom(campaignsAtom);
  const [draft, setDraft] = useAtom(draftSubmissionAtom);

  const handleToggleJoin = (campaignId: string) => {
    setCampaigns((prev) =>
      prev.map((c) =>
        c.campaignId === campaignId
          ? { ...c, role: c.role === "joined" ? "joinable" : "joined" }
          : c
      )
    );
  };

  const handleClipCampaignSource = (campaignId: string) => {
    const camp = campaigns.find((c) => c.campaignId === campaignId);
    const src = camp?.sources[0];
    if (!camp || !src) return;

    setDraft({
      ...draft,
      sourceUrl: src.videoUrl,
      title: `[Campaign: ${camp.agencyName}] ${src.title}`,
      platform: "YOUTUBE",
      durationSec: src.durationSec,
      resolution: "1080p",
      thumbnailUrl: src.thumbnailUrl,
      brandTemplateId: camp.brandTemplateId,
      rangeStartSec: 0,
      rangeEndSec: src.durationSec,
    });
    router.push("/workflow");
  };

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      <div className="border-b border-[var(--border)] pb-4">
        <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
          <Trophy className="h-5 w-5 text-[var(--primary)]" />
          <span>Clipper Marketplace &amp; Brand Campaigns</span>
        </h1>
        <p className="text-xs text-[var(--muted-foreground)]">
          Replica el ecosistema de campañas de creadores (Módulo 575013 `CampaignInvite` &amp; `CampaignTutorial`). Únete a campañas y recorta material oficial con el Brand Kit preasignado.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {campaigns.map((camp) => {
          const budgetPct = Math.round(
            (camp.budgetRemainingUsd / Math.max(1, camp.budgetTotalUsd)) * 100
          );
          return (
            <div
              key={camp.campaignId}
              className="rounded-3xl border border-[var(--border)] bg-[var(--card)] overflow-hidden flex flex-col justify-between shadow-lg"
            >
              <div>
                <div className="relative h-44 w-full bg-black">
                  <img
                    src={camp.thumbnailUrl}
                    alt={camp.name}
                    className="h-full w-full object-cover brightness-75"
                  />
                  <div className="absolute top-3 left-3 flex items-center gap-2">
                    <span className="rounded-lg bg-[#bef737] px-2.5 py-1 text-xs font-black text-black">
                      ${camp.cpmRateUsd.toFixed(2)} / 1K Views
                    </span>
                    <span className="rounded-lg bg-black/75 px-2.5 py-1 text-xs font-semibold text-white">
                      {camp.videoCount} Videos Source
                    </span>
                  </div>
                </div>

                <div className="p-5 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-[var(--primary)]">
                      {camp.agencyName}
                    </span>
                    <span className="text-xs text-[var(--muted-foreground)]">
                      Presupuesto restante: <strong>${camp.budgetRemainingUsd.toLocaleString()}</strong> / ${camp.budgetTotalUsd.toLocaleString()} ({budgetPct}%)
                    </span>
                  </div>
                  <h2 className="text-base font-bold">{camp.name}</h2>
                  <p className="text-xs text-[var(--muted-foreground)] leading-relaxed">
                    {camp.description}
                  </p>
                </div>
              </div>

              <div className="border-t border-[var(--border)] p-4 bg-[var(--secondary)]/30 flex items-center justify-between gap-3">
                <button
                  onClick={() => handleToggleJoin(camp.campaignId)}
                  className={`rounded-xl px-4 py-2 text-xs font-bold transition ${
                    camp.role === "joined"
                      ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                      : "bg-[var(--secondary)] text-[var(--foreground)] border border-[var(--border)]"
                  }`}
                >
                  {camp.role === "joined" ? "Unido a Campaña ✓" : "Unirse a Campaña"}
                </button>

                <button
                  onClick={() => handleClipCampaignSource(camp.campaignId)}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-[var(--primary)] px-4 py-2 text-xs font-bold text-black hover:opacity-95 transition"
                >
                  <Sparkles className="h-3.5 w-3.5" />
                  <span>Recortar Material Oficial</span>
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
