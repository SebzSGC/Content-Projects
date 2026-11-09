"use client";

import { useEffect, useRef } from "react";

interface ShortcutHandlers {
  onUndo: () => void;
  onRedo: () => void;
  onTogglePlay: () => void;
}

function isTextInput(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return Boolean(el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable));
}

/**
 * Ctrl/Cmd+Z, Ctrl/Cmd+Shift+Z, Ctrl/Cmd+Y and Space. Handlers are read from a ref on every key press,
 * so the listener never calls a stale closure (e.g. a togglePlay that still thinks the video is paused).
 * Inside text fields the browser keeps its own undo/redo and Space types a space.
 */
export function useEditorShortcuts(handlers: ShortcutHandlers): void {
  const ref = useRef(handlers);
  ref.current = handlers;

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (isTextInput(e.target)) return;
      const mod = e.ctrlKey || e.metaKey;
      const key = e.key.toLowerCase();
      if (mod && key === "z") {
        e.preventDefault();
        if (e.shiftKey) ref.current.onRedo();
        else ref.current.onUndo();
      } else if (mod && key === "y") {
        e.preventDefault();
        ref.current.onRedo();
      } else if (e.code === "Space" && !mod) {
        e.preventDefault();
        ref.current.onTogglePlay();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}
