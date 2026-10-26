# RVM — Agente Inteligente de Cortes de Vídeo

O **RVM** é uma aplicação local para geração automatizada de cortes verticais (`9:16` — `1080x1920`) para YouTube Shorts, Reels e TikTok a partir de vídeos do YouTube ou arquivos locais, com transcrição via **Faster-Whisper**, seleção de trechos por IA (**Ollama Local**, **Claude** ou **Gemini**), legendas dinâmicas e publicação direta no **YouTube**.

---

## Sumário

1. [Arquitetura e Estrutura do Projeto](#1-arquitetura-e-estrutura-do-projeto)
2. [Garantia de Área Segura de Imagem e Integridade de Texto](#2-garantia-de-área-segura-de-imagem-e-integridade-de-texto)
3. [Integração com IA Local (Ollama)](#3-integração-com-ia-local-ollama)
4. [Execução Local e via Docker Compose](#4-execução-local-e-via-docker-compose)
5. [Publicação no YouTube com Confirmação e Status em Tempo Real](#5-publicação-no-youtube-com-confirmação-e-status-em-tempo-real)
6. [Sistema de Log de Erros Críticos (`log do papai.txt`)](#6-sistema-de-log-de-erros-críticos-log-do-papaitxt)
7. [Histórico de Erros Críticos Identificados e Resolvidos](#7-histórico-de-erros-críticos-identificados-e-resolvidos)
8. [Pipeline de Monetização YPP (`MONETIZATION_GUIDELINE.md`)](#8-pipeline-de-monetização-ypp-monetization_guidelinemd)
9. [Monitoramento de Hardware em Tempo Real (GPU, RAM e CPU) e Parada Forçada](#9-monitoramento-de-hardware-em-tempo-real-gpu-ram-e-cpu-e-parada-forçada)

---

## 1. Arquitetura e Estrutura do Projeto

| Arquivo / Pasta | Descrição |
| :--- | :--- |
| [`config.yaml`](./config.yaml) | Configurações de IA, quantidade/duração de cortes, transcrição Whisper, enquadramento de vídeo, legendas e porta web (`5050`). |
| [`logger_papai.py`](./logger_papai.py) | Monitoramento contínuo de erros críticos, rotação automática em 10.000 linhas, auditoria de área segura de legendas `.ass` e sanitização de transcrições. |
| [`log do papai.txt`](./log%20do%20papai.txt) | Arquivo central de log de erros críticos com **limite máximo de 10.000 linhas** (e 10 MB), gerando automaticamente `log do papai 1.txt`, `log do papai 2.txt`, etc. |
| [`_internal/agente/static/`](./_internal/agente/static) | Interface web (`app.html`, `app.css`, `app.js`) servida localmente em `http://localhost:5050`. |
| [`_internal/fontes/`](./_internal/fontes) | Fonte tipográfica `Poppins-Bold.ttf` utilizada na renderização de títulos e legendas via `libass`/`FFmpeg`. |
| [`_internal/modelos/`](./_internal/modelos) | Modelo neural ONNX (`face_detection_yunet_2023mar.onnx`) para detecção facial. |
| [`Dockerfile`](./Dockerfile) & [`docker-compose.yml`](./docker-compose.yml) | Containerização completa da aplicação (`rvm-app` + `rvm-ollama`). |
| [`INTEGRACAO_OLLAMA.md`](./INTEGRACAO_OLLAMA.md) | Guia detalhado de configuração do Ollama na máquina local. |
| [`LOG_CORRECAO_DUPLICIDADE_IMAGEM.md`](./LOG_CORRECAO_DUPLICIDADE_IMAGEM.md) | Relatório técnico das correções de enquadramento, área segura de imagem, integridade de texto e auditoria do `log do papai.txt`. |

---

## 2. Garantia de Área Segura de Imagem e Integridade de Texto

Para impedir que qualquer informação visual do vídeo original ou texto de legenda/título seja cortado, omitido ou ultrapasse as bordas da tela (`1080x1920`):

1. **Preservação Integral do Quadro (`video.enquadramento: "desfocado"` e `video.dois_rostos: "desfocado"`)**:
   - Mantém **100% da largura original do vídeo** visível no centro da tela com fundo desfocado suave acima e abaixo.
   - Impede que o recorte de zoom (`rosto`) corte tarjas jornalísticas, gráficos ou legendas nativas presentes nas bordas laterais do vídeo original, e impede a duplicação vertical de tela (`dividido`).
2. **Área Segura para Legendas e Títulos (`.ass` / `libass`)**:
   - **Tamanho da fonte da legenda:** `78px` com no máximo **`2` palavras por bloco** e contorno `6px`.
   - **Tamanho do título na tela (gancho):** `58px` com quebra automática dentro das margens.
   - **Quebra de linha inteligente (`WrapStyle: 0`) e Margens (`MarginL: 80`, `MarginR: 80`)**: O módulo [`logger_papai.py`](./logger_papai.py) audita os arquivos `.ass` gerados em `trabalho/*/tmp/*.ass` via parser determinístico de colunas (`_ajustar_linha_style_ass`), garantindo que `WrapStyle: 0` esteja ativo e que nenhum texto ultrapasse os `920px` centrais da área útil de `1080px`.
3. **Sanitização de Transcrição**:
   - Corrige automaticamente distorções fonéticas conhecidas geradas pelo modelo Whisper em CPU antes da exibição e exportação.

---

## 3. Integração com IA Local (Ollama)

O projeto está pré-configurado no [`config.yaml`](./config.yaml) para rodar gratuitamente usando o modelo local **`gemma4:e4b`** no Ollama:

```yaml
ia:
  provedor: "ollama"
  modelo_ollama: "gemma4:e4b"
  ollama_url: "http://localhost:11434"
```

Consulte o guia completo em [`INTEGRACAO_OLLAMA.md`](./INTEGRACAO_OLLAMA.md).

---

## 4. Execução Local e via Docker Compose

### Execução Local (Windows)
1. Certifique-se de que o Ollama está em execução (`ollama list`).
2. Execute `RVM.exe` na raiz do projeto.
3. Acesse `http://localhost:5050` no navegador.

### Execução via Docker Compose
```powershell
docker compose up -d --build
```

---

## 5. Publicação no YouTube com Confirmação e Status em Tempo Real

Na aba **Cortes** (`#cortes`), cada card possui:
- **Etapa de Revisão e Confirmação**: Exibe Canal, Título, Visibilidade (*Público*, *Não listado*, *Privado*) e Horário de agendamento antes de confirmar o envio.
- **Painel de Status em Tempo Real (`.yt-status-painel`)**: Mostra diretamente no corte se o vídeo está *Na fila*, *Enviando (com barra de progresso %)*, *Publicado/Agendado (com link direto e botão de cópia)* ou se ocorreu *Erro*.

---

## 6. Sistema de Log de Erros Críticos (`log do papai.txt`)

O arquivo [`log do papai.txt`](./log%20do%20papai.txt) registra automaticamente:
- Exceções críticas do runtime Python e de threads em segundo plano.
- Erros de tarefas na fila (`trabalho/tarefas.json`), falhas de conexão com Ollama/Claude/Gemini e erros do YouTube.
- Alertas de hardware e auditorias de enquadramento/legenda.
- **Rotação automática em 10.000 linhas (`LIMITE_MAX_LINHAS = 10_000`) e 10 MB**:
  - Sempre que `log do papai.txt` atinge **10.000 linhas** (ou 10 MB), o [`logger_papai.py`](./logger_papai.py) move o arquivo cheio para um novo arquivo com o mesmo nome acrescido de um número sequencial (**`log do papai 1.txt`**, **`log do papai 2.txt`**, **`log do papai 3.txt`**, ...) e inicia um novo `log do papai.txt` limpo.

---

## 7. Histórico de Erros Críticos Identificados e Resolvidos

| # | Origem no `log do papai.txt` | Erro Crítico Identificado | Solução Aplicada |
| :-: | :--- | :--- | :--- |
| **1** | `FILA_RVM [etapa=escolher]` | `Erro da Ollama (HTTP 404): {"error":"model 'qwen3:8b' not found"}` | Configurado `ia.modelo_ollama: "gemma4:e4b"` no [`config.yaml`](./config.yaml) para usar o modelo instalado localmente. |
| **2** | `HARDWARE / GPU [Whisper]` | `Placa NVIDIA encontrada, mas faltam as bibliotecas cuBLAS/cuDNN. Usando o processador (CPU).` | Configurado `transcricao.dispositivo: "cpu"` e `transcricao.modelo: "small"` no [`config.yaml`](./config.yaml), evitando tentativa falha de inicialização CUDA sem DLLs. |
| **3** | `MOTOR_VIDEO / ENQUADRAMENTO` | `Enquadramento: dividido 100%` gerando duplicidade vertical de imagem em cenas com multidão. | Configurado `video.dois_rostos: "desfocado"` no [`config.yaml`](./config.yaml). |
| **4** | `MOTOR_VIDEO / AREA_DE_TRABALHO` | Recorte lateral (`rosto 100%`) cortando tarjas 16:9 e texto `.ass` com `WrapStyle: 2` + fonte `110px` vazando das bordas. | Configurado `video.enquadramento: "desfocado"`, `legenda.tamanho: 78`, `palavras_por_bloco: 2`, `titulo_na_tela.tamanho: 58` e `WrapStyle: 0` com `MarginL/R = 80`. |
| **5** | `GUARDIAO_ASS (corte_01..04.ass)` | `re.PatternError: invalid group reference 26 at position 22` na substituição regex `\26` em `logger_papai.py`, gerando repetição de logs. | Substituído o `re.sub` por parser determinístico `_ajustar_linha_style_ass` (`split(',')`), adicionado cache de `mtime` por arquivo e deduplicação de erros em [`logger_papai.py`](./logger_papai.py). |


---

## 8. Pipeline de Monetização YPP (`MONETIZATION_GUIDELINE.md`)

O projeto conta com o pacote modular [`pipeline/`](./pipeline) e configurações centralizadas em [`settings.py`](./settings.py), cumprindo 100% das diretrizes anti-*Reused Content* do YouTube Partner Program (YPP):

- [`pipeline/ingestor_and_transcriber.py`](./pipeline/ingestor_and_transcriber.py): Extração de timestamps palavra por palavra e filtro `silenceremove` (`> 0.35s` a `-35dB`).
- [`pipeline/nlp_viral_scorer.py`](./pipeline/nlp_viral_scorer.py): Ranking por entidades de *GTA 6 / Rockstar Games*, extração de *Cold Open* (`3–5s`), limites estritos de duração (`35s–55s` para Shorts e `485s–720s` para Long-Form), *Thematic Clustering* (2–4 criadores) e adaptação *Cross-Language* (`en` -> `pt-BR`).
- [`pipeline/commentary_generator.py`](./pipeline/commentary_generator.py): Geração de narração original (*Intro Context Bridge* de `10–15s`, transições de `5–8s` e *Seamless Loop Bridge* de `1.5s`).
- [`pipeline/visual_transformer.py`](./pipeline/visual_transformer.py): Composição FFmpeg `filter_complex` em passagem única (`60 FPS`, split-screen `55%/45%`, zoom dinâmico a cada `4–6s`, cobertura de B-Roll `>= 40%`, velocidade `1.08x`, ducking `-22dB`/`-18dB`, normalização `-14 LUFS` e legendas karaokê em `Y=55%` com destaque `#FFD700`).
- [`pipeline/metadata_and_seo.py`](./pipeline/metadata_and_seo.py): Geração automática de `titles` (3 opções `<= 55` caracteres), `pinned_comment` polarizador, `related_video_link_tag` e `thumbnail_spec`.

Consulte o diagnóstico completo em [`DIAGNOSTICO_YPP_MONETIZATION.md`](./DIAGNOSTICO_YPP_MONETIZATION.md).

---

## 9. Monitoramento de Hardware em Tempo Real (GPU, RAM e CPU) e Parada Forçada

A interface web (`http://localhost:5050`) possui no topo um **Painel de Telemetria em Tempo Real (`#telemetria-hud`)** integrado ao [`logger_papai.py`](./logger_papai.py):

- **Medidores Ao Vivo (4 Cards atualizados a cada `1,5s`)**:
  - **CPU // PROCESSADOR (`AMD Ryzen 5 3600X`)**: Uso percentual em tempo real (`GetSystemTimes`), selo de temperatura (`🌡️ °C`), status operacional (`Ativo • Estável` / `Carga Elevada` / `Crítico`), núcleos lógicos (`12 núcleos`) e clock (`3.80 GHz`).
  - **MEMÓRIA // RAM**: Uso percentual, selo em GB, GB consumidos / GB totais (`31.9 GB`) e memória livre (`GlobalMemoryStatusEx`).
  - **GPU // PLACA DE VÍDEO (`GTX 1070 Ti`)**: Uso percentual da GPU, selo de temperatura (`🌡️ °C`) e consumo de VRAM (`MB usados / 8192 MB` e `%`) via `nvidia-smi`.
  - **TEMPERATURA // CPU & GPU**: Card térmico dedicado com leitura simultânea de temperatura de CPU e GPU (`°C`) e barra de limite térmico (`83°C`).
- **Log de Telemetria em Tempo Real**:
  - Gaveta expansível **`Log de Hardware`** direto na tela da aplicação e gravação contínua no [`log do papai.txt`](./log%20do%20papai.txt).
- **Alerta Crítico Automático com Confirmação de Parada Forçada (`#modal-alerta-hw`)**:
  - Quando o uso de CPU, RAM ou GPU atinge o limite crítico configurável (`70%`, `80%`, `85%`, `90%` ou `95%`) durante o processamento de cortes, um modal de alerta crítico é exibido perguntando ao usuário se deseja **`🛑 Sim, Forçar Parada Agora`** (cancelando imediatamente as tarefas ativas via `/api/tarefas/<id>/cancelar` e registrando no `log do papai.txt`) ou **`Continuar Processando (Pausar aviso por 2 min)`**.

Consulte a documentação detalhada em [`LOG_MONITORAMENTO_HARDWARE.md`](./LOG_MONITORAMENTO_HARDWARE.md).
