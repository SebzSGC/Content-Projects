"use client";

import React, { useRef, useState } from "react";
import { Upload, Loader2 } from "lucide-react";
import { uploadFile } from "@/lib/workerClient";

// A local path input (fastest: the worker reads the file in place) with an
// upload fallback that streams the file to the worker's disk.
export function PathOrUpload({
  label,
  hint,
  value,
  onChange,
  accept = "video/*,.mkv",
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (path: string) => void;
  accept?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    setProgress(0);
    try {
      onChange(await uploadFile(file, setProgress));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al subir");
    } finally {
      setProgress(null);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-semibold text-[var(--foreground)]">{label}</span>
      <div className="flex gap-2">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="C:\\Grabaciones\\2026-11-05 20-00-00.mkv"
          className="flex-1 min-w-0 rounded-xl border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-xs font-mono text-[var(--foreground)] focus:border-[var(--primary)] focus:outline-none"
        />
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={progress !== null}
          className="inline-flex items-center gap-1.5 rounded-xl border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-xs font-semibold text-[var(--foreground)] hover:border-[var(--primary)] transition cursor-pointer disabled:opacity-60 shrink-0"
        >
          {progress !== null ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {Math.round(progress * 100)}%
            </>
          ) : (
            <>
              <Upload className="h-3.5 w-3.5" />
              Subir
            </>
          )}
        </button>
        <input ref={inputRef} type="file" accept={accept} className="hidden" onChange={(e) => onFile(e.target.files?.[0])} />
      </div>
      {hint && <span className="block text-[11px] text-[var(--muted-foreground)]">{hint}</span>}
      {error && <span className="block text-[11px] text-[var(--status-error)]">{error}</span>}
    </label>
  );
}
