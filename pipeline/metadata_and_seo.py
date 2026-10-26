# -*- coding: utf-8 -*-
"""
Module 5: metadata_and_seo
Implements Section 6 of MONETIZATION_GUIDELINE.md:
For every rendered video, outputs/enriches the companion .json file containing:
1. titles (Array of 3 options): Max 55 characters, curiosity gap structure, 1-2 capitalized power words.
2. pinned_comment (String): Polarizing question directly tied to the transcript designed to trigger replies.
3. related_video_link_tag: Metadata flag linking every generated Short to the latest Long-Form video ID.
4. thumbnail_spec (JSON):
   - background_frame_timestamp
   - subject_face_emotion ("Shocked" | "Skeptical" | "Laughing")
   - overlay_text (Max 3 words, e.g. "60 FPS IMPOSSÍVEL?", "VAZOU TUDO!")
   - visual_cue (Red arrow or circle coordinates pointing to background detail)
"""

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import settings


@dataclass
class ThumbnailSpec:
    background_frame_timestamp: float
    subject_face_emotion: str  # "Shocked" | "Skeptical" | "Laughing"
    overlay_text: str          # Max 3 words
    visual_cue: Dict[str, Any]


@dataclass
class SEOMetadataPackage:
    titles: List[str]
    pinned_comment: str
    related_video_link_tag: str
    thumbnail_spec: ThumbnailSpec
    creator_credit_directive: Dict[str, Any]


class MetadataAndSEOGenerator:
    """
    Generates CTR-optimized titles (<= 55 chars), polarizing pinned comments,
    related Long-Form link tags, and thumbnail specifications.
    """

    def __init__(self, default_long_form_id: str = "RVM-GTA6-LONG-001") -> None:
        self.default_long_form_id = default_long_form_id

    @staticmethod
    def _enforce_max_55_chars(title: str) -> str:
        """Strictly enforces Section 6.1: Max 55 characters per title."""
        clean = re.sub(r"\s+", " ", title.strip())
        if len(clean) <= settings.MAX_TITLE_CHARS:
            return clean
        truncated = clean[: settings.MAX_TITLE_CHARS - 3].rstrip(" ,;:-")
        return f"{truncated}..."

    def generate_three_titles(
        self,
        base_title: str,
        matched_keywords: List[str],
        speaker_channel: str = "",
    ) -> List[str]:
        """
        Section 6.1:
        Array of 3 options, max 55 characters each, curiosity gap structure,
        with 1-2 capitalized power words.
        """
        primary_entity = matched_keywords[0] if matched_keywords else "GTA 6"
        core = re.sub(r"[\"'!?:]+", "", base_title or primary_entity).strip()
        short_core = core[:24].strip() if len(core) > 24 else core

        raw_options = [
            f"O SEGREDO de {short_core} que Ninguém Viu...",
            f"A VERDADE sobre {primary_entity}: Isso Muda Tudo!",
            f"ERRO GRAVE em {short_core}? Veja o Motivo...",
        ]
        return [self._enforce_max_55_chars(opt) for opt in raw_options]

    def generate_polarizing_pinned_comment(
        self,
        transcript_text: str,
        matched_keywords: List[str],
    ) -> str:
        """
        Section 6.2:
        A polarizing question directly tied to the transcript designed to trigger replies.
        """
        kw = matched_keywords[0] if matched_keywords else "GTA 6"
        lower = (transcript_text or "").lower()
        if "fps" in lower or "ps5" in lower or "console" in lower:
            return (
                f"Vocês acham que o PS5 base vai aguentar o {kw} a 60 FPS "
                "ou isso só vai ser possível no PC? Comenta aí!"
            )
        if "anula" in lower or "stf" in lower or "elei" in lower or "ministro" in lower:
            return (
                "Na sua opinião, esse argumento realmente tem base para mudar o resultado "
                "ou é apenas pressão política? Deixe sua opinião nos comentários!"
            )
        return (
            f"Vocês concordam com essa análise sobre {kw} ou acham que a comunidade "
            "está exagerando no hype? Comenta aí embaixo!"
        )

    def generate_thumbnail_spec(
        self,
        clip_start: float,
        clip_end: float,
        hook_text: str,
        matched_keywords: List[str],
    ) -> ThumbnailSpec:
        """
        Section 6.4:
        - background_frame_timestamp: Timestamp of highest visual contrast in B-roll
        - subject_face_emotion: Shocked / Skeptical / Laughing
        - overlay_text: Max 3 words (e.g., '60 FPS IMPOSSÍVEL?', 'VAZOU TUDO!')
        - visual_cue: Red arrow or circle coordinates pointing to background detail
        """
        duration = max(1.0, clip_end - clip_start)
        contrast_ts = round(clip_start + (duration * 0.38), 2)

        lower = (hook_text or "").lower()
        if "?" in (hook_text or "") or "dúvida" in lower or "será" in lower:
            emotion = "Skeptical"
        elif "haha" in lower or "piada" in lower or "rir" in lower:
            emotion = "Laughing"
        else:
            emotion = "Shocked"

        # Max 3 words for overlay_text
        if matched_keywords and "60 FPS" in matched_keywords:
            overlay = "60 FPS IMPOSSÍVEL?"
        elif "impossível" in lower or "anulad" in lower:
            overlay = "ISSO É IMPOSSÍVEL!"
        elif "inaceitável" in lower:
            overlay = "DECISÃO INACEITÁVEL!"
        else:
            words = re.sub(r"[^\w\s!?]", "", (hook_text or "VAZOU TUDO!")).upper().split()
            overlay = " ".join(words[: settings.MAX_THUMBNAIL_OVERLAY_WORDS]) or "VAZOU TUDO!"

        return ThumbnailSpec(
            background_frame_timestamp=contrast_ts,
            subject_face_emotion=emotion,
            overlay_text=overlay,
            visual_cue={
                "type": "red_arrow_and_circle",
                "color_hex": "#FF0033",
                "arrow_from_xy": [220, 340],
                "arrow_to_xy": [640, 480],
                "circle_center_xy": [660, 490],
                "circle_radius_px": 115,
            },
        )

    def build_seo_package(
        self,
        base_title: str,
        transcript_text: str,
        hook_text: str,
        clip_start: float,
        clip_end: float,
        matched_keywords: List[str],
        speaker_channel: str = "",
        long_form_video_id: Optional[str] = None,
        original_video_url: str = "",
    ) -> Dict[str, Any]:
        """Builds the full Section 6 metadata dictionary ready to write to the companion .json."""
        canal_nome = (speaker_channel or "Criador Original").strip()
        credito_tela = settings.CREATOR_CREDIT_SCREEN_TEMPLATE.format(canal=canal_nome)
        credito_descricao = settings.CREATOR_CREDIT_DESCRIPTION_TEMPLATE.format(
            canal=canal_nome,
            link=original_video_url or "https://youtube.com",
        )
        pkg = SEOMetadataPackage(
            titles=self.generate_three_titles(base_title, matched_keywords, canal_nome),
            pinned_comment=self.generate_polarizing_pinned_comment(transcript_text, matched_keywords),
            related_video_link_tag=long_form_video_id or self.default_long_form_id,
            thumbnail_spec=self.generate_thumbnail_spec(clip_start, clip_end, hook_text, matched_keywords),
            creator_credit_directive={
                "mandatory": settings.MANDATORY_CREATOR_CREDIT_DIRECTIVE,
                "directive_note": settings.CREATOR_CREDIT_DIRECTIVE_NOTE,
                "original_channel": canal_nome,
                "original_video_url": original_video_url,
                "on_screen_credit": credito_tela,
                "description_credit": credito_descricao,
            },
        )
        return asdict(pkg)

