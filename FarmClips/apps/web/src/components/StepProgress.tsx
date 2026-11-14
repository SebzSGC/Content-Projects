"use client";

import React from "react";
import { Check, X } from "lucide-react";

export type StepStatus = "done" | "active" | "pending" | "error";

export interface PipelineStep {
  key: string;
  label: string;
  hint: string;
}

// 7-step Astryx precision track: concentric step indicators, tabular numbers,
// subtle top-edge bezel lighting and smooth hardware-accelerated progress fill.
export function StepProgress({
  steps,
  statuses,
  fill,
  current,
  compact = false,
}: {
  steps: PipelineStep[];
  statuses: StepStatus[];
  /** 0..1 position of the filled track (0 = first dot, 1 = last dot). */
  fill: number;
  current: number;
  compact?: boolean;
}) {
  const pct = Math.max(0, Math.min(1, fill)) * 100;
  const dotSize = compact ? "h-2.5 w-2.5" : "h-8 w-8";

  return (
    <div className="w-full">
      <div className={`relative ${compact ? "" : "pb-2 sm:pb-7"}`}>
        <div className={`absolute ${compact ? "inset-x-[5px] top-[4px] h-[2px]" : "inset-x-[16px] top-[15px] h-[2px]"}`}>
          <div className="absolute inset-0 rounded-full bg-white/[0.08]" />
          <div
            className={`absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-amber-500 to-amber-300 transition-[width] duration-500 ease-out motion-reduce:transition-none ${
              compact ? "" : "shadow-[0_0_10px_rgba(245,158,11,0.4)]"
            }`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <ol className="relative flex justify-between">
          {steps.map((step, i) => {
            const status = statuses[i];
            const dot = {
              done: "bg-amber-400 text-slate-950 border-amber-300 shadow-[0_1px_2px_rgba(0,0,0,0.4)]",
              active:
                "bg-[#161922] text-amber-300 border-amber-400 ring-4 ring-amber-400/20 shadow-[0_0_12px_rgba(245,158,11,0.35)]",
              pending: "bg-[#11141b] text-slate-500 border-white/[0.1]",
              error: "bg-rose-950 text-rose-300 border-rose-400/60 ring-4 ring-rose-500/15",
            }[status];
            return (
              <li
                key={step.key}
                className={`relative flex justify-center ${dotSize}`}
                title={`${i + 1}. ${step.label}: ${step.hint}`}
              >
                <span
                  className={`flex items-center justify-center rounded-full font-mono font-bold tabular-nums transition-all duration-300 ease-out motion-reduce:transition-none ${
                    compact ? "h-2.5 w-2.5 border" : "h-8 w-8 border text-xs"
                  } ${dot}`}
                  aria-current={status === "active" ? "step" : undefined}
                >
                  {!compact &&
                    (status === "done" ? (
                      <Check className="h-3.5 w-3.5" strokeWidth={2.8} />
                    ) : status === "error" ? (
                      <X className="h-3.5 w-3.5" strokeWidth={2.8} />
                    ) : (
                      i + 1
                    ))}
                </span>
                {!compact && (
                  <span
                    className={`absolute top-10 left-1/2 hidden -translate-x-1/2 whitespace-nowrap text-[11px] font-semibold tracking-tight transition-colors duration-200 sm:block ${
                      status === "active"
                        ? "text-amber-300"
                        : status === "done"
                          ? "text-slate-300"
                          : status === "error"
                            ? "text-rose-300"
                            : "text-slate-500"
                    }`}
                  >
                    {step.label}
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      </div>
      {!compact && (
        <p className="mt-1 text-center text-xs font-medium text-slate-400 sm:hidden">
          Paso <span className="font-mono text-slate-200">{current + 1}</span> de{" "}
          <span className="font-mono text-slate-200">{steps.length}</span>:{" "}
          <span className="font-semibold text-amber-300">{steps[current]?.label}</span>
        </p>
      )}
    </div>
  );
}
