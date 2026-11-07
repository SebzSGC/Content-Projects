"""ASS subtitles for the reference look.

* **Title** — white, heavy, thick black outline, two balanced lines centered on
  the seam between the camera and gameplay panels, for the first N seconds.
* **Captions** (optional) — short phrases of the streamer's words with the active
  word highlighted, in the upper part of the gameplay panel (game HUDs and
  in-game subtitles usually live at the bottom).
* **Game lines** (``captions == "all"``) — a quieter italic style.
"""

from __future__ import annotations

from typing import List, Sequence

from ..domain import RenderOptions, Speaker, Utterance, Word

ACTIVE = "&H0024D8FF&"  # warm yellow (BGR)
WHITE = "&H00FFFFFF&"


def ass_time(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = int(round((sec - int(sec)) * 100))
    if cs == 100:
        s, cs = s + 1, 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def escape(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ").strip()


def balance_lines(title: str, max_chars: int = 18) -> str:
    """Split a title into two lines of similar width when it's long."""
    words = title.split()
    if len(title) <= max_chars or len(words) < 2:
        return title
    best, best_diff = 1, len(title)
    for i in range(1, len(words)):
        diff = abs(len(" ".join(words[:i])) - len(" ".join(words[i:])))
        if diff < best_diff:
            best, best_diff = i, diff
    return " ".join(words[:best]) + r"\N" + " ".join(words[best:])


def caption_chunks(words: Sequence[Word], max_words: int = 3, max_chars: int = 16, max_gap: float = 0.45) -> List[List[Word]]:
    chunks: List[List[Word]] = []
    current: List[Word] = []
    for w in words:
        if current and (
            len(current) >= max_words
            or len(" ".join(x.text for x in current + [w])) > max_chars
            or w.start - current[-1].end > max_gap
            or current[-1].text.endswith((".", "?", "!", ","))
        ):
            chunks.append(current)
            current = []
        current.append(w)
    if current:
        chunks.append(current)
    return chunks


def build_ass(
    clip_start: float,
    clip_end: float,
    utterances: Sequence[Utterance],
    overlay_title: str,
    opts: RenderOptions,
    seam_y: int,
    game_top: int,
    game_height: int,
    title_font: str,
    caption_font: str,
) -> str:
    dur = clip_end - clip_start
    w, h = opts.width, opts.height
    header = f"""[Script Info]
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: {w}
PlayResY: {h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,{title_font},78,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,7,0,5,40,40,0,1
Style: Caption,{caption_font},70,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,5,60,60,0,1
Style: Game,{caption_font},50,&H00FFF2C8,&H000000FF,&H00000000,&H64000000,0,-1,0,0,100,100,0,0,1,4,1,5,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: List[str] = []
    title = escape(overlay_title)
    if title and opts.title_duration_sec > 0:
        end = min(dur, opts.title_duration_sec)
        events.append(
            f"Dialogue: 2,{ass_time(0)},{ass_time(end)},Title,,0,0,0,,{{\\an5\\pos({w // 2},{seam_y})\\fad(150,250)}}{balance_lines(title)}"
        )

    if opts.captions != "none":
        caption_y = game_top + int(game_height * 0.2)
        game_y = caption_y + 120
        for u in utterances:
            if u.end <= clip_start or u.start >= clip_end:
                continue
            if u.speaker == Speaker.GAME or u.source == "ocr":
                if opts.captions == "all":
                    a, b = max(0.0, u.start - clip_start), min(dur, u.end - clip_start)
                    events.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Game,,0,0,0,,{{\\an5\\pos({w // 2},{game_y})}}{escape(u.text)}")
                continue
            words = [x for x in u.words if x.end > clip_start and x.start < clip_end]
            events += _karaoke_events(words, clip_start, dur, w // 2, caption_y)
    return header + "\n".join(events) + "\n"


def _karaoke_events(words: Sequence[Word], clip_start: float, dur: float, x: int, y: int) -> List[str]:
    events: List[str] = []
    chunks = caption_chunks(words)
    for ci, chunk in enumerate(chunks):
        next_start = chunks[ci + 1][0].start if ci + 1 < len(chunks) else None
        for wi, word in enumerate(chunk):
            a = word.start - clip_start
            if wi + 1 < len(chunk):
                b = chunk[wi + 1].start - clip_start
            else:
                b = word.end - clip_start
                if next_start is not None and next_start - word.end < 0.3:
                    b = next_start - clip_start
            a, b = max(0.0, a), min(dur, max(b, a + 0.08))
            if b <= a:
                continue
            parts = []
            for other in chunk:
                text = escape(other.text).upper()
                parts.append(f"{{\\c{ACTIVE}}}{text}{{\\c{WHITE}}}" if other is word else text)
            events.append(f"Dialogue: 1,{ass_time(a)},{ass_time(b)},Caption,,0,0,0,,{{\\an5\\pos({x},{y})}}{' '.join(parts)}")
    return events
