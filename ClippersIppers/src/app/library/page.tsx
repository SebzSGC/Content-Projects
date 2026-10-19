"use client";

import React, { useState } from "react";
import {
  FolderOpen,
  Upload,
  Music,
  Image as ImageIcon,
  Type,
  Film,
  Trash2,
  Check,
} from "lucide-react";

interface StudioAsset {
  id: string;
  name: string;
  category: "logo" | "font" | "intro_outro" | "music_sfx";
  sizeLabel: string;
  format: string;
}

const INITIAL_ASSETS: StudioAsset[] = [
  {
    id: "ast-1",
    name: "OpusClip_Watermark_White.png",
    category: "logo",
    sizeLabel: "148 KB",
    format: "PNG",
  },
  {
    id: "ast-2",
    name: "Montserrat-ExtraBold-Karaoke.ttf",
    category: "font",
    sizeLabel: "312 KB",
    format: "TTF",
  },
  {
    id: "ast-3",
    name: "Subscribe_CTA_Vertical_Outro_9x16.mp4",
    category: "intro_outro",
    sizeLabel: "4.2 MB",
    format: "MP4",
  },
  {
    id: "ast-4",
    name: "Whoosh_Transition_Punch_v2.wav",
    category: "music_sfx",
    sizeLabel: "420 KB",
    format: "WAV",
  },
];

export default function AssetLibraryPage() {
  const [assets, setAssets] = useState<StudioAsset[]>(INITIAL_ASSETS);
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [newAssetName, setNewAssetName] = useState("");
  const [newAssetCat, setNewAssetCat] =
    useState<StudioAsset["category"]>("logo");

  const filtered = assets.filter((a) =>
    categoryFilter === "all" ? true : a.category === categoryFilter
  );

  const handleAddAsset = () => {
    if (!newAssetName.trim()) return;
    setAssets((prev) => [
      {
        id: `ast-${Date.now()}`,
        name: newAssetName.trim(),
        category: newAssetCat,
        sizeLabel: "512 KB",
        format: newAssetCat === "font" ? "TTF" : newAssetCat === "music_sfx" ? "WAV" : "PNG",
      },
      ...prev,
    ]);
    setNewAssetName("");
  };

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[var(--border)] pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
            <FolderOpen className="h-5 w-5 text-[var(--primary)]" />
            <span>Brand Asset Library ({filtered.length})</span>
          </h1>
          <p className="text-xs text-[var(--muted-foreground)]">
            Administra logotipos, fuentes tipográficas TTF/OTF, intros/outros 9:16 y efectos de sonido (Auto SFX).
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={newAssetName}
            onChange={(e) => setNewAssetName(e.target.value)}
            placeholder="Nombre de archivo (ej. Brand_Logo.png)..."
            className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] px-3 py-1.5 text-xs"
          />
          <select
            value={newAssetCat}
            onChange={(e) =>
              setNewAssetCat(e.target.value as StudioAsset["category"])
            }
            className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] px-3 py-1.5 text-xs"
          >
            <option value="logo">Logo / Overlay</option>
            <option value="font">Custom Font</option>
            <option value="intro_outro">Intro / Outro Video</option>
            <option value="music_sfx">Music &amp; Auto SFX</option>
          </select>
          <button
            onClick={handleAddAsset}
            className="inline-flex items-center gap-1.5 rounded-xl bg-[var(--primary)] px-3.5 py-1.5 text-xs font-bold text-black"
          >
            <Upload className="h-3.5 w-3.5" />
            <span>Registrar Activo</span>
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {(
          [
            { id: "all", label: "All Assets" },
            { id: "logo", label: "Logos & Watermarks" },
            { id: "font", label: "Custom Fonts" },
            { id: "intro_outro", label: "Intros & Outros" },
            { id: "music_sfx", label: "Music & SFX" },
          ] as const
        ).map((tab) => (
          <button
            key={tab.id}
            onClick={() => setCategoryFilter(tab.id)}
            className={`rounded-xl px-3.5 py-1.5 text-xs font-semibold transition ${
              categoryFilter === tab.id
                ? "bg-[var(--primary)] text-black"
                : "bg-[var(--secondary)] text-[var(--muted-foreground)]"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {filtered.map((item) => (
          <div
            key={item.id}
            className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-4 flex flex-col justify-between space-y-3"
          >
            <div className="flex items-start justify-between">
              <div className="rounded-xl bg-[var(--secondary)] p-2.5 text-[var(--primary)]">
                {item.category === "logo" && <ImageIcon className="h-5 w-5" />}
                {item.category === "font" && <Type className="h-5 w-5" />}
                {item.category === "intro_outro" && <Film className="h-5 w-5" />}
                {item.category === "music_sfx" && <Music className="h-5 w-5" />}
              </div>
              <button
                onClick={() =>
                  setAssets((prev) => prev.filter((a) => a.id !== item.id))
                }
                className="text-red-400 hover:text-red-300 p-1"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>

            <div>
              <div className="text-xs font-bold truncate">{item.name}</div>
              <div className="text-[11px] text-[var(--muted-foreground)] mt-0.5">
                {item.format} · {item.sizeLabel}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
