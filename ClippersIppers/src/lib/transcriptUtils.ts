import { TranscriptWord } from "@/types/opus";

/**
 * Checks if a token is a silence marker, pause indicator, censored blank,
 * or bracketed sound annotation that should NOT be displayed to the user.
 * 
 * Examples filtered:
 * - "[1.5s paused]", "[0.8s pause]", "[pause]", "[pausa]"
 * - "[____]", "[___]", "[__]", "____", "___"
 * - "[Música]", "[Musica]", "[Music]", "[Aplausos]", "[Risas]", "[Applause]"
 * - "[inaudible]", "[Inaudible]"
 */
export function isNoiseOrPauseWord(word: string | undefined | null): boolean {
  if (!word) return true;
  const trimmed = word.trim();
  if (!trimmed) return true;

  // Censors / blanks from YouTube ASR: [____], [___], [__], ____, ___
  if (/^\[?_{2,}\]?$/.test(trimmed)) {
    return true;
  }

  // Bracketed pause, silence, sound annotations or durations:
  // e.g. [1.5s paused], [0.8s pause], [pause], [pausa], [música], [risas], [aplausos], etc.
  if (
    /^\[.*(pause|paused|pausa|m[úu]sic|risas?|laughter|aplaus|applause|inaudible|_|\d+\.?\d*s).*\]$/i.test(
      trimmed
    )
  ) {
    return true;
  }

  // Bracketed numbers or durations like [1.5s] or [00:15]
  if (/^\[\s*\d+(\.\d+)?s?\s*\]$/i.test(trimmed)) {
    return true;
  }

  // Generic short bracket metadata annotations (e.g. [Audio], [Sound], [Noise])
  if (/^\[[A-Za-z0-9_\.\s\-]+\]$/.test(trimmed) && trimmed.length <= 25) {
    return true;
  }

  return false;
}

/**
 * Filters out deleted words, pauses, and bracketed noise/censor tokens.
 */
export function getCleanVisibleWords(
  words: TranscriptWord[] | undefined | null
): TranscriptWord[] {
  if (!Array.isArray(words)) return [];
  return words.filter(
    (w) => !w.deleted && !w.isPause && !isNoiseOrPauseWord(w.word)
  );
}

/**
 * Cleans an entire list of words to ensure no pause or noise tokens exist.
 */
export function cleanAllTranscriptWords(
  words: TranscriptWord[] | undefined | null
): TranscriptWord[] {
  if (!Array.isArray(words)) return [];
  return words.filter((w) => !w.isPause && !isNoiseOrPauseWord(w.word));
}

/**
 * Resolves a natural, coherent subtitle phrase around the active word.
 *
 * Prevents gluing words that are spoken seconds in the future (e.g. pauses > 0.45s)
 * or mixing words that belong to separate spoken sentences or utterances.
 *
 * Rules:
 * 1. If activeWordIndex < 0, returns [] (speaker silent -> no subtitles).
 * 2. Words in the same phrase card must have temporal continuity (gap <= 0.45s).
 * 3. Sentence-terminating punctuation (. ! ? : ;) immediately ends the phrase card.
 * 4. Maximum 4 words per phrase card and max card duration <= 2.2s.
 * 5. Future words starting > 0.85s ahead of current playhead are NEVER included.
 */
export function getNaturalSubtitlePhrase(
  visibleWords: TranscriptWord[] | undefined | null,
  activeWordIndex: number,
  currentPlayhead?: number
): TranscriptWord[] {
  if (!Array.isArray(visibleWords) || visibleWords.length === 0) return [];
  if (activeWordIndex < 0 || activeWordIndex >= visibleWords.length) return [];

  const activeWord = visibleWords[activeWordIndex];

  // If playhead is provided, verify we are within or near the active word
  if (
    typeof currentPlayhead === "number" &&
    (currentPlayhead < activeWord.start - 0.08 ||
      currentPlayhead > activeWord.end + 0.18)
  ) {
    return [];
  }

  // Backward expansion from activeWordIndex
  let startIndex = activeWordIndex;
  while (startIndex > 0) {
    const prevIdx = startIndex - 1;
    const prevWord = visibleWords[prevIdx];
    const currWord = visibleWords[startIndex];

    // Max 3 words preceding active word
    if (activeWordIndex - prevIdx >= 3) break;

    // Silence gap between words (> 0.45s indicates pause/breath)
    const gap = currWord.start - prevWord.end;
    if (gap > 0.45) break;

    // Punctuation check: previous word terminated the previous clause/sentence
    if (/[.!?;:¡¿]$/.test(prevWord.word.trim())) break;

    // Max total duration of card
    if (activeWord.end - prevWord.start > 2.2) break;

    startIndex = prevIdx;
  }

  // Forward expansion from activeWordIndex
  let endIndex = activeWordIndex;
  while (endIndex + 1 < visibleWords.length) {
    const nextIdx = endIndex + 1;
    const nextWord = visibleWords[nextIdx];
    const currWord = visibleWords[endIndex];

    // Max 4 words total in the phrase
    if (nextIdx - startIndex >= 4) break;

    // CRITICAL FIX: Silence gap between words (> 0.45s indicates speaker stopped)
    // If locutor says "¡Uf!" and waits 5s, gap is 5.0s > 0.45s, so nextWord is NOT included!
    const gap = nextWord.start - currWord.end;
    if (gap > 0.45) break;

    // Punctuation check: current word ends this clause/sentence
    if (/[.!?;:¡¿]$/.test(currWord.word.trim())) break;

    // Max total duration of card
    if (nextWord.end - visibleWords[startIndex].start > 2.2) break;

    // Don't show words too far ahead of playhead
    if (
      typeof currentPlayhead === "number" &&
      nextWord.start - currentPlayhead > 0.85
    ) {
      break;
    }

    endIndex = nextIdx;
  }

  return visibleWords.slice(startIndex, endIndex + 1);
}

