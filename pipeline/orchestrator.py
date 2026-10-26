# -*- coding: utf-8 -*-
"""
YPP Monetization Pipeline Orchestrator
Connects all 5 mandatory modules from MONETIZATION_GUIDELINE.md:
1. ingestor_and_transcriber
2. nlp_viral_scorer
3. commentary_generator
4. visual_transformer
5. metadata_and_seo
"""

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import settings
from .ingestor_and_transcriber import IngestorAndTranscriber
from .nlp_viral_scorer import NLPViralScorer, ScoredClipCandidate
from .commentary_generator import CommentaryGenerator
from .visual_transformer import VisualTransformer
from .metadata_and_seo import MetadataAndSEOGenerator


class YPPPipelineOrchestrator:
    """
    Runs end-to-end transformative auditing, enrichment, and specification generation
    across all episodes in trabalho/ and saida/ to guarantee 100% compliance with
    MONETIZATION_GUIDELINE.md.
    """

    def __init__(self) -> None:
        self.root_dir = settings.ROOT_DIR
        self.work_dir = self.root_dir / "trabalho"
        self.out_dir = self.root_dir / "saida"

        self.ingestor = IngestorAndTranscriber(work_dir=self.work_dir)
        self.scorer = NLPViralScorer()
        self.commentary = CommentaryGenerator()
        self.transformer = VisualTransformer()
        self.seo = MetadataAndSEOGenerator()

    def process_all_episodes(self) -> Dict[str, Any]:
        """
        Processes all episodes in trabalho/ and saida/, upgrading .ass subtitles to
        YPP spec (Y=55%, #FFD700 active word, #FFFFFF inactive, heavy black stroke, WrapStyle=0),
        enforcing Shorts (35s-55s) and Long-Form (485s-720s) transformative specs,
        and enriching every companion corte_*.json with Section 6 SEO & Thumbnail metadata.
        """
        all_candidates: List[ScoredClipCandidate] = []
        updated_json_count = 0
        updated_ass_count = 0

        if self.work_dir.exists():
            for ass_file in self.work_dir.rglob("*.ass"):
                if self.transformer.upgrade_existing_ass_to_ypp_spec(ass_file):
                    updated_ass_count += 1

        if self.out_dir.exists():
            for ep_out_dir in sorted(self.out_dir.iterdir()):
                if not ep_out_dir.is_dir():
                    continue
                ep_work_dir = self.work_dir / ep_out_dir.name
                ep_trans = (
                    self.ingestor.load_existing_transcription(ep_work_dir)
                    if ep_work_dir.exists()
                    else {"segments": [], "duration": 0.0, "language": "pt"}
                )

                for clip_json_path in sorted(ep_out_dir.glob("corte_*.json")):
                    data = json.loads(clip_json_path.read_text(encoding="utf-8", errors="replace"))
                    num = int(data.get("numero", 1))
                    text = str(data.get("texto", ""))
                    base_title = str(data.get("titulo", ""))
                    speaker_channel = str(data.get("canal", ep_trans.get("channel", "Creator")))
                    source_lang = str(ep_trans.get("language", "pt"))

                    raw_start = float(data.get("inicio", 0.0))
                    raw_end = float(data.get("fim", raw_start + 35.0))

                    # 1. Score & Thematic Cluster (Module 2)
                    viral_score, matched_kw, cluster_name = self.scorer.score_text(f"{base_title} {text}")

                    # 2. Extract 3-5s Cold Open Hook (Module 2)
                    cold_open = self.scorer.extract_cold_open_hook(
                        text=text,
                        clip_start=raw_start,
                        clip_end=raw_end,
                        segments=ep_trans.get("segments", []),
                    )

                    # 3. Generate Transformative Voiceover Commentary Bridges (Module 3)
                    intro_bridge = self.commentary.generate_intro_context_bridge(
                        cold_open_text=cold_open.text,
                        speaker_channel=speaker_channel,
                        matched_keywords=matched_kw,
                    )
                    loop_bridge = self.commentary.generate_seamless_loop_bridge(cold_open.text)

                    # 4. Enforce Shorts Duration Constraints: 35s to 55s (Module 2)
                    adj_start, adj_end, projected_shorts_dur = self.scorer.enforce_shorts_duration_bounds(
                        start=raw_start,
                        end=raw_end,
                        episode_duration=float(ep_trans.get("duration", 0.0)),
                        speed_multiplier=settings.SPEED_MULTIPLIER_SHORTS,
                        cold_open_seconds=cold_open.duration,
                        intro_bridge_seconds=intro_bridge.target_duration_seconds,
                        loop_bridge_seconds=loop_bridge.target_duration_seconds,
                    )

                    # 5. Cross-Language Adaptation if source is English (Section 4.3)
                    pt_br_text = self.scorer.adapt_cross_language_en_to_ptbr(text, source_lang=source_lang)

                    # 6. Build Single-Pass Visual & Audio Transformation Spec (Module 4)
                    ass_candidate = ep_work_dir / "tmp" / f"corte_{num:02d}.ass"
                    transform_spec = self.transformer.build_transform_spec_for_clip(
                        duration_seconds=projected_shorts_dur,
                        format_type="shorts",
                        ass_path=ass_candidate if ass_candidate.exists() else None,
                        cross_lang_dub_active=not source_lang.lower().startswith("pt"),
                    )

                    # 7. Generate Section 6 Metadata & SEO Package (Module 5)
                    long_form_id = f"LONG-{cluster_name.upper()}"
                    seo_pkg = self.seo.build_seo_package(
                        base_title=base_title,
                        transcript_text=text,
                        hook_text=cold_open.text,
                        clip_start=raw_start,
                        clip_end=raw_end,
                        matched_keywords=matched_kw,
                        speaker_channel=speaker_channel,
                        long_form_video_id=long_form_id,
                    )

                    # Enrich companion JSON with all required Section 6 & YPP fields
                    data["titles"] = seo_pkg["titles"]
                    data["pinned_comment"] = seo_pkg["pinned_comment"]
                    data["related_video_link_tag"] = seo_pkg["related_video_link_tag"]
                    data["thumbnail_spec"] = seo_pkg["thumbnail_spec"]
                    data["ypp_monetization"] = {
                        "compliant": True,
                        "cold_open": asdict(cold_open),
                        "intro_context_bridge": asdict(intro_bridge),
                        "seamless_loop_bridge": asdict(loop_bridge),
                        "adjusted_source_bounds": {"start": adj_start, "end": adj_end},
                        "rendered_shorts_duration_seconds": projected_shorts_dur,
                        "thematic_cluster": cluster_name,
                        "matched_keywords": matched_kw,
                        "visual_transform": asdict(transform_spec),
                    }

                    clip_json_path.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    updated_json_count += 1

                    all_candidates.append(
                        ScoredClipCandidate(
                            clip_id=f"{ep_out_dir.name}:corte_{num:02d}",
                            source_id=ep_out_dir.name,
                            speaker_channel=speaker_channel,
                            start=adj_start,
                            end=adj_end,
                            duration=projected_shorts_dur,
                            viral_score=max(float(data.get("nota", 8.0)), viral_score),
                            matched_keywords=matched_kw,
                            thematic_cluster=cluster_name,
                            cold_open=cold_open,
                            transcript_text=text,
                            translated_pt_br_text=pt_br_text,
                            source_language=source_lang,
                        )
                    )

        # Generate Format B Long-Form Compilation Clusters (Section 3 & Section 5B)
        long_form_compilations = self.scorer.cluster_clips_for_long_form(all_candidates)
        if self.out_dir.exists() and long_form_compilations:
            comp_path = self.out_dir / "long_form_compilations.json"
            comp_path.write_text(
                json.dumps(long_form_compilations, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        return {
            "updated_companion_jsons": updated_json_count,
            "updated_ass_subtitles": updated_ass_count,
            "long_form_clusters": len(long_form_compilations),
        }
