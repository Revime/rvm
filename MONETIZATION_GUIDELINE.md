# SYSTEM SPECIFICATION & BUSINESS RULES: AUTOMATED GAMING CLIP PIPELINE (YPP MONETIZATION FOCUS)

## 1. PROJECT OBJECTIVE & CORE CONSTRAINT
You are refactoring the `main` project of an automated video clipping and publishing bot focused on the **Gaming Niche (specifically GTA 6 / Rockstar Games hype)**.
* **Primary Goal:** Achieve and maintain YouTube Partner Program (YPP) monetization (1,000 subscribers + 4,000 valid public watch hours or 10M Shorts views).
* **Critical Constraint (Anti-Ban):** The pipeline MUST strictly avoid YouTube's **"Reused Content"** and **"Repetitive/Inauthentic Content"** policies. Raw cuts with simple subtitles are forbidden. Every output video must undergo automated transformative editing (commentary injection, multi-source mashup, dynamic B-roll, and visual pacing alterations).

---

## 2. PIPELINE ARCHITECTURE & MODULE REQUIREMENTS
Adapt the existing codebase to follow a modular pipeline with these mandatory processing stages:
1. `ingestor_and_transcriber`: Downloads sources and generates word-level timestamps (e.g., WhisperX / Faster-Whisper).
2. `nlp_viral_scorer`: Analyzes transcripts to extract high-retention segments, hooks, and thematic clusters.
3. `commentary_generator`: Generates original scripts and TTS voiceovers to contextualize clips (Fair Use compliance).
4. `visual_transformer`: Executes FFmpeg/MoviePy composition (dynamic zoom, B-roll overlays, split-screen, speed ramping).
5. `metadata_and_seo`: Generates CTR-optimized titles, descriptions, tags, and polarizing pinned comments.

---

## 3. CONTENT SELECTION & NLP SCORING RULES (`nlp_viral_scorer`)
When scanning source transcripts (podcasts, livestreams, foreign gaming analysis), the LLM/scorer must filter and rank segments based on these parameters:

* **High-Priority Keyword Entities:** `GTA 6`, `GTA VI`, `Rockstar Games`, `Vice City`, `Lucia`, `Jason`, `PS5 Pro`, `60 FPS`, `vazamento` (leak), `trailer`, `física` (physics), `NPC`, `mapa` (map), `adiamento` (delay), `preço` (price).
* **Hook Extraction (The 3-Second Rule):** Every video must start with a "Cold Open" — the single most controversial, shocking, or curiosity-inducing sentence from the clip (3 to 5 seconds long) BEFORE any context or intro plays.
* **Thematic Clustering (For Long-Form):** Group 2 to 4 clips from DIFFERENT creators discussing the exact same sub-topic (e.g., "GTA 6 running at 30 FPS on base consoles") to compile a single debate video.

---

## 4. TRANSFORMATIVE EDITING RULES (`visual_transformer` & `commentary_generator`)
To guarantee monetization approval, enforce the following hard-coded editing parameters in the rendering engine:

### 4.1. Mandatory Original Voiceover Injection (TTS/Audio)
* **Intro Context Bridge:** After the 3-5s Cold Open, insert a generated narrator voiceover (10 to 15 seconds) introducing the debate/news over gameplay B-roll before cutting to the streamer/podcast.
* **Inter-Clip Transitions (Long-Form):** Insert a 5 to 8-second narrator bridge between different clips summarizing the counterpoint.
* **Audio Ducking:** When the narrator TTS is active, duck background music and B-roll game audio to `-22dB`. Normalize main speech to `-14 LUFS`.

### 4.2. Visual Pacing & Anti-Static Frame Rules
* **Max Static Shot Duration:** Never display an unaltered talking-head frame for more than **8 consecutive seconds**.
* **Dynamic Keyframe Zoom:** Apply an automated slow zoom-in (`1.0x` to `1.12x`) or instant punch-in (`1.15x`) every `4 to 6 seconds` synced with sentence boundaries or vocal emphasis.
* **B-Roll Overlay Trigger:** Cover at least **40% of the total video duration** with gaming B-roll (GTA 6 trailers, GTA V graphic mods gameplay, map concepts) while keeping the original speaker's audio running underneath.
* **Playback Speed Alteration:**
  * For Shorts: Apply a `1.05x` to `1.10x` speed multiplier to eliminate dead air.
  * Silence Trimming: Automatically cut any audio silence exceeding `0.35 seconds` (`silenceremove` filter).

### 4.3. Cross-Language Adaptation Module (Optional/High-Value Flag)
* When the input source language is `en` (English), translate transcript segments to `pt-BR` keeping gaming slang natural (e.g., retain terms like *nerf, buff, FPS, drop, hype, NPC, ray tracing*).
* Render dynamic burned-in Portuguese captions OR dub with voice-cloned/synthesized PT-BR audio while ducking original English audio to `-18dB`.

---

## 5. OUTPUT FORMAT SPECIFICATIONS

### Format A: YouTube Shorts (Subscriber Acquisition Engine)
* **Resolution & Aspect Ratio:** `1080x1920` (9:16), `60 FPS`.
* **Duration Constraints:** Strictly between `35s` and `55s`.
* **Layout Structure:**
  * Top `55%` of screen: Speaker/Podcast feed (face-tracked crop) OR full-screen B-roll during key descriptive moments.
  * Bottom `45%` of screen: High-retention gameplay (GTA V stunt races, graphical mod showcases, or GTA 6 trailer frame analysis).
* **Subtitles (ASS/SRT):** Centered at `Y-axis: 55%` (junction of split screen), word-by-word highlight (karaoke style), bold sans-serif font (e.g., Montserrat ExtraBold), yellow (`#FFD700`) and white (`#FFFFFF`) active word emphasis with heavy black stroke.
* **Seamless Loop Ending:** Trim the end of the clip right after a punchline and append a 1.5s bridge that grammatically connects back to the 0:00 Cold Open sentence.

### Format B: Long-Form Compilation/Analysis (4,000 Watch-Hours & Mid-Roll Ad Engine)
* **Resolution & Aspect Ratio:** `1920x1080` (16:9), `60 FPS`.
* **Duration Constraints:** Strictly `>= 485 seconds` (8 minutes and 5 seconds) and `<= 720 seconds` (12 minutes) to unlock YouTube Mid-Roll ad slots.
* **Timeline Structure:**
  1. `00:00 - 00:05`: Explosive Cold Open quote from Clip 1.
  2. `00:05 - 00:25`: Narrator Voiceover + B-Roll introducing the central controversy/theory.
  3. `00:25 - 03:30`: Clip 1 (Edited with B-roll overlays every 8s and dynamic zooms).
  4. `03:30 - 03:45`: Narrator transition introducing a contrasting viewpoint.
  5. `03:45 - 07:30`: Clip 2 & Clip 3 (Mashup comparison + visual data/tweets on screen).
  6. `07:30 - 08:15+`: Narrator conclusion + Polarizing question CTA to drive comment section debate.

---

## 6. AUTOMATED METADATA & ENGAGEMENT GENERATION (`metadata_and_seo`)
For every rendered video, output a companion `.json` file containing:
1. **`titles` (Array of 3 options):** Max 55 characters, curiosity gap structure, 1-2 capitalized power words. (e.g., *"O PROBLEMA SECRETO do Mapa de GTA 6 que Ninguém Viu..."*).
2. **`pinned_comment` (String):** A polarizing question directly tied to the transcript designed to trigger replies (e.g., *"Vocês acham que o PS5 base vai aguentar o GTA 6 a 60 FPS ou só no PC? Comenta aí!"*).
3. **`related_video_link_tag`:** Metadata flag linking every generated Short to the latest Long-Form video ID.
4. **`thumbnail_spec` (JSON):**
   * `background_frame_timestamp`: Timestamp of highest visual contrast in B-roll.
   * `subject_face_emotion`: Shocked / Skeptical / Laughing.
   * `overlay_text`: Max 3 words (e.g., `"60 FPS IMPOSSÍVEL?"`, `"VAZOU TUDO!"`).
   * `visual_cue`: Red arrow or circle coordinates pointing to background detail.

---

## 7. IMPLEMENTATION DIRECTIVES FOR THE AI CODER
1. **Audit `main` first:** Map existing functions against Sections 3, 4, and 5. Identify where raw cuts are currently being exported without transformation.
2. **Externalize Constants:** Move all timing thresholds (`MAX_STATIC_SECONDS = 8`, `MIN_LONG_DURATION = 485`, `SILENCE_THRESHOLD_DB = -35`, `SPEED_MULTIPLIER_SHORTS = 1.08`) into a centralized `config.yaml` or `settings.py` file.
3. **FFmpeg Filter Complex:** Optimize video rendering using single-pass `filter_complex` graphs where possible to avoid intermediate disk I/O bottlenecks when combining B-roll, face-crop, audio ducking, and `.ass` subtitle burn-in.