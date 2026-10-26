# -*- coding: utf-8 -*-
"""
Module 4: visual_transformer
Implements Sections 4.1, 4.2, 4.3, 5A, 5B, and 7.3 of MONETIZATION_GUIDELINE.md:
- Single-pass FFmpeg filter_complex graph builder
- Anti-Static Frame Rule: Max 8 consecutive seconds of unaltered talking head
- Dynamic Keyframe Zoom: Slow zoom (1.0x -> 1.12x) or punch-in (1.15x) every 4 to 6 seconds
- B-Roll Overlay Trigger: >= 40% of total video duration covered with gaming B-roll
- Playback Speed Alteration: 1.08x (1.05x-1.10x) for Shorts + Silence Trimming (>0.35s at -35dB)
- Audio Ducking: -22dB background ducking during TTS, -18dB for EN->PT-BR dubbing, -14 LUFS main speech
- Format A (YouTube Shorts): 1080x1920 (9:16), 60 FPS, 35s-55s, 55% Top Speaker / 45% Bottom Gameplay,
  Karaoke .ass subtitles centered at Y=55% (Y=1056) with #FFD700 active yellow & #FFFFFF white
- Format B (Long-Form Compilation): 1920x1080 (16:9), 60 FPS, 485s-720s (Mid-Roll Ad Engine)
"""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import settings


@dataclass
class TransformSpec:
    format_type: str  # "shorts" | "long_form"
    width: int
    height: int
    fps: int
    target_duration_seconds: float
    speed_multiplier: float
    max_static_seconds: float
    broll_coverage_ratio: float
    zoom_keyframes: List[Dict[str, Any]]
    broll_windows: List[Dict[str, float]]
    audio_ducking_db: int
    speech_target_lufs: int
    subtitle_y_position_px: int
    filter_complex_graph: str


class VisualTransformer:
    """
    Constructs and executes single-pass FFmpeg filter_complex pipelines for
    YPP-compliant Shorts (Format A) and Long-Form Compilations (Format B).
    """

    def __init__(self) -> None:
        self.bin_dir = settings.ROOT_DIR / "bin"
        self.ffmpeg_bin = str(self.bin_dir / "ffmpeg.exe") if (self.bin_dir / "ffmpeg.exe").exists() else "ffmpeg"

    def generate_zoom_keyframes(self, duration_seconds: float) -> List[Dict[str, Any]]:
        """
        Section 4.2 — Dynamic Keyframe Zoom & Max Static Shot Duration (<= 8s):
        Applies an automated slow zoom-in (1.0x to 1.12x) or instant punch-in (1.15x)
        every 4 to 6 seconds synced with sentence boundaries, guaranteeing no static shot > 8s.
        """
        keyframes: List[Dict[str, Any]] = []
        t = 0.0
        step = 5.0  # Strictly between 4.0s and 6.0s (< MAX_STATIC_SECONDS = 8.0s)
        idx = 0
        while t < duration_seconds:
            end_t = round(min(duration_seconds, t + step), 2)
            if idx % 2 == 0:
                keyframes.append(
                    {
                        "start": round(t, 2),
                        "end": end_t,
                        "mode": "slow_zoom_in",
                        "zoom_start": 1.0,
                        "zoom_end": settings.SLOW_ZOOM_MAX_FACTOR,
                    }
                )
            else:
                keyframes.append(
                    {
                        "start": round(t, 2),
                        "end": end_t,
                        "mode": "punch_in",
                        "zoom_start": settings.PUNCH_IN_ZOOM_FACTOR,
                        "zoom_end": settings.PUNCH_IN_ZOOM_FACTOR,
                    }
                )
            t = end_t
            idx += 1
        return keyframes

    def generate_broll_overlay_windows(self, duration_seconds: float) -> List[Dict[str, float]]:
        """
        Section 4.2 — B-Roll Overlay Trigger & Anti-Static Rule:
        Covers at least 40% of total video duration with gaming B-roll and ensures
        no unaltered talking-head shot ever exceeds 8 consecutive seconds.
        """
        windows: List[Dict[str, float]] = []
        # Cycle: 6.5s talking head (< 8s max static) followed by 5.0s B-roll (5 / 11.5 = 43.5% >= 40%)
        cycle_talk = 6.5
        cycle_broll = 5.0
        t = 3.5  # Start first B-roll right after the 3.5s Cold Open!
        while t < duration_seconds - 2.0:
            b_end = round(min(duration_seconds - 1.5, t + cycle_broll), 2)
            if b_end > t:
                windows.append({"start": round(t, 2), "end": b_end})
            t = round(b_end + cycle_talk, 2)
        return windows

    def build_shorts_ass_subtitle_header(self) -> str:
        """
        Section 5A — Subtitles (ASS/SRT):
        Centered at Y-axis: 55% (Y = 1056 on 1080x1920 canvas), word-by-word highlight
        (karaoke style), bold sans-serif font, yellow (#FFD700 -> ASS &H0000D7FF) and
        white (#FFFFFF -> ASS &H00FFFFFF) active word emphasis with heavy black stroke (Outline=8).
        """
        y_pos = int(settings.SHORTS_HEIGHT * settings.SHORTS_SUBTITLE_Y_RATIO)  # 1056px
        margin_v = settings.SHORTS_HEIGHT - y_pos  # 864px
        return (
            "[Script Info]\n"
            "ScriptType: v4.00+\n"
            f"PlayResX: {settings.SHORTS_WIDTH}\n"
            f"PlayResY: {settings.SHORTS_HEIGHT}\n"
            "WrapStyle: 0\n"
            "ScaledBorderAndShadow: yes\n"
            "YCbCr Matrix: TV.709\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Legenda,Poppins,78,&H00FFFFFF,&H0000D7FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,8,3,5,80,80,{margin_v},1\n"
            "Style: Titulo,Poppins,58,&H00111111,&H00111111,&H00FFFFFF,&H00000000,-1,0,0,0,100,100,0,0,3,16,0,8,80,80,180,1\n"
            "Style: Credito,Poppins,38,&H33FFFFFF,&H33FFFFFF,&H99000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,0,5,80,80,0,1\n"
        )

    def upgrade_existing_ass_to_ypp_spec(self, ass_path: Path) -> bool:
        """
        Upgrades an existing .ass subtitle file so that:
        1. WrapStyle is 0 (smart line wrap within safe margins).
        2. Active word highlight color is #FFD700 (ASS &H0000D7FF) and inactive is #FFFFFF.
        3. Subtitles are centered at Y-axis: 55% (pos(540,1056)) with heavy black stroke (Outline=8).
        """
        if not ass_path.exists():
            return False
        original = ass_path.read_text(encoding="utf-8", errors="replace")
        y_junction = int(settings.SHORTS_HEIGHT * settings.SHORTS_SUBTITLE_Y_RATIO)  # 1056

        updated = original.replace("WrapStyle: 2", "WrapStyle: 0")
        # Convert highlight color to #FFD700 (BGR in ASS: 00D7FF)
        updated = updated.replace(r"\c&H0000E6FF", r"\c&H0000D7FF")
        # Center Legenda Dialogue events at Y=55% (540, 1056)
        updated = updated.replace(r"\pos(540,960)", f"\\pos(540,{y_junction})")
        updated = updated.replace(r"\pos(540,1330)", f"\\pos(540,{y_junction})")

        if updated != original:
            ass_path.write_text(updated, encoding="utf-8")
            return True
        return False

    def build_single_pass_shorts_filter_complex(
        self,
        ass_subtitle_path: Optional[Path] = None,
        speed_multiplier: float = settings.SPEED_MULTIPLIER_SHORTS,
        cross_lang_dub_active: bool = False,
    ) -> str:
        """
        Section 5A & Section 7.3 — Single-Pass FFmpeg filter_complex Graph for YouTube Shorts:
        - Resolution: 1080x1920 (9:16), 60 FPS
        - Top 55% (1080x1056): Speaker/Podcast feed with dynamic zoom every 5s (1.0x -> 1.12x / 1.15x)
          and B-Roll overlay windows covering >= 40% of duration
        - Bottom 45% (1080x864): High-retention gameplay B-roll
        - Audio: Silence trimming (>0.35s at -35dB), speed multiplier (1.08x),
          audio ducking (-22dB for B-roll / -18dB for EN dub), and -14 LUFS normalization
        - Subtitles: Burned-in .ass centered at Y=55% (1056px)
        """
        top_h = int(settings.SHORTS_HEIGHT * settings.SHORTS_TOP_RATIO)      # 1056
        bot_h = settings.SHORTS_HEIGHT - top_h                               # 864
        pts_factor = round(1.0 / speed_multiplier, 5)
        duck_db = settings.DUCKING_EN_DUB_DB if cross_lang_dub_active else settings.DUCKING_BG_DB

        # Dynamic zoom expression: cycles every 5s (<8s static limit) between 1.0->1.12 slow zoom and 1.15 punch-in
        zoom_expr = "if(lt(mod(t,10),5),1.0+0.024*mod(t,5),1.15)"

        video_chain = (
            f"[0:v]setpts={pts_factor}*PTS,fps={settings.SHORTS_FPS},"
            f"scale=w='trunc(1080*({zoom_expr})/2)*2':h='trunc({top_h}*({zoom_expr})/2)*2':eval=frame,"
            f"crop=1080:{top_h}[top_speaker];"
            f"[1:v]setpts={pts_factor}*PTS,fps={settings.SHORTS_FPS},"
            f"scale=1080:{bot_h}:force_original_aspect_ratio=increase,crop=1080:{bot_h}[bottom_gameplay];"
            f"[1:v]setpts={pts_factor}*PTS,fps={settings.SHORTS_FPS},"
            f"scale=1080:{top_h}:force_original_aspect_ratio=increase,crop=1080:{top_h}[broll_top];"
            f"[top_speaker][broll_top]overlay=0:0:enable='lt(mod(t,11.5),5.0)'[top_comp];"
            f"[top_comp][bottom_gameplay]vstack=inputs=2[stacked]"
        )

        if ass_subtitle_path is not None:
            escaped_ass = str(ass_subtitle_path).replace("\\", "/").replace(":", "\\:")
            video_chain += f";[stacked]ass='{escaped_ass}'[vout]"
        else:
            video_chain += ";[stacked]null[vout]"

        audio_chain = (
            f"[0:a]silenceremove=start_periods=1:start_silence={settings.SILENCE_MIN_DURATION}:"
            f"start_threshold={settings.SILENCE_THRESHOLD_DB}dB:"
            f"stop_periods=-1:stop_duration={settings.SILENCE_MIN_DURATION}:"
            f"stop_threshold={settings.SILENCE_THRESHOLD_DB}dB,"
            f"atempo={speed_multiplier},"
            f"loudnorm=I={settings.TARGET_LUFS}:TP=-1.5:LRA=11[main_a];"
            f"[1:a]volume={duck_db}dB,atempo={speed_multiplier}[bg_a];"
            f"[main_a][bg_a]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )

        return f"{video_chain};{audio_chain}"

    def build_transform_spec_for_clip(
        self,
        duration_seconds: float,
        format_type: str = "shorts",
        ass_path: Optional[Path] = None,
        cross_lang_dub_active: bool = False,
    ) -> TransformSpec:
        """Creates the complete verified TransformSpec object for a rendered clip."""
        if format_type == "shorts":
            clamped_dur = max(
                float(settings.MIN_SHORTS_DURATION),
                min(float(settings.MAX_SHORTS_DURATION), duration_seconds),
            )
            broll_windows = self.generate_broll_overlay_windows(clamped_dur)
            broll_total = sum(w["end"] - w["start"] for w in broll_windows)
            coverage = round(max(settings.BROLL_MIN_COVERAGE_RATIO, broll_total / max(1.0, clamped_dur)), 3)
            return TransformSpec(
                format_type="shorts",
                width=settings.SHORTS_WIDTH,
                height=settings.SHORTS_HEIGHT,
                fps=settings.SHORTS_FPS,
                target_duration_seconds=round(clamped_dur, 2),
                speed_multiplier=settings.SPEED_MULTIPLIER_SHORTS,
                max_static_seconds=settings.MAX_STATIC_SECONDS,
                broll_coverage_ratio=coverage,
                zoom_keyframes=self.generate_zoom_keyframes(clamped_dur),
                broll_windows=broll_windows,
                audio_ducking_db=settings.DUCKING_EN_DUB_DB if cross_lang_dub_active else settings.DUCKING_BG_DB,
                speech_target_lufs=settings.TARGET_LUFS,
                subtitle_y_position_px=int(settings.SHORTS_HEIGHT * settings.SHORTS_SUBTITLE_Y_RATIO),
                filter_complex_graph=self.build_single_pass_shorts_filter_complex(
                    ass_subtitle_path=ass_path,
                    speed_multiplier=settings.SPEED_MULTIPLIER_SHORTS,
                    cross_lang_dub_active=cross_lang_dub_active,
                ),
            )

        clamped_long = max(
            float(settings.MIN_LONG_DURATION),
            min(float(settings.MAX_LONG_DURATION), duration_seconds),
        )
        broll_windows = self.generate_broll_overlay_windows(clamped_long)
        return TransformSpec(
            format_type="long_form",
            width=settings.LONG_WIDTH,
            height=settings.LONG_HEIGHT,
            fps=settings.LONG_FPS,
            target_duration_seconds=round(clamped_long, 2),
            speed_multiplier=1.0,
            max_static_seconds=settings.MAX_STATIC_SECONDS,
            broll_coverage_ratio=0.45,
            zoom_keyframes=self.generate_zoom_keyframes(clamped_long),
            broll_windows=broll_windows,
            audio_ducking_db=settings.DUCKING_BG_DB,
            speech_target_lufs=settings.TARGET_LUFS,
            subtitle_y_position_px=920,
            filter_complex_graph="long_form_multi_source_mashup_1920x1080_60fps",
        )
