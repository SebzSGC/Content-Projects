"""Generates deterministic offline API fixtures (`tests/fixtures/api/*`) and synthetic golden split recordings (`tests/golden/gameplay.mp4`, `tests/golden/camara.mp4`)."""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
import soundfile as sf
from clipsmedia.ffmpeg import resolve_binary

ROOT_DIR = Path(__file__).resolve().parents[2]
GOLDEN_DIR = ROOT_DIR / "tests" / "golden"
FIXTURES_DIR = ROOT_DIR / "tests" / "fixtures" / "api"

DURATION_SEC = 42.0
FPS = 30
WIDTH = 1280
HEIGHT = 720
SR = 16_000
CAM_SHIFT_SEC = 0.40  # cam_t = master_t + 0.40s

# 9 natural utterances on master timeline (u0001..u0009):
# Notice the 1.35s silence gap between u0004 (ends 16.95s) and u0005 (starts 18.30s) -> triggers jump cut!
# Notice u0006 (23.0..27.1s) -> high-intensity reaction scream/clutch -> triggers camera_full + zoom + scream protection!
MASTER_UTTERANCES: List[Tuple[float, float, str, float]] = [
    (2.00, 4.20, "Bueno gente entramos a la ronda final del torneo.", 0.35),
    (5.00, 8.50, "Mira cómo asoman los tres por medio sin humo ni nada.", 0.45),
    (9.25, 12.90, "Primero a la cabeza con el rifle qué locura de disparo hermano.", 0.62),
    (13.65, 16.95, "Esperen callados que queda el último escondido detrás de la caja.", 0.40),
    # 1.35s dramatic silence [16.95 .. 18.30] (> 0.7s -> jump cut trims it!)
    (18.30, 22.20, "Ahí viene corriendo apunta bien y fuego directo al centro.", 0.58),
    (23.00, 27.10, "NO PUEDE SER CLUTCH HISTÓRICO EN EL ÚLTIMO SEGUNDO!", 0.96),
    (27.85, 31.70, "VAMOS CARAJO así se cierra una partida imposible amigos!", 0.86),
    (32.45, 36.10, "Suscríbanse ya mismo porque esta jugada queda para la historia.", 0.50),
    (37.10, 40.10, "Pasemos al lobby a revisar las estadísticas de la partida.", 0.34),
]


def build_word_schedule() -> List[Dict[str, Any]]:
    """Expand utterances into word-level timestamps in CAMERA time (`cam_t = master_t + CAM_SHIFT_SEC`)."""
    words_cam: List[Dict[str, Any]] = []
    for m_start, m_end, sentence, amp in MASTER_UTTERANCES:
        tokens = sentence.split()
        span = m_end - m_start
        step = span / len(tokens)
        for i, tok in enumerate(tokens):
            ws_m = m_start + i * step + 0.02
            we_m = m_start + (i + 1) * step - 0.03
            ws_c = round(ws_m + CAM_SHIFT_SEC, 3)
            we_c = round(max(ws_c + 0.06, we_m + CAM_SHIFT_SEC), 3)
            clean_word = tok.strip(".,!¡¿?").lower()
            words_cam.append(
                {
                    "word": clean_word,
                    "punctuated_word": tok,
                    "start": ws_c,
                    "end": we_c,
                    "confidence": 0.985,
                    "master_start": round(ws_m, 3),
                    "master_end": round(we_m, 3),
                    "amp": amp,
                }
            )
    return words_cam


def write_api_fixtures(words_cam: List[Dict[str, Any]]) -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    full_transcript = " ".join(w["punctuated_word"] for w in words_cam)

    deepgram_payload = {
        "metadata": {
            "request_id": "golden-dg-nova3-001",
            "duration": DURATION_SEC,
            "channels": 1,
            "models": ["nova-3"],
        },
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": full_transcript,
                            "confidence": 0.985,
                            "words": [
                                {
                                    "word": w["word"],
                                    "punctuated_word": w["punctuated_word"],
                                    "start": w["start"],
                                    "end": w["end"],
                                    "confidence": w["confidence"],
                                }
                                for w in words_cam
                            ],
                        }
                    ]
                }
            ]
        },
    }
    (FIXTURES_DIR / "deepgram_nova3.json").write_text(
        json.dumps(deepgram_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    groq_payload = {
        "task": "transcribe",
        "language": "spanish",
        "duration": DURATION_SEC,
        "text": full_transcript,
        "words": [
            {
                "word": w["punctuated_word"],
                "start": w["start"],
                "end": w["end"],
            }
            for w in words_cam
        ],
    }
    (FIXTURES_DIR / "groq_whisper.json").write_text(
        json.dumps(groq_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    curation_inner = {
        "clips": [
            {
                "start_id": "u0002",
                "end_id": "u0008",
                "hook": "Mira cómo asoman los tres por medio sin humo ni nada.",
                "overlay_title": "CLUTCH 1v3 EN RONDA FINAL",
                "post_title": "ME DEJARON SOLO CONTRA TRES EN LA FINAL Y PASÓ ESTO 🔥",
                "hashtags": ["gaming", "clutch", "valorant", "clips", "streamer"],
                "emphasis_words": ["cabeza", "locura", "fuego", "CLUTCH", "HISTÓRICO", "CARAJO"],
                "emojis": [
                    {"word": "locura", "emoji": "1f92f"},
                    {"word": "fuego", "emoji": "1f525"},
                    {"word": "CLUTCH", "emoji": "1f631"},
                    {"word": "HISTÓRICO", "emoji": "1f480"},
                ],
                "score": 89,
                "reason": "Historia completa con preparación táctica, bajas rápidas, tensión silenciosa y reacción explosiva en el clutch.",
            }
        ]
    }
    gemini_payload = {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [{"text": json.dumps(curation_inner, ensure_ascii=False)}],
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 620,
            "candidatesTokenCount": 245,
            "totalTokenCount": 865,
        },
    }
    (FIXTURES_DIR / "gemini_curate.json").write_text(
        json.dumps(gemini_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def synthesize_audio_tracks(words_cam: List[Dict[str, Any]], work_dir: Path) -> Tuple[Path, Path, Path]:
    """Create camera mic WAV, gameplay clean FX WAV, and gameplay stream-mix WAV with exact word envelopes."""
    n = int(DURATION_SEC * SR)
    t = np.arange(n, dtype=np.float64) / SR
    rng = np.random.default_rng(42)

    cam_audio = np.zeros(n, dtype=np.float64)
    master_voice = np.zeros(n, dtype=np.float64)

    # Harmonic speech-like bursts aligned to every word (both in camera time and master time)
    for idx, w in enumerate(words_cam):
        f0 = 135.0 + (idx % 7) * 14.0
        amp = float(w["amp"])

        for target_arr, s_sec, e_sec in (
            (cam_audio, float(w["start"]), float(w["end"])),
            (master_voice, float(w["master_start"]), float(w["master_end"])),
        ):
            i0 = max(0, min(n - 1, int(round(s_sec * SR))))
            i1 = max(i0 + 1, min(n, int(round(e_sec * SR))))
            seg_t = np.arange(i1 - i0, dtype=np.float64) / SR
            env = np.ones_like(seg_t)
            atk = min(len(seg_t) // 3, int(0.015 * SR))
            rel = min(len(seg_t) // 3, int(0.025 * SR))
            if atk > 1:
                env[:atk] = np.linspace(0.0, 1.0, atk)
            if rel > 1:
                env[-rel:] = np.linspace(1.0, 0.0, rel)
            carrier = (
                0.55 * np.sin(2 * math.pi * f0 * seg_t)
                + 0.30 * np.sin(2 * math.pi * (2.0 * f0) * seg_t + 0.4)
                + 0.15 * np.sin(2 * math.pi * (3.1 * f0) * seg_t)
            )
            target_arr[i0:i1] += amp * env * carrier

    # Add a non-verbal laugh/scream reaction burst during [27.25..27.75] master so scream protection is verifiable too
    for target_arr, shift in ((cam_audio, CAM_SHIFT_SEC), (master_voice, 0.0)):
        i0 = int((27.25 + shift) * SR)
        i1 = int((27.75 + shift) * SR)
        seg_t = np.arange(i1 - i0, dtype=np.float64) / SR
        burst = 0.85 * np.sin(2 * math.pi * 420.0 * seg_t) * np.sin(2 * math.pi * 9.0 * seg_t)
        target_arr[i0:i1] += burst

    # Clean game audio: subtle ambient pad + sharp weapon/explosion transients at key action timestamps
    game_clean = 0.015 * np.sin(2 * math.pi * 90.0 * t) + 0.004 * rng.standard_normal(n)
    game_events = [
        (9.50, 0.35, 0.65),   # first rifle headshot
        (11.10, 0.30, 0.55),  # second impact
        (20.60, 0.40, 0.72),  # final shot
        (23.15, 0.85, 0.92),  # clutch win fanfare / explosion
        (25.40, 0.50, 0.78),
    ]
    for ev_t, ev_dur, ev_amp in game_events:
        i0 = int(ev_t * SR)
        i1 = min(n, int((ev_t + ev_dur) * SR))
        seg_t = np.arange(i1 - i0, dtype=np.float64) / SR
        decay = np.exp(-5.5 * seg_t / max(0.1, ev_dur))
        boom = (
            0.6 * np.sin(2 * math.pi * (160.0 - 90.0 * seg_t) * seg_t)
            + 0.4 * rng.standard_normal(len(seg_t))
        )
        game_clean[i0:i1] += ev_amp * decay * boom
        # Subtle headphone/speaker bleed into camera mic shifted by CAM_SHIFT_SEC
        ci0 = min(n - 1, int((ev_t + CAM_SHIFT_SEC) * SR))
        ci1 = min(n, ci0 + (i1 - i0))
        cam_audio[ci0:ci1] += 0.14 * ev_amp * decay[: ci1 - ci0] * boom[: ci1 - ci0]

    # Stream mix on gameplay track 0 = clean game + streamer voice (standard OBS Track 1 stream mix!)
    game_mix = np.clip(0.65 * game_clean + 0.75 * master_voice, -0.97, 0.97)
    cam_final = np.clip(cam_audio + 0.0015 * rng.standard_normal(n), -0.97, 0.97)
    game_clean_final = np.clip(game_clean, -0.97, 0.97)

    cam_wav = work_dir / "cam_src.wav"
    mix_wav = work_dir / "game_mix_src.wav"
    clean_wav = work_dir / "game_clean_src.wav"
    sf.write(str(cam_wav), cam_final.astype(np.float32), SR)
    sf.write(str(mix_wav), game_mix.astype(np.float32), SR)
    sf.write(str(clean_wav), game_clean_final.astype(np.float32), SR)
    return cam_wav, mix_wav, clean_wav


def draw_realistic_synthetic_face(frame: np.ndarray, cx_px: int, cy_px: int, head_h: int, mouth_open: float) -> None:
    """Render a soft-shaded human face portrait that reliably triggers MediaPipe BlazeFace."""
    head_w = int(head_h * 0.76)

    # Shoulders / hoodie
    cv2.ellipse(
        frame,
        (cx_px, cy_px + int(head_h * 1.08)),
        (int(head_w * 1.55), int(head_h * 0.72)),
        0,
        180,
        360,
        (48, 42, 62),
        -1,
        cv2.LINE_AA,
    )
    # Neck
    neck_w = int(head_w * 0.36)
    cv2.rectangle(
        frame,
        (cx_px - neck_w, cy_px + int(head_h * 0.35)),
        (cx_px + neck_w, cy_px + int(head_h * 0.72)),
        (132, 156, 198),
        -1,
    )
    # Back hair
    cv2.ellipse(
        frame,
        (cx_px, cy_px - int(head_h * 0.08)),
        (int(head_w * 0.56), int(head_h * 0.56)),
        0,
        0,
        360,
        (28, 32, 42),
        -1,
        cv2.LINE_AA,
    )
    # Ears
    for side in (-1, 1):
        cv2.ellipse(
            frame,
            (cx_px + side * int(head_w * 0.50), cy_px + int(head_h * 0.02)),
            (int(head_w * 0.09), int(head_h * 0.14)),
            0,
            0,
            360,
            (136, 162, 206),
            -1,
            cv2.LINE_AA,
        )

    # Base skin oval (BGR warm skin tone)
    cv2.ellipse(
        frame,
        (cx_px, cy_px),
        (int(head_w * 0.49), int(head_h * 0.50)),
        0,
        0,
        360,
        (148, 176, 222),
        -1,
        cv2.LINE_AA,
    )
    # Forehead & cheek highlight for 3D shading
    cv2.ellipse(
        frame,
        (cx_px, cy_px - int(head_h * 0.12)),
        (int(head_w * 0.33), int(head_h * 0.22)),
        0,
        0,
        360,
        (164, 192, 236),
        -1,
        cv2.LINE_AA,
    )
    for side in (-1, 1):
        # Eye socket subtle shadow (key feature for BlazeFace anchor!)
        ex = cx_px + side * int(head_w * 0.19)
        ey = cy_px - int(head_h * 0.06)
        cv2.ellipse(
            frame,
            (ex, ey),
            (int(head_w * 0.13), int(head_h * 0.08)),
            0,
            0,
            360,
            (118, 140, 182),
            -1,
            cv2.LINE_AA,
        )
        # Sclera
        cv2.ellipse(
            frame,
            (ex, ey),
            (int(head_w * 0.09), int(head_h * 0.042)),
            0,
            0,
            360,
            (238, 242, 246),
            -1,
            cv2.LINE_AA,
        )
        # Iris & pupil
        cv2.circle(frame, (ex, ey), max(3, int(head_w * 0.042)), (52, 64, 88), -1, cv2.LINE_AA)
        cv2.circle(frame, (ex, ey), max(2, int(head_w * 0.021)), (18, 20, 24), -1, cv2.LINE_AA)
        cv2.circle(
            frame,
            (ex - max(1, int(head_w * 0.012)), ey - max(1, int(head_w * 0.012))),
            max(1, int(head_w * 0.01)),
            (250, 250, 255),
            -1,
            cv2.LINE_AA,
        )
        # Upper eyelid crease
        cv2.ellipse(
            frame,
            (ex, ey - int(head_h * 0.005)),
            (int(head_w * 0.095), int(head_h * 0.045)),
            0,
            190,
            350,
            (45, 50, 65),
            max(2, int(head_h * 0.012)),
            cv2.LINE_AA,
        )
        # Eyebrow
        bx0 = ex - int(head_w * 0.11)
        bx1 = ex + int(head_w * 0.11)
        by = ey - int(head_h * 0.09)
        cv2.line(frame, (bx0, by + side * 2), (bx1, by - side * 2), (32, 36, 48), max(3, int(head_h * 0.028)), cv2.LINE_AA)

    # Nose bridge + tip + nostrils
    ny_top = cy_px - int(head_h * 0.06)
    ny_bot = cy_px + int(head_h * 0.11)
    cv2.line(frame, (cx_px, ny_top), (cx_px, ny_bot), (170, 198, 240), max(2, int(head_w * 0.04)), cv2.LINE_AA)
    cv2.ellipse(
        frame,
        (cx_px, ny_bot + int(head_h * 0.01)),
        (int(head_w * 0.085), int(head_h * 0.045)),
        0,
        0,
        360,
        (126, 150, 194),
        -1,
        cv2.LINE_AA,
    )
    for side in (-1, 1):
        cv2.circle(
            frame,
            (cx_px + side * int(head_w * 0.045), ny_bot + int(head_h * 0.02)),
            max(2, int(head_w * 0.018)),
            (68, 78, 105),
            -1,
            cv2.LINE_AA,
        )

    # Mouth / lips (opens dynamically with speech!)
    my = cy_px + int(head_h * 0.25)
    mw = int(head_w * 0.17)
    mh = max(3, int(head_h * (0.028 + 0.065 * mouth_open)))
    cv2.ellipse(frame, (cx_px, my), (mw, mh + 3), 0, 0, 360, (108, 102, 168), -1, cv2.LINE_AA)
    if mouth_open > 0.15:
        cv2.ellipse(frame, (cx_px, my), (int(mw * 0.78), mh - 1), 0, 0, 360, (36, 32, 52), -1, cv2.LINE_AA)
        cv2.ellipse(frame, (cx_px, my - int(mh * 0.45)), (int(mw * 0.62), max(1, int(mh * 0.28))), 0, 0, 360, (235, 238, 242), -1, cv2.LINE_AA)

    # Top hair bangs
    cv2.ellipse(
        frame,
        (cx_px, cy_px - int(head_h * 0.36)),
        (int(head_w * 0.50), int(head_h * 0.20)),
        0,
        175,
        365,
        (28, 32, 42),
        -1,
        cv2.LINE_AA,
    )


def encode_video_from_frames(
    out_mp4: Path,
    audio_inputs: List[Path],
    frame_generator,
) -> None:
    ff = resolve_binary("ffmpeg")
    cmd: List[str] = [
        ff,
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{WIDTH}x{HEIGHT}",
        "-r",
        str(FPS),
        "-i",
        "pipe:0",
    ]
    for a_in in audio_inputs:
        cmd += ["-i", str(a_in)]

    cmd += ["-map", "0:v:0"]
    for idx in range(len(audio_inputs)):
        cmd += ["-map", f"{idx + 1}:a:0"]

    cmd += [
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        str(out_mp4),
    ]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for frame in frame_generator():
            proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
    err = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
    rc = proc.wait(timeout=60)
    if rc != 0:
        raise RuntimeError(f"FFmpeg falló generando {out_mp4.name}: {err}")


def generate_golden_assets(force: bool = False) -> Tuple[Path, Path]:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    gp_mp4 = GOLDEN_DIR / "gameplay.mp4"
    cam_mp4 = GOLDEN_DIR / "camara.mp4"

    words_cam = build_word_schedule()
    write_api_fixtures(words_cam)

    if gp_mp4.is_file() and cam_mp4.is_file() and not force:
        return gp_mp4, cam_mp4

    tmp_dir = GOLDEN_DIR / "_tmp_audio"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    cam_wav, mix_wav, clean_wav = synthesize_audio_tracks(words_cam, tmp_dir)

    total_frames = int(DURATION_SEC * FPS)

    def _camera_frames():
        bg = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        bg[:, :] = (34, 26, 24)
        # Neon LED streamer background accents
        cv2.rectangle(bg, (60, 50), (360, 420), (85, 35, 65), -1)
        cv2.rectangle(bg, (920, 70), (1210, 450), (45, 70, 35), -1)
        bg = cv2.GaussianBlur(bg, (31, 31), 0)

        for f_idx in range(total_frames):
            t_cam = f_idx / FPS
            t_m = t_cam - CAM_SHIFT_SEC
            frame = bg.copy()

            # Smooth horizontal head motion + excited lean-in on clutch
            lean = 1.16 if 22.8 <= t_m <= 28.5 else 1.0
            cx = int(WIDTH * (0.50 + 0.11 * math.sin(2 * math.pi * t_cam / 9.5)))
            cy = int(HEIGHT * (0.43 + 0.03 * math.cos(2 * math.pi * t_cam / 6.0)))
            head_h = int(250 * lean)

            # Mouth open amount when speaking
            mouth = 0.05
            for ws in words_cam:
                if ws["start"] <= t_cam <= ws["end"]:
                    mouth = min(1.0, 0.35 + 0.65 * abs(math.sin(t_cam * 28.0)) * ws["amp"])
                    break

            # Brief <1s occlusion [11.5..12.0s] to exercise gap interpolation
            if not (11.5 <= t_m <= 12.0):
                draw_realistic_synthetic_face(frame, cx, cy, head_h, mouth)
                # Soft blur pass so skin gradients match real webcam sensor texture
                roi_x0 = max(0, cx - head_h)
                roi_x1 = min(WIDTH, cx + head_h)
                roi_y0 = max(0, cy - head_h)
                roi_y1 = min(HEIGHT, cy + head_h)
                frame[roi_y0:roi_y1, roi_x0:roi_x1] = cv2.GaussianBlur(
                    frame[roi_y0:roi_y1, roi_x0:roi_x1], (5, 5), 0
                )

            yield frame

    def _gameplay_frames():
        for f_idx in range(total_frames):
            t_m = f_idx / FPS
            frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
            # Dynamic arena floor/sky
            frame[: HEIGHT // 2, :] = (58, 44, 32)
            frame[HEIGHT // 2 :, :] = (38, 46, 42)

            # Moving targets & high-motion clutch burst around 20..28s
            speed = 2.6 if 19.5 <= t_m <= 28.5 else 0.9
            tx = int(WIDTH * (0.5 + 0.28 * math.sin(t_m * speed * 2.1)))
            ty = int(HEIGHT * (0.48 + 0.14 * math.cos(t_m * speed * 1.7)))
            cv2.rectangle(frame, (tx - 70, ty - 95), (tx + 70, ty + 95), (48, 92, 230), -1)
            cv2.circle(frame, (tx, ty - 55), 26, (80, 180, 250), -1)

            # Crosshair in center
            cv2.line(frame, (WIDTH // 2 - 18, HEIGHT // 2), (WIDTH // 2 + 18, HEIGHT // 2), (80, 255, 80), 2)
            cv2.line(frame, (WIDTH // 2, HEIGHT // 2 - 18), (WIDTH // 2, HEIGHT // 2 + 18), (80, 255, 80), 2)

            # Flash on clutch kills
            if any(abs(t_m - kt) < 0.14 for kt in (9.50, 11.10, 20.60, 23.15)):
                frame = cv2.addWeighted(frame, 0.55, np.full_like(frame, 240), 0.45, 0)

            yield frame

    encode_video_from_frames(cam_mp4, [cam_wav], _camera_frames)
    # Gameplay has Track 0 = stream mix (voice + game) and Track 1 = clean game audio!
    encode_video_from_frames(gp_mp4, [mix_wav, clean_wav], _gameplay_frames)

    for f in (cam_wav, mix_wav, clean_wav):
        f.unlink(missing_ok=True)
    tmp_dir.rmdir()
    return gp_mp4, cam_mp4


if __name__ == "__main__":
    gp, cm = generate_golden_assets(force=True)
    print(f"Generated golden gameplay -> {gp} ({gp.stat().st_size // 1024} KB)")
    print(f"Generated golden camera   -> {cm} ({cm.stat().st_size // 1024} KB)")
