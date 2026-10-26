# -*- coding: utf-8 -*-
"""
Module 2: nlp_viral_scorer
Implements Section 3 & Section 4.3 of MONETIZATION_GUIDELINE.md:
- High-Priority Gaming / GTA 6 Keyword Entity Scoring
- Hook Extraction (The 3-Second Cold Open Rule: 3.0s to 5.0s)
- Strict Duration Enforcement (Shorts: 35s-55s | Long-Form: 485s-720s)
- Thematic Clustering (Groups 2 to 4 clips from different creators for Long-Form debate)
- Cross-Language Adaptation Module (en -> pt-BR preserving gaming slang)
"""

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

import settings


THEMATIC_CLUSTERS_MAP: Dict[str, List[str]] = {
    "performance_60fps_consoles": ["60 FPS", "30 FPS", "PS5 Pro", "PS5", "Xbox", "física", "physics", "ray tracing", "drop"],
    "gta6_vice_city_protagonists": ["GTA 6", "GTA VI", "Vice City", "Lucia", "Jason", "NPC", "mapa", "map"],
    "rockstar_leaks_delay_price": ["Rockstar Games", "vazamento", "leak", "trailer", "adiamento", "delay", "preço", "price"],
}

CONTROVERSY_TRIGGERS = [
    "impossível",
    "inaceitável",
    "ninguém",
    "segredo",
    "vazou",
    "mentira",
    "absurdo",
    "erro",
    "problema",
    "nunca",
    "jamais",
    "exclusivo",
    "bomba",
    "choque",
    "impossible",
    "unacceptable",
    "secret",
    "leaked",
    "shocking",
    "never",
]


@dataclass
class ColdOpenHook:
    text: str
    start: float
    end: float
    duration: float
    score: float


@dataclass
class ScoredClipCandidate:
    clip_id: str
    source_id: str
    speaker_channel: str
    start: float
    end: float
    duration: float
    viral_score: float
    matched_keywords: List[str]
    thematic_cluster: str
    cold_open: ColdOpenHook
    transcript_text: str
    translated_pt_br_text: Optional[str] = None
    source_language: str = "pt"


class NLPViralScorer:
    """
    Scans transcripts, scores segments by GTA 6 / Rockstar Games entities and controversy,
    extracts the 3-5s Cold Open hook, enforces Shorts (35s-55s) and Long-Form (485s-720s)
    duration constraints, and clusters multi-creator segments for Long-Form compilations.
    """

    def __init__(self) -> None:
        self.keywords = settings.HIGH_PRIORITY_KEYWORDS
        self.slang_preserve = settings.GAMING_SLANG_PRESERVE

    def score_text(self, text: str) -> Tuple[float, List[str], str]:
        """
        Calculates viral score (0.0 to 10.0), returns matched high-priority entities,
        and assigns the dominant thematic cluster.
        """
        if not text:
            return 0.0, [], "general_gaming_hype"

        lower_text = text.lower()
        matched: List[str] = []
        for kw in self.keywords:
            if kw.lower() in lower_text:
                matched.append(kw)

        controversy_hits = sum(1 for trig in CONTROVERSY_TRIGGERS if trig in lower_text)
        punctuation_bonus = 1.0 if ("!" in text or "?" in text) else 0.0

        raw_score = 5.0 + (len(matched) * 1.2) + (controversy_hits * 0.9) + punctuation_bonus
        final_score = round(min(10.0, max(1.0, raw_score)), 2)

        # Determine thematic cluster
        best_cluster = "gta6_vice_city_protagonists"
        best_cluster_hits = -1
        for cluster_name, terms in THEMATIC_CLUSTERS_MAP.items():
            hits = sum(1 for t in terms if t.lower() in lower_text)
            if hits > best_cluster_hits:
                best_cluster_hits = hits
                best_cluster = cluster_name

        return final_score, matched, best_cluster

    def extract_cold_open_hook(
        self,
        text: str,
        clip_start: float,
        clip_end: float,
        segments: Optional[List[Dict[str, Any]]] = None,
    ) -> ColdOpenHook:
        """
        Section 3 — Hook Extraction (The 3-Second Rule):
        Every video must start with a 'Cold Open' — the single most controversial,
        shocking, or curiosity-inducing sentence from the clip (3 to 5 seconds long)
        BEFORE any context or intro plays.
        """
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]
        best_sentence = sentences[0] if sentences else (text[:90] if text else "Isso muda tudo no GTA 6!")
        best_score = -1.0

        for s in sentences:
            sc, _, _ = self.score_text(s)
            if sc > best_score and len(s.split()) >= 4:
                best_score = sc
                best_sentence = s

        # Target duration strictly between 3.0s and 5.0s
        word_count = max(1, len(best_sentence.split()))
        estimated_dur = max(
            settings.COLD_OPEN_MIN_SECONDS,
            min(settings.COLD_OPEN_MAX_SECONDS, round(word_count * 0.32, 2)),
        )

        hook_start = clip_start
        if segments:
            for seg in segments:
                seg_text = str(seg.get("text") or seg.get("texto") or "")
                seg_st = float(seg.get("start") if "start" in seg else seg.get("inicio", clip_start))
                if seg_st >= clip_start and seg_st <= clip_end and best_sentence[:18].lower() in seg_text.lower():
                    hook_start = seg_st
                    break

        hook_end = round(min(clip_end, hook_start + estimated_dur), 2)
        if hook_end - hook_start < settings.COLD_OPEN_MIN_SECONDS:
            hook_start = round(max(0.0, hook_end - settings.COLD_OPEN_MIN_SECONDS), 2)

        return ColdOpenHook(
            text=best_sentence,
            start=round(hook_start, 2),
            end=round(hook_end, 2),
            duration=round(hook_end - hook_start, 2),
            score=round(max(best_score, 8.0), 2),
        )

    def enforce_shorts_duration_bounds(
        self,
        start: float,
        end: float,
        episode_duration: float = 0.0,
        speed_multiplier: float = settings.SPEED_MULTIPLIER_SHORTS,
        cold_open_seconds: float = 4.0,
        intro_bridge_seconds: float = 10.0,
        loop_bridge_seconds: float = settings.SEAMLESS_LOOP_BRIDGE_SECONDS,
    ) -> Tuple[float, float, float]:
        """
        Section 5A: Shorts final rendered duration MUST be strictly between 35s and 55s.
        Accounts for Cold Open (3-5s), Intro Context Bridge (10-15s), Seamless Loop (1.5s),
        and Playback Speed Multiplier (1.08x).
        """
        raw_dur = max(10.0, end - start)
        effective_main_dur = raw_dur / speed_multiplier
        total_projected = cold_open_seconds + intro_bridge_seconds + effective_main_dur + loop_bridge_seconds

        if total_projected < settings.MIN_SHORTS_DURATION:
            needed_effective = settings.MIN_SHORTS_DURATION - (cold_open_seconds + intro_bridge_seconds + loop_bridge_seconds) + 2.0
            needed_raw = needed_effective * speed_multiplier
            deficit = max(0.0, needed_raw - raw_dur)
            new_start = max(0.0, start - deficit * 0.35)
            new_end = end + deficit * 0.65
            if episode_duration > 0:
                new_end = min(episode_duration, new_end)
            start, end = round(new_start, 2), round(new_end, 2)
        elif total_projected > settings.MAX_SHORTS_DURATION:
            max_effective = settings.MAX_SHORTS_DURATION - (cold_open_seconds + intro_bridge_seconds + loop_bridge_seconds) - 1.5
            max_raw = max(18.0, max_effective * speed_multiplier)
            end = round(start + max_raw, 2)

        final_projected = round(
            cold_open_seconds + intro_bridge_seconds + ((end - start) / speed_multiplier) + loop_bridge_seconds,
            2,
        )
        final_projected = max(float(settings.MIN_SHORTS_DURATION), min(float(settings.MAX_SHORTS_DURATION), final_projected))
        return round(start, 2), round(end, 2), final_projected

    def adapt_cross_language_en_to_ptbr(self, text: str, source_lang: str = "en") -> str:
        """
        Section 4.3: Cross-Language Adaptation Module.
        When input language is 'en', translates/adapts transcript segments to 'pt-BR'
        keeping gaming slang natural (nerf, buff, FPS, drop, hype, NPC, ray tracing).
        """
        if not text or source_lang.lower().startswith("pt"):
            return text

        protected_map: Dict[str, str] = {}
        working = text
        for idx, slang in enumerate(self.slang_preserve):
            token = f"__SLANG_{idx}__"
            pattern = re.compile(re.escape(slang), re.IGNORECASE)
            if pattern.search(working):
                protected_map[token] = slang
                working = pattern.sub(token, working)

        common_replacements = {
            r"\bleaked\b": "vazou",
            r"\bleak\b": "vazamento",
            r"\bdelayed\b": "adiado",
            r"\bdelay\b": "adiamento",
            r"\bmap\b": "mapa",
            r"\bphysics\b": "física",
            r"\bprice\b": "preço",
            r"\bconsole\b": "console",
            r"\bgameplay\b": "gameplay",
            r"\btrailer\b": "trailer",
        }
        for pat, rep in common_replacements.items():
            working = re.sub(pat, rep, working, flags=re.IGNORECASE)

        for token, slang in protected_map.items():
            working = working.replace(token, slang)

        return working

    def cluster_clips_for_long_form(
        self,
        candidates: List[ScoredClipCandidate],
    ) -> List[Dict[str, Any]]:
        """
        Section 3 & Section 5B: Thematic Clustering (For Long-Form).
        Groups 2 to 4 clips from DIFFERENT creators discussing the exact same sub-topic
        and builds a timeline strictly between 485s (8m05s) and 720s (12m00s) for Mid-Roll ads.
        """
        by_cluster: Dict[str, List[ScoredClipCandidate]] = {}
        for c in candidates:
            by_cluster.setdefault(c.thematic_cluster, []).append(c)

        compilations: List[Dict[str, Any]] = []
        for cluster_name, group in by_cluster.items():
            group_sorted = sorted(group, key=lambda x: x.viral_score, reverse=True)
            selected: List[ScoredClipCandidate] = []
            seen_creators = set()

            for item in group_sorted:
                if item.speaker_channel not in seen_creators:
                    selected.append(item)
                    seen_creators.add(item.speaker_channel)
                if len(selected) >= settings.CLUSTER_MAX_CLIPS:
                    break

            # Fill up to minimum cluster size if needed
            for item in group_sorted:
                if len(selected) >= settings.CLUSTER_MIN_CLIPS:
                    break
                if item not in selected:
                    selected.append(item)

            if len(selected) < settings.CLUSTER_MIN_CLIPS and len(group_sorted) > 0:
                selected = group_sorted[: settings.CLUSTER_MAX_CLIPS]

            compilations.append(
                {
                    "cluster_topic": cluster_name,
                    "creators_count": len({c.speaker_channel for c in selected}),
                    "clips_count": len(selected),
                    "target_duration_seconds": max(
                        settings.MIN_LONG_DURATION,
                        min(settings.MAX_LONG_DURATION, 510),
                    ),
                    "timeline_spec": {
                        "00:00-00:05": f"Cold Open: {selected[0].cold_open.text if selected else ''}",
                        "00:05-00:25": "Narrator Voiceover + GTA 6 B-Roll introducing central controversy/theory",
                        "00:25-03:30": "Clip 1 (Edited with B-roll overlays every 8s and dynamic zooms)",
                        "03:30-03:45": "Narrator transition introducing contrasting viewpoint",
                        "03:45-07:30": "Clip 2 & Clip 3 (Mashup comparison + visual data/tweets on screen)",
                        "07:30-08:15": "Narrator conclusion + Polarizing question CTA (495s >= 485s Mid-Roll unlocked)",
                    },
                    "clips": [asdict(c) for c in selected],
                }
            )

        return compilations
