"use client";

import { useEffect, useRef } from "react";

export const AUTOSAVE_DELAY_MS = 2500;

/**
 * Saves `delayMs` after the last change while `dirty`, unless `paused` (dragging, saving, rendering).
 * Each new change restarts the timer, so a burst of edits produces a single save.
 */
export function useAutosave(options: {
  dirty: boolean;
  paused: boolean;
  changeKey: unknown;
  save: () => Promise<unknown>;
  delayMs?: number;
}): void {
  const { dirty, paused, changeKey, save, delayMs = AUTOSAVE_DELAY_MS } = options;
  const saveRef = useRef(save);
  saveRef.current = save;

  useEffect(() => {
    if (!dirty || paused) return;
    const timer = window.setTimeout(() => {
      saveRef.current().catch(() => null);
    }, delayMs);
    return () => window.clearTimeout(timer);
  }, [dirty, paused, changeKey, delayMs]);
}

/** Native "leave site?" prompt while there are unsaved changes (reload, close tab, external link). */
export function useUnsavedChangesWarning(dirty: boolean): void {
  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);
}
