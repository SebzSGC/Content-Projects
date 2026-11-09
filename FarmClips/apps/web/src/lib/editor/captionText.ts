import type { CaptionGroup, CaptionWord } from "@/lib/api/editplan";

export function captionGroupText(group: CaptionGroup): string {
  return group.words.map((w) => w.w).join(" ");
}

/**
 * Replace the text of a caption group while keeping it in sync with the audio.
 *
 * - Same number of words: each word keeps its own timing and emphasis (typical fix of a misheard word).
 * - Different number: the group's time span is split between the new words proportionally to their
 *   length, so the karaoke highlight still moves through the phrase at speaking pace; emphasis is kept
 *   for words that are still there. Returns null for empty text.
 */
export function retextCaptionGroup(group: CaptionGroup, text: string): CaptionGroup | null {
  const tokens = text.split(/\s+/).map((t) => t.trim()).filter(Boolean);
  if (tokens.length === 0 || group.words.length === 0) return null;

  if (tokens.length === group.words.length) {
    // A corrected word keeps its position, timing and emphasis.
    const words: CaptionWord[] = group.words.map((w, i) => ({ ...w, w: tokens[i] }));
    return { ...group, words };
  }

  const start = group.words[0].s;
  const end = Math.max(start + 0.05 * tokens.length, group.words[group.words.length - 1].e);
  const weights = tokens.map((t) => Math.max(1, t.length));
  const total = weights.reduce((a, b) => a + b, 0);
  const kept = new Map(group.words.map((w) => [w.w.toLowerCase(), w.emphasis]));
  let cursor = start;
  const words: CaptionWord[] = tokens.map((tok, i) => {
    const dur = ((end - start) * weights[i]) / total;
    const s = Number(cursor.toFixed(3));
    cursor += dur;
    const e = i === tokens.length - 1 ? Number(end.toFixed(3)) : Number(cursor.toFixed(3));
    const emphasis = kept.get(tok.toLowerCase());
    return emphasis ? { w: tok, s, e, emphasis } : { w: tok, s, e };
  });
  return { ...group, words };
}
