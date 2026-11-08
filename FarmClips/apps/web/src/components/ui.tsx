"use client";

import React, { useId, useState } from "react";
import { ChevronDown, Info } from "lucide-react";

// Shared look for the studio: soft slate glass, rounded shapes, gold accent
// reserved for primary actions, scores and the budget.

export const btnPrimary =
  "inline-flex items-center justify-center gap-2 rounded-full bg-amber-400 px-5 py-2.5 text-sm font-extrabold text-slate-950 shadow-lg shadow-amber-500/20 transition-all duration-300 ease-in-out hover:bg-amber-300 hover:shadow-amber-400/30 hover:scale-[1.02] active:scale-[0.98] disabled:opacity-40 disabled:shadow-none disabled:hover:scale-100 disabled:cursor-not-allowed cursor-pointer motion-reduce:transition-none motion-reduce:hover:scale-100";

export const btnSecondary =
  "inline-flex items-center justify-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold text-slate-200 transition-all duration-300 ease-in-out hover:bg-white/10 hover:border-white/20 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer motion-reduce:transition-none";

export const btnGhost =
  "inline-flex items-center justify-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold text-slate-400 transition-all duration-300 hover:bg-white/5 hover:text-slate-100 cursor-pointer";

export const inputBase =
  "w-full rounded-2xl border border-white/10 bg-slate-900/60 px-4 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 transition-all duration-300 focus:border-amber-300/60 focus:outline-none focus:ring-4 focus:ring-amber-400/10";

export function GlassCard({
  children,
  className = "",
  interactive = false,
  as: Tag = "div",
  onSubmit,
}: {
  children: React.ReactNode;
  className?: string;
  interactive?: boolean;
  as?: "div" | "section" | "article" | "form";
  onSubmit?: React.FormEventHandler<HTMLFormElement>;
}) {
  const Element = Tag as React.ElementType;
  return (
    <Element
      onSubmit={onSubmit}
      className={`rounded-3xl border border-white/[0.06] bg-slate-900/70 backdrop-blur-md shadow-xl shadow-black/20 transition-all duration-200 ease-out motion-reduce:transition-none transform-gpu ${
        interactive ? "hover:scale-[1.01] hover:border-amber-300/20 hover:shadow-2xl motion-reduce:hover:scale-100 will-change-transform" : ""
      } ${className}`}
    >
      {children}
    </Element>
  );
}

export function Badge({
  children,
  tone = "neutral",
  className = "",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "gold" | "success" | "danger" | "info";
  className?: string;
}) {
  const tones = {
    neutral: "bg-white/5 text-slate-300 border-white/10",
    gold: "bg-amber-400/15 text-amber-300 border-amber-300/25",
    success: "bg-emerald-400/10 text-emerald-300 border-emerald-300/20",
    danger: "bg-rose-400/10 text-rose-300 border-rose-300/20",
    info: "bg-sky-400/10 text-sky-300 border-sky-300/20",
  } as const;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-bold ${tones[tone]} ${className}`}>
      {children}
    </span>
  );
}

/** Small "i" with a tooltip on hover/focus for purely technical information. */
export function InfoTip({
  children,
  label = "Más información",
  side = "top",
  align = "center",
}: {
  children: React.ReactNode;
  label?: string;
  side?: "top" | "bottom";
  /** "end" anchors the bubble to the icon's right edge (for icons near the right of the screen). */
  align?: "center" | "end";
}) {
  const id = useId();
  const position = [
    side === "top"
      ? "bottom-full mb-2 translate-y-1 group-hover:translate-y-0 group-focus-within:translate-y-0"
      : "top-full mt-2 -translate-y-1 group-hover:translate-y-0 group-focus-within:translate-y-0",
    align === "center" ? "left-1/2 -translate-x-1/2" : "right-0",
  ].join(" ");
  return (
    <span className="group relative inline-flex align-middle">
      <button
        type="button"
        aria-label={label}
        aria-describedby={id}
        className="inline-flex h-5 w-5 items-center justify-center rounded-full text-slate-500 transition-colors duration-300 hover:text-amber-300 focus:text-amber-300 focus:outline-none cursor-help"
      >
        <Info className="h-3.5 w-3.5" />
      </button>
      <span
        id={id}
        role="tooltip"
        className={`pointer-events-none invisible absolute z-50 w-max max-w-[18rem] rounded-2xl border border-white/10 bg-slate-900/95 px-3 py-2 text-left text-xs font-medium leading-relaxed text-slate-300 opacity-0 shadow-xl backdrop-blur-md transition-all duration-200 ease-out group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100 ${position}`}
      >
        {children}
      </span>
    </span>
  );
}

/** Collapsible panel with a smooth height transition (grid-rows 0fr → 1fr). */
export function Disclosure({
  title,
  subtitle,
  icon,
  defaultOpen = false,
  open: controlledOpen,
  onToggle,
  children,
  className = "",
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  icon?: React.ReactNode;
  defaultOpen?: boolean;
  open?: boolean;
  onToggle?: (open: boolean) => void;
  children: React.ReactNode;
  className?: string;
}) {
  const [inner, setInner] = useState(defaultOpen);
  const open = controlledOpen ?? inner;
  const contentId = useId();
  const toggle = () => {
    setInner(!open);
    onToggle?.(!open);
  };
  return (
    <div className={className}>
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-controls={contentId}
        className="group flex w-full items-center gap-3 rounded-2xl px-1 py-1 text-left cursor-pointer"
      >
        {icon && <span className="text-slate-400 transition-colors duration-300 group-hover:text-amber-300">{icon}</span>}
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-bold text-slate-200">{title}</span>
          {subtitle && <span className="block truncate text-xs text-slate-400">{subtitle}</span>}
        </span>
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-slate-500 transition-transform duration-300 ease-in-out ${open ? "rotate-180" : ""}`}
        />
      </button>
      <div
        id={contentId}
        className={`grid transition-[grid-template-rows,opacity] duration-300 ease-in-out motion-reduce:transition-none ${
          open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
        }`}
      >
        <div className="overflow-hidden">
          <div className="pt-4">{children}</div>
        </div>
      </div>
    </div>
  );
}

/** Label/value rows for the "Detalles técnicos" panels. */
export function DetailList({ items }: { items: Array<[string, React.ReactNode]> }) {
  return (
    <dl className="grid gap-x-6 gap-y-2.5 sm:grid-cols-2">
      {items.map(([label, value]) => (
        <div key={label} className="min-w-0">
          <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</dt>
          <dd className="break-words font-mono text-xs text-slate-300">
            {value ?? "—"}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** Calm spinner: thin gold arc, slower than the default spin. */
export function SoftSpinner({ className = "h-5 w-5", onAccent = false }: { className?: string; onAccent?: boolean }) {
  const colors = onAccent ? "border-slate-950/20 border-t-slate-950" : "border-amber-300/20 border-t-amber-300";
  return (
    <span
      aria-hidden
      className={`inline-block rounded-full border-2 animate-[spin_1.4s_linear_infinite] motion-reduce:animate-none ${colors} ${className}`}
    />
  );
}

/** Thin progress bar with a smooth width transition and a soft moving sheen. */
export function ProgressBar({ value, className = "" }: { value: number; className?: string }) {
  const pct = Math.max(0, Math.min(100, value * 100));
  return (
    <div className={`h-1.5 overflow-hidden rounded-full bg-white/5 ${className}`} role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
      <div
        className="gc-sheen h-full rounded-full bg-gradient-to-r from-amber-500 to-amber-300 transition-[width] duration-700 ease-out motion-reduce:transition-none"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  className = "",
}: {
  value: T;
  options: Array<{ value: T; label: React.ReactNode }>;
  onChange: (value: T) => void;
  className?: string;
}) {
  return (
    <div className={`inline-flex rounded-full border border-white/10 bg-slate-900/60 p-1 ${className}`} role="radiogroup">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={`inline-flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-full px-3.5 py-1.5 text-xs font-bold transition-all duration-300 ease-in-out cursor-pointer ${
            value === o.value ? "bg-amber-400 text-slate-950 shadow-md shadow-amber-500/20" : "text-slate-400 hover:text-slate-100"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="inline-flex items-center gap-2.5 text-sm font-semibold text-slate-300 cursor-pointer"
    >
      <span className={`relative h-6 w-11 rounded-full transition-colors duration-300 ${checked ? "bg-amber-400" : "bg-slate-700"}`}>
        <span
          className={`absolute top-1 left-1 h-4 w-4 rounded-full bg-white shadow transition-transform duration-300 ease-in-out ${
            checked ? "translate-x-5" : ""
          }`}
        />
      </span>
      {label}
    </button>
  );
}
