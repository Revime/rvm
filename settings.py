# -*- coding: utf-8 -*-
"""
Centralized Settings & Constants for the Automated Gaming Clip Pipeline (YPP Monetization Focus).
Implements Section 7.2 of MONETIZATION_GUIDELINE.md.
"""

from pathlib import Path
from typing import Any, Dict

try:
    import yaml
except ImportError:
    yaml = None

ROOT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = ROOT_DIR / "config.yaml"

# =====================================================================
#  HARD-CODED & EXTERNALIZED YPP MONETIZATION CONSTANTS (Sections 3–7)
# =====================================================================

# Section 3: High-Priority Keyword Entities & Hook Rules
HIGH_PRIORITY_KEYWORDS = [
    "GTA 6",
    "GTA VI",
    "Rockstar Games",
    "Vice City",
    "Lucia",
    "Jason",
    "PS5 Pro",
    "60 FPS",
    "vazamento",
    "leak",
    "trailer",
    "física",
    "physics",
    "NPC",
    "mapa",
    "map",
    "adiamento",
    "delay",
    "preço",
    "price",
]

GAMING_SLANG_PRESERVE = [
    "nerf",
    "buff",
    "FPS",
    "drop",
    "hype",
    "NPC",
    "ray tracing",
    "hitbox",
    "spawn",
    "open world",
    "shader",
    "upscaling",
]

COLD_OPEN_MIN_SECONDS: float = 3.0
COLD_OPEN_MAX_SECONDS: float = 5.0
CLUSTER_MIN_CLIPS: int = 2
CLUSTER_MAX_CLIPS: int = 4

# Section 4.1: Mandatory Original Voiceover Injection & Audio Ducking
INTRO_BRIDGE_MIN_SECONDS: float = 10.0
INTRO_BRIDGE_MAX_SECONDS: float = 15.0
INTER_CLIP_BRIDGE_MIN_SECONDS: float = 5.0
INTER_CLIP_BRIDGE_MAX_SECONDS: float = 8.0
SEAMLESS_LOOP_BRIDGE_SECONDS: float = 1.5
DUCKING_BG_DB: int = -22
DUCKING_EN_DUB_DB: int = -18
TARGET_LUFS: int = -14

# Section 4.2: Visual Pacing & Anti-Static Frame Rules
MAX_STATIC_SECONDS: float = 8.0
ZOOM_INTERVAL_MIN_SECONDS: float = 4.0
ZOOM_INTERVAL_MAX_SECONDS: float = 6.0
SLOW_ZOOM_MAX_FACTOR: float = 1.12
PUNCH_IN_ZOOM_FACTOR: float = 1.15
BROLL_MIN_COVERAGE_RATIO: float = 0.40
SPEED_MULTIPLIER_SHORTS: float = 1.08
SPEED_MULTIPLIER_MIN: float = 1.05
SPEED_MULTIPLIER_MAX: float = 1.10
SILENCE_THRESHOLD_DB: int = -35
SILENCE_MIN_DURATION: float = 0.35

# Section 5A: Format A — YouTube Shorts
SHORTS_WIDTH: int = 1080
SHORTS_HEIGHT: int = 1920
SHORTS_FPS: int = 60
MIN_SHORTS_DURATION: int = 35
MAX_SHORTS_DURATION: int = 55
SHORTS_TOP_RATIO: float = 0.55
SHORTS_BOTTOM_RATIO: float = 0.45
SHORTS_SUBTITLE_Y_RATIO: float = 0.55
SUBTITLE_ACTIVE_COLOR_HEX: str = "#FFD700"
SUBTITLE_INACTIVE_COLOR_HEX: str = "#FFFFFF"

# Section 5B: Format B — Long-Form Compilation / Analysis
LONG_WIDTH: int = 1920
LONG_HEIGHT: int = 1080
LONG_FPS: int = 60
MIN_LONG_DURATION: int = 485
MAX_LONG_DURATION: int = 720

# Section 6: Metadata & SEO Constraints
MAX_TITLE_CHARS: int = 55
TITLE_OPTIONS_COUNT: int = 3
MAX_THUMBNAIL_OVERLAY_WORDS: int = 3

# Section 8: Real-Time Hardware Telemetry & Critical Alert Thresholds
HW_MONITOR_INTERVAL_SECONDS: float = 1.5
HW_LOG_INTERVAL_SECONDS: float = 15.0
CPU_WARNING_PCT: float = 75.0
CPU_CRITICAL_PCT: float = 85.0
RAM_WARNING_PCT: float = 75.0
RAM_CRITICAL_PCT: float = 85.0
GPU_WARNING_PCT: float = 75.0
GPU_CRITICAL_PCT: float = 90.0
GPU_TEMP_CRITICAL_C: float = 83.0



def load_config() -> Dict[str, Any]:
    """Loads config.yaml and merges with default YPP monetization settings."""
    if CONFIG_PATH.exists() and yaml is not None:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}

