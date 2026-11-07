"use client";

import React from "react";
import { Check, X } from "lucide-react";
import { STEPS, StepState } from "@/lib/gamingSteps";

// 7-step track: the gold fill glides as the pipeline advances, the active step
// glows softly, finished steps get a check. Dots have a fixed width so the track
// runs exactly from the first dot's center to the last one's.
export function StepProgress({ state, compact = false }: { state: StepState; compact?: boolean }) {
  const pct = Math.max(0, Math.min(1, state.fill)) * 100;
  const dotSize = compact ? "h-3 w-3" : "h-9 w-9";

  return (
    <div className="w-full">
      <div className={`relative ${compact ? "" : "pb-3 sm:pb-8"}`}>
        <div className={`absolute ${compact ? "inset-x-[6px] top-[5px] h-0.5" : "inset-x-[18px] top-4 h-1"}`}>
          <div className="absolute inset-0 rounded-full bg-white/[0.07]" />
          <div
            className={`absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-amber-500 to-amber-300 transition-[width] duration-700 ease-out motion-reduce:transition-none ${
              compact ? "" : "shadow-[0_0_12px_rgba(251,191,36,0.45)]"
            }`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <ol className="relative flex justify-between">
          {STEPS.map((step, i) => {
            const status = state.statuses[i];
            const dot = {
              done: "bg-amber-400 text-slate-950 border-amber-400",
              active: "bg-slate-900 text-amber-300 border-amber-300 ring-4 ring-amber-400/25 shadow-lg shadow-amber-500/40",
              pending: "bg-slate-900 text-slate-500 border-white/10",
              error: "bg-rose-950 text-rose-300 border-rose-400/60 ring-4 ring-rose-500/15",
            }[status];
            return (
              <li key={step.key} className={`relative flex justify-center ${dotSize}`} title={`${i + 1}. ${step.label}: ${step.hint}`}>
                <span
                  className={`flex items-center justify-center rounded-full font-extrabold transition-all duration-500 ease-out motion-reduce:transition-none ${
                    compact ? "h-3 w-3 border" : "h-9 w-9 border-2 text-sm"
                  } ${dot} ${status === "active" && !compact ? "scale-110" : ""}`}
                  aria-current={status === "active" ? "step" : undefined}
                >
                  {!compact &&
                    (status === "done" ? (
                      <Check className="h-4 w-4" strokeWidth={3} />
                    ) : status === "error" ? (
                      <X className="h-4 w-4" strokeWidth={3} />
                    ) : (
                      i + 1
                    ))}
                </span>
                {!compact && (
                  <span
                    className={`absolute top-11 left-1/2 hidden -translate-x-1/2 whitespace-nowrap text-xs font-bold transition-colors duration-300 sm:block ${
                      status === "active" ? "text-amber-300" : status === "done" ? "text-slate-300" : status === "error" ? "text-rose-300" : "text-slate-500"
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
        <p className="text-center text-xs font-semibold text-slate-400 sm:hidden">
          Paso {state.current + 1} de {STEPS.length}: <span className="text-slate-200">{STEPS[state.current].label}</span>
        </p>
      )}
    </div>
  );
}
