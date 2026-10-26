# Diagnóstico Completo e Arquitetura YPP — `MONETIZATION_GUIDELINE.md`

**Data:** 26/10/2026  
**Escopo:** Auditoria completa da branch `main` contra 100% das regras de transformação visual, áudio, duração e metadados SEO de [`MONETIZATION_GUIDELINE.md`](./MONETIZATION_GUIDELINE.md).

---

## 1. Diagnóstico do Código anterior na Branch `main`

| Requisito (`MONETIZATION_GUIDELINE.md`) | Estado Anterior em `main` | Diagnóstico / Gap Identificado | Status Atual |
| :--- | :--- | :--- | :---: |
| **Seção 2 — Arquitetura Modular em 5 Estágios** | Monolítico (cortes simples sem módulos dedicados) | Faltavam os 5 módulos independentes (`ingestor_and_transcriber`, `nlp_viral_scorer`, `commentary_generator`, `visual_transformer`, `metadata_and_seo`). | **100% Implementado** |
| **Seção 3 — Entidades Gaming/GTA 6, Cold Open (3–5s) e Clustering Temático** | Sem filtro de entidades GTA 6, sem Cold Open antes de intro e sem agrupamento multi-criador | Faltava extração automática da frase mais polêmica (3–5s) para *Cold Open* e agrupamento de 2 a 4 clipes por subtópico para vídeos Long-Form. | **100% Implementado** |
| **Seção 4.1 — Injeção de Narração Original (TTS) e Audio Ducking** | Apenas áudio original sem ponte narrativa nem normalização LUFS | Faltavam *Intro Context Bridge* (10–15s), *Inter-Clip Transitions* (5–8s), *Audio Ducking* a `-22dB` e normalização de voz em `-14 LUFS`. | **100% Implementado** |
| **Seção 4.2 — Ritmo Visual, Anti-Estático (<= 8s), B-Roll (>= 40%), Speed (1.08x) e Silence Trim (> 0.35s)** | Quadro estático contínuo, `fps_max: 30`, sem corte de silêncio (`silenceremove`) e sem velocidade `1.05x–1.10x` | Exigia zoom dinâmico (`1.0x -> 1.12x` / punch-in `1.15x`) a cada 4–6s, janelas de B-Roll cobrindo `>= 40%`, `setpts`/`atempo` em `1.08x` e `silenceremove` para silêncios `> 0.35s` (`-35dB`). | **100% Implementado** |
| **Seção 4.3 — Adaptação Cross-Language (`en` -> `pt-BR`)** | Sem proteção de gírias gamer na tradução e sem ducking `-18dB` | Exigia preservação de termos gamer (*nerf, buff, FPS, drop, hype, NPC, ray tracing*) e ducking em `-18dB`. | **100% Implementado** |
| **Seção 5A — Formato A: YouTube Shorts (`1080x1920`, `60 FPS`, `35s–55s`)** | `duracao_min: 25`, `duracao_max: 120`, `30 FPS`, sem Loop Bridge de `1.5s` | Ajustado para `35s–55s`, `60 FPS`, layout `55%` topo / `45%` gameplay base, legenda karaokê no eixo `Y=55%` (`1056px`) com amarelo `#FFD700` e branco `#FFFFFF`, e *Seamless Loop Ending* (`1.5s`). | **100% Implementado** |
| **Seção 5B — Formato B: Compilação Long-Form (`1920x1080`, `60 FPS`, `485s–720s`)** | Inexistente | Criado motor de compilação Long-Form (`>= 485s` e `<= 720s`) com estrutura de linha do tempo em 6 blocos para habilitar anúncios *Mid-Roll*. | **100% Implementado** |
| **Seção 6 — Metadados Automatizados e SEO (`.json`)** | `corte_*.json` tinha apenas `titulo`, `descricao` e `hashtags` simples | Adicionados `titles` (3 opções `<= 55` caracteres com *Curiosity Gap*), `pinned_comment` polarizador, `related_video_link_tag` e `thumbnail_spec` completo. | **100% Implementado** |
| **Seção 7 — Constantes Externalizadas e `filter_complex` Single-Pass** | Parâmetros espalhados sem constantes YPP | Criado [`settings.py`](./settings.py) e seção `monetizacao_ypp` em [`config.yaml`](./config.yaml) + grafo `filter_complex` de passagem única. | **100% Implementado** |

---

## 2. Módulos Criados e Refatorados

1. **[`settings.py`](./settings.py) e [`config.yaml`](./config.yaml)**:
   - Centraliza todas as constantes da Seção 7 (`MAX_STATIC_SECONDS = 8.0`, `MIN_LONG_DURATION = 485`, `MAX_LONG_DURATION = 720`, `MIN_SHORTS_DURATION = 35`, `MAX_SHORTS_DURATION = 55`, `SILENCE_THRESHOLD_DB = -35`, `SILENCE_MIN_DURATION = 0.35`, `SPEED_MULTIPLIER_SHORTS = 1.08`, `BROLL_MIN_COVERAGE_RATIO = 0.40`, `DUCKING_BG_DB = -22`, `DUCKING_EN_DUB_DB = -18`, `TARGET_LUFS = -14`, `SHORTS_FPS = 60`, `LONG_FPS = 60`).
2. **[`pipeline/ingestor_and_transcriber.py`](./pipeline/ingestor_and_transcriber.py)**:
   - Ingestão de fontes, extração de timestamps palavra por palavra (*word-level timestamps*) via Faster-Whisper com filtro VAD e geração do filtro FFmpeg `silenceremove` (`> 0.35s` abaixo de `-35dB`).
3. **[`pipeline/nlp_viral_scorer.py`](./pipeline/nlp_viral_scorer.py)**:
   - Pontuação viral baseada nas entidades prioritárias de GTA 6 / Rockstar Games.
   - Extração do *Cold Open Hook* (regra dos 3 segundos: `3.0s` a `5.0s`).
   - Enquadramento estrito de duração para Shorts (`35s` a `55s`) e agrupamento temático (*Thematic Clustering* de 2 a 4 criadores) para Long-Form (`485s` a `720s`).
   - Adaptação Cross-Language (`en` -> `pt-BR`) preservando gírias gamer (*nerf, buff, FPS, drop, hype, NPC, ray tracing*).
4. **[`pipeline/commentary_generator.py`](./pipeline/commentary_generator.py)**:
   - Geração de roteiros originais e síntese de voz TTS para:
     - *Intro Context Bridge* (`10s` a `15s` após o Cold Open)
     - *Inter-Clip Transitions* (`5s` a `8s` entre clipes no Long-Form)
     - *Seamless Loop Bridge* (`1.5s` no final do Short conectando de volta ao Cold Open `0:00`)
     - *Long-Form Conclusion + Polarizing CTA* (`45s` finais)
5. **[`pipeline/visual_transformer.py`](./pipeline/visual_transformer.py)**:
   - Construtor de grafo `filter_complex` de passagem única para FFmpeg:
     - Zoom dinâmico a cada `5s` (`1.0x -> 1.12x` slow zoom alternado com `1.15x` punch-in), garantindo `MAX_STATIC_SECONDS <= 8s`.
     - Sobreposição de B-Roll cobrindo `>= 40%` da duração total do vídeo.
     - Alteração de velocidade (`1.08x` para Shorts) + remoção de silêncio (`silenceremove`) + *Audio Ducking* (`-22dB` / `-18dB`) + normalização `-14 LUFS` (`loudnorm`).
     - Atualizador de legendas `.ass` posicionadas em `Y=55%` (`1056px`), cor ativa amarelo ouro `#FFD700` (`&H0000D7FF`), cor inativa branca `#FFFFFF` e contorno preto pesado (`Outline=8`).
6. **[`pipeline/metadata_and_seo.py`](./pipeline/metadata_and_seo.py)**:
   - Gera os 4 artefatos obrigatórios da Seção 6 em cada `.json` de saída:
     - `titles` (3 opções com `<= 55` caracteres, *Curiosity Gap* e palavras de poder em maiúsculas)
     - `pinned_comment` (pergunta polarizadora ligada à transcrição)
     - `related_video_link_tag` (vínculo entre o Short e o vídeo Long-Form)
     - `thumbnail_spec` (`background_frame_timestamp`, `subject_face_emotion`, `overlay_text` de no máximo 3 palavras e `visual_cue` com coordenadas de seta/círculo vermelho)
7. **[`pipeline/orchestrator.py`](./pipeline/orchestrator.py)**:
   - Orquestra os 5 módulos sobre os episódios em `trabalho/` e `saida/` e gera também `saida/long_form_compilations.json`.
