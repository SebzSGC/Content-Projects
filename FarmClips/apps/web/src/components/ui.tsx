"use client";

import React, { useEffect, useId, useState } from "react";
import { AlertTriangle, ChevronDown, Info, X } from "lucide-react";

// ============================================================================
// Astryx-Inspired Component Primitives for FarmClips Studio
// - Concentric radii: inner (6px) -> element (8px) -> container (12px) -> page (16px)
// - 1px top-edge bezel lighting (--shadow-low / --shadow-med / --shadow-high)
// - Crisp 120ms transitions without rubbery hover scale transforms
// ============================================================================

export const btnPrimary =
  "inline-flex items-center justify-center gap-2 rounded-lg bg-amber-400 px-4 py-2 text-xs sm:text-sm font-semibold text-slate-950 shadow-[0_1px_2px_rgba(0,0,0,0.4),inset_0_1px_0_rgba(255,255,255,0.35)] transition-[background-color,box-shadow,transform,opacity] duration-150 ease-out hover:bg-amber-300 active:translate-y-[0.5px] disabled:opacity-40 disabled:shadow-none disabled:cursor-not-allowed cursor-pointer";

export const btnSecondary =
  "inline-flex items-center justify-center gap-2 rounded-lg border border-white/[0.09] bg-white/[0.04] px-3.5 py-2 text-xs sm:text-sm font-medium text-slate-200 shadow-[0_1px_2px_rgba(0,0,0,0.25),inset_0_1px_0_rgba(255,255,255,0.05)] transition-[background-color,border-color,color,opacity] duration-150 ease-out hover:bg-white/[0.08] hover:border-white/[0.16] hover:text-white active:translate-y-[0.5px] disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer";

export const btnGhost =
  "inline-flex items-center justify-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-slate-400 transition-[background-color,color] duration-150 ease-out hover:bg-white/[0.06] hover:text-slate-100 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed";

export const btnDanger =
  "inline-flex items-center justify-center gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3.5 py-2 text-xs sm:text-sm font-medium text-rose-200 transition-[background-color,border-color,color] duration-150 ease-out hover:bg-rose-500/20 hover:border-rose-400/50 hover:text-white cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed";

export const inputBase =
  "w-full rounded-lg border border-white/[0.09] bg-[#0e1016] px-3.5 py-2 text-sm text-slate-100 placeholder:text-slate-500 shadow-[inset_0_1px_2px_rgba(0,0,0,0.45)] transition-[border-color,box-shadow,background-color] duration-150 ease-out focus:border-amber-400/60 focus:bg-[#11141c] focus:outline-none focus:ring-2 focus:ring-amber-400/15";

export function GlassCard({
  children,
  className = "",
  interactive = false,
  variant = "default",
  as: Tag = "div",
  onSubmit,
}: {
  children: React.ReactNode;
  className?: string;
  interactive?: boolean;
  variant?: "default" | "muted" | "elevated" | "transparent";
  as?: "div" | "section" | "article" | "form";
  onSubmit?: React.FormEventHandler<HTMLFormElement>;
}) {
  const Element = Tag as React.ElementType;
  const variants = {
    default: "ax-card",
    muted: "ax-card-muted",
    elevated: "ax-card-elevated",
    transparent: "rounded-xl border border-white/[0.06] bg-transparent",
  } as const;

  return (
    <Element
      onSubmit={onSubmit}
      className={`${variants[variant]} ${interactive ? "ax-card-interactive" : ""} ${className}`}
    >
      {children}
    </Element>
  );
}

export const Card = GlassCard;

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
    neutral: "bg-white/[0.05] text-slate-300 border-white/[0.09]",
    gold: "bg-amber-400/12 text-amber-300 border-amber-400/25",
    success: "bg-emerald-400/12 text-emerald-300 border-emerald-400/25",
    danger: "bg-rose-400/12 text-rose-300 border-rose-400/25",
    info: "bg-sky-400/12 text-sky-300 border-sky-400/25",
  } as const;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-semibold tracking-tight ${tones[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

/** Semantic status indicator dot inspired by Astryx StatusDot */
export function StatusDot({
  tone = "neutral",
  pulse = false,
  className = "",
}: {
  tone?: "online" | "warning" | "danger" | "info" | "neutral";
  pulse?: boolean;
  className?: string;
}) {
  const colors = {
    online: "bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.65)]",
    warning: "bg-amber-400 shadow-[0_0_8px_rgba(245,158,11,0.65)]",
    danger: "bg-rose-400 shadow-[0_0_8px_rgba(244,63,94,0.65)]",
    info: "bg-sky-400 shadow-[0_0_8px_rgba(56,189,248,0.65)]",
    neutral: "bg-slate-500",
  } as const;

  return (
    <span className={`relative inline-flex h-2 w-2 shrink-0 ${className}`}>
      {pulse && (
        <span
          className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-75 ${colors[tone]}`}
        />
      )}
      <span className={`relative inline-flex h-2 w-2 rounded-full ${colors[tone]}`} />
    </span>
  );
}

/** macOS-style keyboard shortcut keycap */
export function Kbd({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <kbd
      className={`inline-flex items-center justify-center rounded-[5px] border border-white/[0.12] bg-white/[0.05] px-1.5 py-0.5 font-mono text-[10px] font-medium leading-none text-slate-300 shadow-[0_1px_0_rgba(255,255,255,0.06)] ${className}`}
    >
      {children}
    </kbd>
  );
}

/** Small "i" with a tooltip on hover/focus for contextual technical information. */
export function InfoTip({
  children,
  label = "Más información",
  side = "top",
  align = "center",
}: {
  children: React.ReactNode;
  label?: string;
  side?: "top" | "bottom";
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
        className="inline-flex h-5 w-5 items-center justify-center rounded-md text-slate-500 transition-colors duration-150 hover:bg-white/[0.06] hover:text-amber-300 focus:text-amber-300 focus:outline-none cursor-help"
      >
        <Info className="h-3.5 w-3.5" />
      </button>
      <span
        id={id}
        role="tooltip"
        className={`ax-popover pointer-events-none invisible absolute z-50 w-max max-w-[19rem] px-3 py-2 text-left text-xs font-normal leading-relaxed text-slate-200 opacity-0 transition-all duration-150 ease-out group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100 ${position}`}
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
        className="group flex w-full items-center gap-3 rounded-lg px-1 py-1 text-left transition-colors duration-150 hover:text-white cursor-pointer"
      >
        {icon && (
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-white/[0.07] bg-white/[0.03] text-slate-400 transition-colors duration-150 group-hover:border-amber-400/30 group-hover:text-amber-300">
            {icon}
          </span>
        )}
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold text-slate-100">{title}</span>
          {subtitle && <span className="block truncate text-xs text-slate-400">{subtitle}</span>}
        </span>
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-slate-500 transition-transform duration-200 ease-out ${open ? "rotate-180 text-slate-300" : ""}`}
        />
      </button>
      <div
        id={contentId}
        className={`grid transition-[grid-template-rows,opacity] duration-200 ease-out motion-reduce:transition-none ${
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

/** Label/value rows for technical inspection panels. */
export function DetailList({ items }: { items: Array<[string, React.ReactNode]> }) {
  return (
    <dl className="grid gap-x-6 gap-y-2.5 sm:grid-cols-2">
      {items.map(([label, value]) => (
        <div key={label} className="min-w-0 rounded-lg border border-white/[0.05] bg-[#0e1016]/80 px-3 py-2">
          <dt className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{label}</dt>
          <dd className="mt-0.5 break-words font-mono text-xs text-slate-200 tabular-nums">
            {value ?? "—"}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** Calm spinner: thin gold arc. */
export function SoftSpinner({ className = "h-4 w-4", onAccent = false }: { className?: string; onAccent?: boolean }) {
  const colors = onAccent ? "border-slate-950/25 border-t-slate-950" : "border-amber-300/20 border-t-amber-300";
  return (
    <span
      aria-hidden
      className={`inline-block rounded-full border-2 animate-[spin_1.1s_linear_infinite] motion-reduce:animate-none ${colors} ${className}`}
    />
  );
}

/** Thin progress bar with a smooth width transition and a soft moving sheen. */
export function ProgressBar({
  value,
  tone = "gold",
  className = "",
}: {
  value: number;
  tone?: "gold" | "emerald" | "rose" | "sky";
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, value * 100));
  const fills = {
    gold: "bg-gradient-to-r from-amber-500 to-amber-300",
    emerald: "bg-gradient-to-r from-emerald-500 to-emerald-400",
    rose: "bg-gradient-to-r from-rose-500 to-rose-400",
    sky: "bg-gradient-to-r from-sky-500 to-sky-400",
  } as const;
  return (
    <div
      className={`h-1.5 overflow-hidden rounded-full bg-white/[0.06] ${className}`}
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className={`gc-sheen h-full rounded-full ${fills[tone]} transition-[width] duration-500 ease-out motion-reduce:transition-none`}
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
    <div
      className={`inline-flex rounded-lg border border-white/[0.08] bg-[#0e1016] p-1 shadow-[inset_0_1px_2px_rgba(0,0,0,0.4)] ${className}`}
      role="radiogroup"
    >
      {options.map((o) => {
        const active = value === o.value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(o.value)}
            className={`inline-flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-md px-3 py-1.5 text-xs font-semibold transition-all duration-150 ease-out cursor-pointer ${
              active
                ? "bg-amber-400 text-slate-950 shadow-[0_1px_2px_rgba(0,0,0,0.35),inset_0_1px_0_rgba(255,255,255,0.35)]"
                : "text-slate-400 hover:text-slate-100"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/** Astryx-style TabList for workspace and inspector navigation */
export function TabList<T extends string>({
  value,
  tabs,
  onChange,
  className = "",
}: {
  value: T;
  tabs: Array<{ value: T; label: React.ReactNode; icon?: React.ReactNode; badge?: React.ReactNode }>;
  onChange: (value: T) => void;
  className?: string;
}) {
  return (
    <div
      role="tablist"
      className={`flex items-center gap-1 border-b border-white/[0.08] bg-[#11141b] px-2 pt-1.5 ${className}`}
    >
      {tabs.map((tab) => {
        const active = value === tab.value;
        return (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(tab.value)}
            className={`relative inline-flex items-center gap-1.5 rounded-t-md px-3 py-2 text-xs font-semibold transition-colors duration-150 cursor-pointer ${
              active
                ? "text-amber-300 bg-white/[0.04]"
                : "text-slate-400 hover:bg-white/[0.025] hover:text-slate-200"
            }`}
          >
            {tab.icon}
            <span>{tab.label}</span>
            {tab.badge}
            {active && (
              <span className="absolute inset-x-0 bottom-0 h-0.5 rounded-full bg-amber-400" />
            )}
          </button>
        );
      })}
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="inline-flex items-center gap-2.5 text-xs sm:text-sm font-medium text-slate-300 hover:text-slate-100 cursor-pointer"
    >
      <span
        className={`relative h-5 w-9 shrink-0 rounded-full border transition-colors duration-150 ${
          checked
            ? "border-amber-300/40 bg-amber-400"
            : "border-white/[0.1] bg-[#0e1016]"
        }`}
      >
        <span
          className={`absolute top-0.5 left-0.5 h-3.5 w-3.5 rounded-full shadow transition-transform duration-150 ease-out ${
            checked ? "translate-x-4 bg-slate-950" : "bg-slate-400"
          }`}
        />
      </span>
      {label}
    </button>
  );
}

/** Standardized page or section header following Astryx hierarchy */
export function SectionHeader({
  eyebrow,
  title,
  description,
  actions,
  className = "",
}: {
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex flex-wrap items-end justify-between gap-4 ${className}`}>
      <div className="min-w-0">
        {eyebrow && (
          <div className="mb-1 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-amber-400/90">
            {eyebrow}
          </div>
        )}
        <h1 className="text-xl font-bold tracking-tight text-slate-50 sm:text-2xl">{title}</h1>
        {description && (
          <p className="mt-1 max-w-2xl text-xs sm:text-sm text-slate-400 leading-relaxed">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/** Clean macOS Studio Empty State */
export function EmptyState({
  icon,
  title,
  description,
  action,
  className = "",
}: {
  icon?: React.ReactNode;
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`ax-card-muted flex flex-col items-center justify-center px-6 py-12 text-center ${className}`}
    >
      {icon && (
        <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl border border-white/[0.08] bg-white/[0.03] text-slate-400 shadow-inner">
          {icon}
        </div>
      )}
      <p className="text-sm font-semibold text-slate-200">{title}</p>
      {description && (
        <p className="mt-1 max-w-md text-xs text-slate-400 leading-relaxed">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/** Accessible Modal AlertDialog replacing native window.confirm */
export function AlertDialog({
  open,
  title,
  description,
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  tone = "warning",
  isLoading = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: React.ReactNode;
  description: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "warning" | "danger";
  isLoading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isLoading) onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, isLoading, onCancel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-xs animate-in fade-in duration-150"
      role="alertdialog"
      aria-modal="true"
    >
      <div className="ax-popover relative w-full max-w-md p-5 sm:p-6">
        <button
          type="button"
          onClick={onCancel}
          disabled={isLoading}
          aria-label="Cerrar diálogo"
          className="absolute top-4 right-4 rounded-md p-1 text-slate-400 hover:bg-white/[0.06] hover:text-slate-100 cursor-pointer"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="flex items-start gap-3.5">
          <span
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border ${
              tone === "danger"
                ? "border-rose-500/30 bg-rose-500/12 text-rose-300"
                : "border-amber-400/30 bg-amber-400/12 text-amber-300"
            }`}
          >
            <AlertTriangle className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1 pr-4">
            <h3 className="text-base font-bold text-slate-100">{title}</h3>
            <div className="mt-1.5 text-xs sm:text-sm leading-relaxed text-slate-300">
              {description}
            </div>
          </div>
        </div>

        <div className="mt-6 flex items-center justify-end gap-2.5 border-t border-white/[0.07] pt-4">
          <button
            type="button"
            onClick={onCancel}
            disabled={isLoading}
            className={btnSecondary}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isLoading}
            className={tone === "danger" ? btnDanger : btnPrimary}
          >
            {isLoading && <SoftSpinner className="h-3.5 w-3.5" onAccent={tone !== "danger"} />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
