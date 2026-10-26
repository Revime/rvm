# -*- coding: utf-8 -*-
"""
Module 1: ingestor_and_transcriber
Downloads sources (yt-dlp), trims dead-air silences (> 0.35s at -35dB),
and generates word-level timestamps (Faster-Whisper) with source language detection.
"""

import json
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import settings


@dataclass
class WordTimestamp:
    word: str
    start: float
    end: float
    probability: float = 1.0


@dataclass
class TranscriptSegment:
    id: int
    start: float
    end: float
    text: str
    words: List[WordTimestamp] = field(default_factory=list)
    speaker_channel: str = ""
    source_id: str = ""
    language: str = "pt"


class IngestorAndTranscriber:
    """
    Handles source ingestion, dead-air silence removal specification, and
    word-level timestamp transcription via Faster-Whisper.
    """

    def __init__(
        self,
        work_dir: Optional[Path] = None,
        whisper_model: str = "small",
        device: str = "cpu",
    ) -> None:
        self.root_dir = settings.ROOT_DIR
        self.work_dir = work_dir or (self.root_dir / "trabalho")
        self.bin_dir = self.root_dir / "bin"
        self.ffmpeg_bin = str(self.bin_dir / "ffmpeg.exe") if (self.bin_dir / "ffmpeg.exe").exists() else "ffmpeg"
        self.whisper_model = whisper_model
        self.device = device

    def build_silence_remove_filter(
        self,
        threshold_db: int = settings.SILENCE_THRESHOLD_DB,
        min_duration: float = settings.SILENCE_MIN_DURATION,
    ) -> str:
        """
        Section 4.2: Silence Trimming — Automatically cut any audio silence
        exceeding 0.35 seconds (silenceremove filter).
        """
        return (
            f"silenceremove=start_periods=1:start_silence={min_duration}:start_threshold={threshold_db}dB:"
            f"stop_periods=-1:stop_duration={min_duration}:stop_threshold={threshold_db}dB"
        )

    def load_existing_transcription(self, episode_dir: Path) -> Dict[str, Any]:
        """
        Loads word-level and segment-level transcription from an existing RVM episode folder
        (trabalho/<episode_id>/transcricao.json and info.json).
        """
        trans_path = episode_dir / "transcricao.json"
        info_path = episode_dir / "info.json"

        info_data: Dict[str, Any] = {}
        if info_path.exists():
            info_data = json.loads(info_path.read_text(encoding="utf-8", errors="replace"))

        segments_raw: Any = []
        if trans_path.exists():
            segments_raw = json.loads(trans_path.read_text(encoding="utf-8", errors="replace"))

        if isinstance(segments_raw, dict):
            language = segments_raw.get("idioma") or segments_raw.get("language") or "pt"
            seg_list = segments_raw.get("segmentos") or segments_raw.get("segments") or []
        elif isinstance(segments_raw, list):
            language = info_data.get("idioma", "pt")
            seg_list = segments_raw
        else:
            language = "pt"
            seg_list = []

        parsed_segments: List[TranscriptSegment] = []
        for idx, seg in enumerate(seg_list):
            words_list: List[WordTimestamp] = []
            for w in seg.get("palavras") or seg.get("words") or []:
                words_list.append(
                    WordTimestamp(
                        word=str(w.get("palavra") or w.get("word") or "").strip(),
                        start=float(w.get("inicio") if "inicio" in w else w.get("start", 0.0)),
                        end=float(w.get("fim") if "fim" in w else w.get("end", 0.0)),
                        probability=float(w.get("prob", w.get("probability", 1.0))),
                    )
                )
            parsed_segments.append(
                TranscriptSegment(
                    id=idx,
                    start=float(seg.get("inicio") if "inicio" in seg else seg.get("start", 0.0)),
                    end=float(seg.get("fim") if "fim" in seg else seg.get("end", 0.0)),
                    text=str(seg.get("texto") or seg.get("text") or "").strip(),
                    words=words_list,
                    speaker_channel=str(info_data.get("canal", "Creator")),
                    source_id=str(info_data.get("id", episode_dir.name)),
                    language=language,
                )
            )

        return {
            "episode_id": info_data.get("id", episode_dir.name),
            "title": info_data.get("titulo", episode_dir.name),
            "channel": info_data.get("canal", "Unknown"),
            "source_url": info_data.get("link", ""),
            "video_path": info_data.get("video", str(episode_dir / "video.mp4")),
            "duration": float(info_data.get("duracao", 0.0)),
            "language": language,
            "segments": [asdict(s) for s in parsed_segments],
        }

    def transcribe_audio_with_word_timestamps(
        self,
        media_path: Path,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Runs Faster-Whisper with word_timestamps=True and VAD filtering to produce
        word-level timestamps required for karaoke subtitles and dynamic zoom triggers.
        """
        from faster_whisper import WhisperModel

        model = WhisperModel(self.whisper_model, device=self.device, compute_type="int8")
        segments_gen, info = model.transcribe(
            str(media_path),
            language=language,
            word_timestamps=True,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": int(settings.SILENCE_MIN_DURATION * 1000)},
        )

        segments: List[Dict[str, Any]] = []
        for idx, seg in enumerate(segments_gen):
            words = [
                {
                    "word": w.word.strip(),
                    "start": round(float(w.start), 3),
                    "end": round(float(w.end), 3),
                    "probability": round(float(w.probability), 3),
                }
                for w in (seg.words or [])
            ]
            segments.append(
                {
                    "id": idx,
                    "start": round(float(seg.start), 3),
                    "end": round(float(seg.end), 3),
                    "text": seg.text.strip(),
                    "words": words,
                }
            )

        return {
            "language": info.language,
            "language_probability": round(float(info.language_probability), 3),
            "duration": round(float(info.duration), 3),
            "segments": segments,
        }
