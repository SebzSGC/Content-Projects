"use client";

import React, { useState } from "react";
import { useAtom } from "jotai";
import {
  brandTemplatesAtom,
  selectedBrandTemplateIdAtom,
} from "@/store/opusStore";
import { AspectRatioOption, BrandTemplate, LayoutModeOption } from "@/types/opus";
import {
  Palette,
  Plus,
  Check,
  Sparkles,
  Type,
  Layers,
  Trash2,
} from "lucide-react";

const ANIMATION_STYLES: BrandTemplate["animationStyle"][] = [
  "simple-words-pop",
  "marker-sweep",
  "breathe-scale-wiggle",
  "slide-in-from-top",
  "word-cut",
  "individual-focus",
];

export default function BrandTemplatePage() {
  const [templates, setTemplates] = useAtom(brandTemplatesAtom);
  const [selectedId, setSelectedId] = useAtom(selectedBrandTemplateIdAtom);
  const [newTemplateName, setNewTemplateName] = useState("");
  const [savedNotice, setSavedNotice] = useState<string | null>(null);

  const activeTemplate =
    templates.find((t) => t.id === selectedId) || templates[0];

  const updateActiveTemplate = (patch: Partial<BrandTemplate>) => {
    setTemplates((prev) =>
      prev.map((t) => (t.id === activeTemplate.id ? { ...t, ...patch } : t))
    );
  };

  const handleCreateTemplate = () => {
    if (!newTemplateName.trim()) return;
    const newId = `preset-custom-${Date.now()}`;
    const created: BrandTemplate = {
      ...activeTemplate,
      id: newId,
      name: newTemplateName.trim(),
      isDefault: false,
    };
    setTemplates((prev) => [...prev, created]);
    setSelectedId(newId);
    setNewTemplateName("");
    setSavedNotice(`Brand Kit "${created.name}" creado y seleccionado como predeterminado.`);
    setTimeout(() => setSavedNotice(null), 3000);
  };

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[var(--border)] pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
            <Palette className="h-5 w-5 text-[var(--primary)]" />
            <span>Brand Kit &amp; Caption Animation Studio</span>
          </h1>
          <p className="text-xs text-[var(--muted-foreground)]">
            Configura fuentes, colores de resaltado karaoke (`#bef737`, `#ffc141`), animaciones CSS (`3icf7l4ivv-o7.css`) y marca de agua.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <input
            type="text"
            value={newTemplateName}
            onChange={(e) => setNewTemplateName(e.target.value)}
            placeholder="Nombre de nueva plantilla..."
            className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] px-3 py-1.5 text-xs"
          />
          <button
            onClick={handleCreateTemplate}
            className="inline-flex items-center gap-1.5 rounded-xl bg-[var(--primary)] px-3.5 py-1.5 text-xs font-bold text-white shadow-xs hover:opacity-95 transition cursor-pointer"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>Duplicar / Crear</span>
          </button>
        </div>
      </div>

      {savedNotice && (
        <div className="rounded-xl border border-emerald-500/40 bg-emerald-500/15 px-4 py-2.5 text-xs text-emerald-300 flex items-center gap-2">
          <Check className="h-4 w-4" />
          <span>{savedNotice}</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left 4 cols: Template List */}
        <div className="lg:col-span-4 space-y-3">
          <div className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
            Saved Brand Templates ({templates.length})
          </div>
          {templates.map((tpl) => (
            <div
              key={tpl.id}
              onClick={() => setSelectedId(tpl.id)}
              className={`cursor-pointer rounded-2xl border p-4 transition flex items-center justify-between ${
                tpl.id === activeTemplate.id
                  ? "border-[var(--primary)] bg-[var(--primary-subtle)]"
                  : "border-[var(--border)] bg-[var(--card)] hover:border-[var(--muted-foreground)]"
              }`}
            >
              <div>
                <div className="text-sm font-bold flex items-center gap-2">
                  <span>{tpl.name}</span>
                  {tpl.id === selectedId && (
                    <span className="rounded bg-[var(--primary)] px-1.5 py-0.5 text-[10px] font-bold text-white">
                      Active
                    </span>
                  )}
                </div>
                <div className="text-xs text-[var(--muted-foreground)] mt-0.5">
                  {tpl.captionPreset} · {tpl.animationStyle} · {tpl.aspectRatio}
                </div>
              </div>
              {!tpl.isDefault && templates.length > 1 && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setTemplates((prev) => prev.filter((item) => item.id !== tpl.id));
                  }}
                  className="text-red-400 hover:text-red-300 p-1"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </div>
          ))}
        </div>

        {/* Center 4 cols: Live Interactive Preview Stage */}
        <div className="lg:col-span-4 flex flex-col items-center">
          <div className="relative aspect-[9/16] w-full max-w-[270px] overflow-hidden rounded-3xl border border-[var(--border)] bg-black shadow-2xl">
            <img
              src="https://i.ytimg.com/vi_webp/TndWQw05wsA/maxresdefault.webp"
              alt="Brand Kit Preview"
              className="h-full w-full object-cover brightness-75"
            />
            {activeTemplate.logoOverlayEnabled && (
              <div className="absolute top-4 right-4 rounded-lg bg-black/70 backdrop-blur-xs px-2.5 py-1 text-[11px] font-bold text-white border border-white/15">
                {activeTemplate.watermarkText}
              </div>
            )}
            {activeTemplate.autoHookEnabled && (
              <div className="absolute top-14 inset-x-4 rounded-xl bg-[#bef737] px-3 py-1.5 text-center text-xs font-black text-black uppercase shadow-md">
                3-SECOND VIRAL HOOK PREVIEW ⚡
              </div>
            )}
            <div
              className={`absolute inset-x-4 text-center ${
                activeTemplate.position === "top"
                  ? "top-28"
                  : activeTemplate.position === "middle"
                  ? "top-1/2 -translate-y-1/2"
                  : "bottom-8"
              }`}
            >
              <div className="inline-block rounded-2xl bg-black/80 px-4 py-2 border border-white/15">
                <div
                  style={{
                    fontFamily:
                      activeTemplate.fontFamily === "Josefin Sans" || !activeTemplate.fontFamily
                        ? 'var(--font-josefin), "Josefin Sans", sans-serif'
                        : activeTemplate.fontFamily,
                    fontSize: `${Math.min(24, Math.round(activeTemplate.fontSize * 0.42))}px`,
                  }}
                  className={`font-black leading-tight ${
                    activeTemplate.uppercase ? "uppercase" : ""
                  }`}
                >
                  <span style={{ color: activeTemplate.fontColor }}>TURN 1 VIDEO INTO </span>
                  <span style={{ color: activeTemplate.highlightColor1 }}>10 VIRAL </span>
                  <span style={{ color: activeTemplate.highlightColor2 }}>SHORTS</span>
                  {activeTemplate.autoEmoji ? " 🔥" : ""}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right 4 cols: Properties Inspector */}
        <div className="lg:col-span-4 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 space-y-4 text-xs">
          <h2 className="text-sm font-bold flex items-center gap-2">
            <Type className="h-4 w-4 text-[var(--primary)]" />
            <span>Propiedades de {activeTemplate.name}</span>
          </h2>

          <div>
            <label className="block text-[var(--muted-foreground)] mb-1">
              Estilo de Animación CSS (`3icf7l4ivv-o7.css`)
            </label>
            <select
              value={activeTemplate.animationStyle}
              onChange={(e) =>
                updateActiveTemplate({
                  animationStyle: e.target.value as BrandTemplate["animationStyle"],
                })
              }
              className="w-full rounded-xl border border-[var(--border)] bg-[var(--secondary)] px-3 py-2"
            >
              {ANIMATION_STYLES.map((st) => (
                <option key={st} value={st}>
                  {st}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-[var(--muted-foreground)] mb-1">
              Tipografía / Fuente de Subtítulos
            </label>
            <select
              value={activeTemplate.fontFamily || "Josefin Sans"}
              onChange={(e) =>
                updateActiveTemplate({ fontFamily: e.target.value })
              }
              className="w-full rounded-xl border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 font-medium"
            >
              <option value="Josefin Sans">Josefin Sans (Recomendada / Editorial)</option>
              <option value="Inter">Inter (Sans Moderna)</option>
              <option value="Montserrat">Montserrat (Negrita Impacto)</option>
              <option value="Geist Sans">Geist Sans (Minimalista)</option>
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[var(--muted-foreground)] mb-1">
                Color Karaoke 1
              </label>
              <input
                type="color"
                value={activeTemplate.highlightColor1}
                onChange={(e) =>
                  updateActiveTemplate({ highlightColor1: e.target.value })
                }
                className="h-9 w-full rounded-lg cursor-pointer bg-transparent"
              />
            </div>
            <div>
              <label className="block text-[var(--muted-foreground)] mb-1">
                Color Karaoke 2
              </label>
              <input
                type="color"
                value={activeTemplate.highlightColor2}
                onChange={(e) =>
                  updateActiveTemplate({ highlightColor2: e.target.value })
                }
                className="h-9 w-full rounded-lg cursor-pointer bg-transparent"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[var(--muted-foreground)] mb-1">
                Aspect Ratio
              </label>
              <select
                value={activeTemplate.aspectRatio}
                onChange={(e) =>
                  updateActiveTemplate({
                    aspectRatio: e.target.value as AspectRatioOption,
                  })
                }
                className="w-full rounded-xl border border-[var(--border)] bg-[var(--secondary)] px-3 py-2"
              >
                <option value="9:16">9:16 Vertical</option>
                <option value="16:9">16:9 Landscape</option>
                <option value="1:1">1:1 Square</option>
                <option value="4:5">4:5 Portrait</option>
              </select>
            </div>
            <div>
              <label className="block text-[var(--muted-foreground)] mb-1">
                Layout Predeterminado
              </label>
              <select
                value={activeTemplate.layoutMode}
                onChange={(e) =>
                  updateActiveTemplate({
                    layoutMode: e.target.value as LayoutModeOption,
                  })
                }
                className="w-full rounded-xl border border-[var(--border)] bg-[var(--secondary)] px-3 py-2"
              >
                <option value="fill">Fill (AI Face Tracking)</option>
                <option value="fit">Fit (Blurred BG)</option>
                <option value="split">Split (2 Speakers)</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-[var(--muted-foreground)] mb-1">
              Texto de Marca de Agua / Handle
            </label>
            <input
              type="text"
              value={activeTemplate.watermarkText}
              onChange={(e) =>
                updateActiveTemplate({ watermarkText: e.target.value })
              }
              className="w-full rounded-xl border border-[var(--border)] bg-[var(--secondary)] px-3 py-2"
            />
          </div>

          <div className="space-y-2 pt-2">
            <label className="flex items-center justify-between">
              <span>Texto en Mayúsculas (ALL CAPS)</span>
              <input
                type="checkbox"
                checked={activeTemplate.uppercase}
                onChange={(e) =>
                  updateActiveTemplate({ uppercase: e.target.checked })
                }
                className="h-4 w-4 accent-[var(--primary)]"
              />
            </label>
            <label className="flex items-center justify-between">
              <span>Auto Emojis Sincronizados</span>
              <input
                type="checkbox"
                checked={activeTemplate.autoEmoji}
                onChange={(e) =>
                  updateActiveTemplate({ autoEmoji: e.target.checked })
                }
                className="h-4 w-4 accent-[var(--primary)]"
              />
            </label>
          </div>
        </div>
      </div>
    </div>
  );
}
