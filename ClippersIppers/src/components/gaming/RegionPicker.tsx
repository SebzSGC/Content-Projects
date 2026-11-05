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

  const finish = () => {
    if (drag) {
      const rect = toRect(drag);
      if (rect.w > 0.02 && rect.h > 0.02) onChange(activeKey, rect);
    }
    setDrag(null);
  };

  const shown = regions.map((r) => (r.key === activeKey && drag ? { ...r, rect: toRect(drag) } : r));

  return (
    <div
      ref={boxRef}
      className="relative w-full select-none touch-none overflow-hidden rounded-2xl border border-[var(--border)] bg-black cursor-crosshair"
      onPointerDown={(e) => {
        (e.target as HTMLElement).setPointerCapture(e.pointerId);
        const p = point(e);
        setDrag({ x0: p.x, y0: p.y, x1: p.x, y1: p.y });
      }}
      onPointerMove={(e) => {
        if (!drag) return;
        const p = point(e);
        setDrag({ ...drag, x1: p.x, y1: p.y });
      }}
      onPointerUp={finish}
      onPointerCancel={() => setDrag(null)}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={imageUrl} alt="Fotograma del stream" className="block w-full h-auto pointer-events-none" draggable={false} />
      {shown.map(
        (r) =>
          r.rect && (
            <div
              key={r.key}
              className="absolute pointer-events-none border-2"
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
              <span className="absolute left-0 top-0 px-1.5 py-0.5 text-[10px] font-bold text-white" style={{ backgroundColor: r.color }}>
                {r.label}
              </span>
            </div>
          )
      )}
    </div>
  );
}
