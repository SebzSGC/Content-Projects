"""Exports EditPlan v2 JSON Schema and generates TypeScript types + timeline/easing utilities."""

from __future__ import annotations

import json
from pathlib import Path

from .models import EditPlan

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "editplan.v2.schema.json"


def export_json_schema(dst: Path = SCHEMA_PATH) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    schema = EditPlan.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "ClipsApp EditPlan v2"
    dst.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dst


TS_TEMPLATE = """// AUTO-GENERATED from packages/editplan/schema/editplan.v2.schema.json — DO NOT EDIT BY HAND.

export type EaseKind = "linear" | "inOutSine" | "outBack" | "outCubic";
export type LayoutKind = "split" | "camera_full" | "gameplay_full";

export interface SourcePlan {
  session: string;
  ranges: [number, number][];
}

export interface OutputPlan {
  w: number;
  h: number;
  fps: number;
  style: string;
}

export interface LayoutEvent {
  t: number;
  kind: LayoutKind;
  camera_ratio?: number;
  until?: number;
}

export interface CropKeyframe {
  t: number;
  cx: number;
  cy: number;
  zoom: number;
  ease?: EaseKind;
}

export interface GameplayCropKeyframe {
  t: number;
  cx: number;
  cy: number;
  zoom: number;
}

export interface CaptionWord {
  w: string;
  s: number;
  e: number;
  emphasis?: boolean;
}

export interface EmojiCue {
  id: string;
  at: number;
}

export interface CaptionGroup {
  words: CaptionWord[];
  emoji?: EmojiCue | null;
}

export interface CaptionsPlan {
  preset: string;
  groups: CaptionGroup[];
  vertical_ratio?: number | null;
}

export interface OverlayItem {
  kind: "title" | "badge";
  text: string;
  start: number;
  end: number;
}

export interface SfxCue {
  t: number;
  id: string;
  gain_db?: number;
}

export interface AudioPlan {
  mic_gain_db: number;
  duck_game_db: number;
  sfx: SfxCue[];
}

export interface EditPlan {
  version: 2;
  clip_id?: string | null;
  candidate_id?: string | null;
  source: SourcePlan;
  output: OutputPlan;
  layout: LayoutEvent[];
  camera_crop: CropKeyframe[];
  gameplay_crop?: GameplayCropKeyframe[] | null;
  captions: CaptionsPlan;
  overlays: OverlayItem[];
  audio: AudioPlan;
}

export function getTotalClipDuration(plan: EditPlan): number {
  return plan.source.ranges.reduce((acc, [a, b]) => acc + Math.max(0, b - a), 0);
}

export function clipToMasterTime(plan: EditPlan, clipT: number): { rangeIndex: number; masterTime: number } {
  const t = Math.max(0, clipT);
  let acc = 0;
  for (let i = 0; i < plan.source.ranges.length; i++) {
    const [a, b] = plan.source.ranges[i];
    const seg = b - a;
    if (t <= acc + seg || i === plan.source.ranges.length - 1) {
      return { rangeIndex: i, masterTime: a + Math.max(0, Math.min(seg, t - acc)) };
    }
    acc += seg;
  }
  return { rangeIndex: 0, masterTime: plan.source.ranges[0]?.[0] ?? 0 };
}

export function masterToClipTime(plan: EditPlan, masterT: number): number {
  let acc = 0;
  for (let i = 0; i < plan.source.ranges.length; i++) {
    const [a, b] = plan.source.ranges[i];
    if (masterT < a) {
      return acc;
    }
    if (masterT <= b) {
      return acc + (masterT - a);
    }
    acc += (b - a);
  }
  return acc;
}

export function applyEase(u: number, ease?: EaseKind): number {
  const x = Math.max(0, Math.min(1, u));
  switch (ease) {
    case "outBack": {
      const c1 = 1.70158;
      const c3 = c1 + 1;
      return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2);
    }
    case "inOutSine":
      return -(Math.cos(Math.PI * x) - 1) / 2;
    case "outCubic":
      return 1 - Math.pow(1 - x, 3);
    default:
      return x;
  }
}

export function evaluateCameraCrop(keyframes: CropKeyframe[], t: number): { cx: number; cy: number; zoom: number } {
  if (!keyframes.length) return { cx: 0.5, cy: 0.45, zoom: 1.0 };
  if (t <= keyframes[0].t) return { cx: keyframes[0].cx, cy: keyframes[0].cy, zoom: keyframes[0].zoom };
  const last = keyframes[keyframes.length - 1];
  if (t >= last.t) return { cx: last.cx, cy: last.cy, zoom: last.zoom };
  for (let i = 0; i < keyframes.length - 1; i++) {
    const a = keyframes[i];
    const b = keyframes[i + 1];
    if (t >= a.t && t <= b.t) {
      const span = Math.max(1e-4, b.t - a.t);
      const u = applyEase((t - a.t) / span, b.ease);
      return {
        cx: Math.max(0, Math.min(1, a.cx + (b.cx - a.cx) * u)),
        cy: Math.max(0, Math.min(1, a.cy + (b.cy - a.cy) * u)),
        zoom: Math.max(1, a.zoom + (b.zoom - a.zoom) * u),
      };
    }
  }
  return { cx: last.cx, cy: last.cy, zoom: last.zoom };
}

export function evaluateLayout(events: LayoutEvent[], t: number): { kind: LayoutKind; cameraRatio: number } {
  let baseRatio = 0.4;
  for (const ev of events) {
    if (ev.kind === "split" && ev.t <= t && ev.camera_ratio != null) {
      baseRatio = ev.camera_ratio;
    }
  }
  for (const ev of events) {
    if (ev.kind !== "split") {
      const until = ev.until ?? ev.t + 2.0;
      if (t >= ev.t && t <= until) {
        return { kind: ev.kind, cameraRatio: ev.kind === "camera_full" ? 1.0 : 0.0 };
      }
    }
  }
  return { kind: "split", cameraRatio: baseRatio };
}
"""


def generate_typescript(dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(TS_TEMPLATE, encoding="utf-8")
    return dst
