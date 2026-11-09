"use client";

import { useCallback, useRef, useState } from "react";
import type { EditPlan } from "@/lib/api/editplan";

const MAX_HISTORY = 30;

export interface EditHistory {
  plan: EditPlan | null;
  /** Always the latest plan, also between renders (60 fps loop, drags, async callbacks). */
  planRef: React.MutableRefObject<EditPlan | null>;
  dirty: boolean;
  canUndo: boolean;
  canRedo: boolean;
  /** Apply an edit; recorded in the undo history unless `skipHistory` (e.g. intermediate drag frames). */
  mutatePlan: (updater: (draft: EditPlan) => EditPlan, options?: { skipHistory?: boolean }) => void;
  /** Record `before` as one undo step for an edit already applied with skipHistory (end of a drag). */
  commitHistoryFrom: (before: EditPlan) => void;
  undo: () => boolean;
  redo: () => boolean;
  /** Replace the plan without touching history (load, server response). */
  replacePlan: (next: EditPlan, options?: { clean?: boolean; resetHistory?: boolean }) => void;
  markClean: () => void;
}

/**
 * Plan state + undo/redo. Every side effect happens outside React's state updaters, so StrictMode's
 * double invocation never records an edit twice.
 */
export function useEditHistory(): EditHistory {
  const [plan, setPlan] = useState<EditPlan | null>(null);
  const [dirty, setDirty] = useState(false);
  const planRef = useRef<EditPlan | null>(null);
  const undoRef = useRef<EditPlan[]>([]);
  const redoRef = useRef<EditPlan[]>([]);
  const [historySizes, setHistorySizes] = useState({ undo: 0, redo: 0 });

  const syncSizes = useCallback(() => {
    setHistorySizes({ undo: undoRef.current.length, redo: redoRef.current.length });
  }, []);

  const apply = useCallback((next: EditPlan) => {
    planRef.current = next;
    setPlan(next);
  }, []);

  const pushUndo = useCallback(
    (before: EditPlan) => {
      undoRef.current = [...undoRef.current.slice(-(MAX_HISTORY - 1)), before];
      redoRef.current = [];
      syncSizes();
    },
    [syncSizes]
  );

  const mutatePlan = useCallback<EditHistory["mutatePlan"]>(
    (updater, options) => {
      const prev = planRef.current;
      if (!prev) return;
      const next = updater(structuredClone(prev));
      if (!options?.skipHistory) pushUndo(prev);
      apply(next);
      setDirty(true);
    },
    [apply, pushUndo]
  );

  const commitHistoryFrom = useCallback(
    (before: EditPlan) => {
      pushUndo(before);
      setDirty(true);
    },
    [pushUndo]
  );

  const undo = useCallback(() => {
    const current = planRef.current;
    const previous = undoRef.current[undoRef.current.length - 1];
    if (!current || !previous) return false;
    undoRef.current = undoRef.current.slice(0, -1);
    redoRef.current = [...redoRef.current, current];
    syncSizes();
    apply(previous);
    setDirty(true);
    return true;
  }, [apply, syncSizes]);

  const redo = useCallback(() => {
    const current = planRef.current;
    const next = redoRef.current[redoRef.current.length - 1];
    if (!current || !next) return false;
    redoRef.current = redoRef.current.slice(0, -1);
    undoRef.current = [...undoRef.current, current];
    syncSizes();
    apply(next);
    setDirty(true);
    return true;
  }, [apply, syncSizes]);

  const replacePlan = useCallback<EditHistory["replacePlan"]>(
    (next, options) => {
      if (options?.resetHistory) {
        undoRef.current = [];
        redoRef.current = [];
        syncSizes();
      }
      apply(next);
      if (options?.clean) setDirty(false);
    },
    [apply, syncSizes]
  );

  const markClean = useCallback(() => setDirty(false), []);

  return {
    plan,
    planRef,
    dirty,
    canUndo: historySizes.undo > 0,
    canRedo: historySizes.redo > 0,
    mutatePlan,
    commitHistoryFrom,
    undo,
    redo,
    replacePlan,
    markClean,
  };
}
