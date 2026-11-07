"use client";

import React, { useRef, useState } from "react";
import type { NormRect } from "@/types/gaming";

export interface PickerRegion {
  key: string;
  label: string;
  color: string;
  rect: NormRect | null;
}

const clamp = (v: number) => Math.max(0, Math.min(1, v));

// Shows a video frame and lets the user drag a rectangle for the active region.
// Rects are normalized to the displayed frame (0..1).
export function RegionPicker({
  imageUrl,
  regions,
  activeKey,
  onChange,
}: {
  imageUrl: string;
  regions: PickerRegion[];
  activeKey: string;
  onChange: (key: string, rect: NormRect) => void;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);

  const point = (e: React.PointerEvent) => {
    const box = boxRef.current!.getBoundingClientRect();
    return { x: clamp((e.clientX - box.left) / box.width), y: clamp((e.clientY - box.top) / box.height) };
  };

  const toRect = (d: { x0: number; y0: number; x1: number; y1: number }): NormRect => ({
    x: Math.min(d.x0, d.x1),
    y: Math.min(d.y0, d.y1),
    w: Math.abs(d.x1 - d.x0),
    h: Math.abs(d.y1 - d.y0),
  });

  // The drag origin lives in a ref so pointer events never read a stale render;
  // the end point always comes from the event itself.
  const origin = useRef<{ x: number; y: number } | null>(null);

  const finish = (e: React.PointerEvent) => {
    const start = origin.current;
    origin.current = null;
    setDrag(null);
    if (!start) return;
    const p = point(e);
    const rect = toRect({ x0: start.x, y0: start.y, x1: p.x, y1: p.y });
    if (rect.w > 0.02 && rect.h > 0.02) onChange(activeKey, rect);
  };

  const shown = regions.map((r) => (r.key === activeKey && drag ? { ...r, rect: toRect(drag) } : r));

  return (
    <div
      ref={boxRef}
      className="relative w-full select-none touch-none overflow-hidden rounded-2xl border border-white/10 bg-slate-950 shadow-inner cursor-crosshair"
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        const p = point(e);
        origin.current = p;
        setDrag({ x0: p.x, y0: p.y, x1: p.x, y1: p.y });
      }}
      onPointerMove={(e) => {
        const start = origin.current;
        if (!start) return;
        const p = point(e);
        setDrag({ x0: start.x, y0: start.y, x1: p.x, y1: p.y });
      }}
      onPointerUp={finish}
      onPointerCancel={() => {
        origin.current = null;
        setDrag(null);
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={imageUrl} alt="Fotograma del stream" className="block w-full h-auto pointer-events-none" draggable={false} />
      {shown.map(
        (r) =>
          r.rect && (
            <div
              key={r.key}
              className="absolute pointer-events-none rounded-xl border-2 transition-opacity duration-150"
              style={{
                left: `${r.rect.x * 100}%`,
                top: `${r.rect.y * 100}%`,
                width: `${r.rect.w * 100}%`,
                height: `${r.rect.h * 100}%`,
                borderColor: r.color,
                backgroundColor: `${r.color}22`,
                opacity: r.key === activeKey ? 1 : 0.6,
              }}
            >
              <span className="absolute left-1.5 top-1.5 rounded-full px-2 py-0.5 text-[10px] font-extrabold text-slate-950" style={{ backgroundColor: r.color }}>
                {r.label}
              </span>
            </div>
          )
      )}
    </div>
  );
}
