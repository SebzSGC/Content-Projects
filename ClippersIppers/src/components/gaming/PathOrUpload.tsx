"use client";

import React, { useRef, useState } from "react";
import { Upload } from "lucide-react";
import { uploadFile } from "@/lib/workerClient";
import { InfoTip, ProgressBar, btnSecondary, inputBase } from "./ui";

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
    <div className="space-y-2">
      <span className="flex items-center gap-1 text-sm font-bold text-slate-200">
        {label}
        {hint && <InfoTip>{hint}</InfoTip>}
      </span>
      <div className="flex gap-2">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Ruta del archivo o súbelo →"
          aria-label={label}
          className={`${inputBase} min-w-0 flex-1 font-mono text-xs`}
        />
        <button type="button" onClick={() => inputRef.current?.click()} disabled={progress !== null} className={`${btnSecondary} shrink-0`}>
          <Upload className="h-4 w-4" />
          <span className="hidden sm:inline">Subir</span>
        </button>
        <input ref={inputRef} type="file" accept={accept} className="hidden" onChange={(e) => onFile(e.target.files?.[0])} />
      </div>
      {progress !== null && (
        <div className="space-y-1">
          <ProgressBar value={progress} />
          <p className="text-xs text-slate-400">Subiendo… {Math.round(progress * 100)}%</p>
        </div>
      )}
      {error && <p className="text-xs font-semibold text-rose-300">{error}</p>}
    </div>
  );
}
