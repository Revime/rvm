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

---

## 1. Arquitetura e Estrutura do Projeto

| Arquivo / Pasta | Descrição |
| :--- | :--- |
| [`config.yaml`](./config.yaml) | Configurações de IA, quantidade/duração de cortes, transcrição Whisper, enquadramento de vídeo, legendas e porta web (`5050`). |
| [`logger_papai.py`](./logger_papai.py) | Monitoramento contínuo de erros críticos, auditoria de área segura de legendas `.ass` e sanitização de transcrições. |
| [`log do papai.txt`](./log%20do%20papai.txt) | Arquivo central de log de erros críticos e auditoria com **limite máximo estrito de 10 MB** (rotação automática). |
| [`_internal/agente/static/`](./_internal/agente/static) | Interface web (`app.html`, `app.css`, `app.js`) servida localmente em `http://localhost:5050`. |
| [`_internal/fontes/`](./_internal/fontes) | Fonte tipográfica `Poppins-Bold.ttf` utilizada na renderização de títulos e legendas via `libass`/`FFmpeg`. |
| [`_internal/modelos/`](./_internal/modelos) | Modelo neural ONNX (`face_detection_yunet_2023mar.onnx`) para detecção facial. |
| [`Dockerfile`](./Dockerfile) & [`docker-compose.yml`](./docker-compose.yml) | Containerização completa da aplicação (`rvm-app` + `rvm-ollama`). |
| [`INTEGRACAO_OLLAMA.md`](./INTEGRACAO_OLLAMA.md) | Guia detalhado de configuração do Ollama na máquina local. |
| [`LOG_CORRECAO_DUPLICIDADE_IMAGEM.md`](./LOG_CORRECAO_DUPLICIDADE_IMAGEM.md) | Relatório técnico das correções de enquadramento, área segura de imagem e integridade de texto. |

---

## 2. Garantia de Área Segura de Imagem e Integridade de Texto

Para impedir que qualquer informação visual do vídeo original ou texto de legenda/título seja cortado, omitido ou ultrapasse as bordas da tela (`1080x1920`):

1. **Preservação Integral do Quadro (`video.enquadramento: "desfocado"` e `video.dois_rostos: "desfocado"`)**:
   - Mantém **100% da largura original do vídeo** visível no centro da tela com fundo desfocado suave acima e abaixo.
   - Impede que o recorte de zoom (`rosto`) corte tarjas jornalísticas, gráficos ou legendas nativas presentes nas bordas laterais do vídeo original, e impede a duplicação vertical de tela (`dividido`).
2. **Área Segura para Legendas e Títulos (`.ass` / `libass`)**:
   - **Tamanho da fonte da legenda:** `78px` com no máximo **`2` palavras por bloco** e contorno `6px`.
   - **Tamanho do título na tela (gancho):** `58px` com quebra automática dentro das margens.
   - **Quebra de linha inteligente (`WrapStyle: 0`) e Margens (`MarginL: 80`, `MarginR: 80`)**: O módulo [`logger_papai.py`](./logger_papai.py) audita automaticamente os arquivos `.ass` gerados em `trabalho/*/tmp/*.ass` garantindo que `WrapStyle: 0` esteja ativo e que nenhum texto ultrapasse os `920px` centrais da área útil de `1080px`.
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
- Alertas de hardware (como ausência de bibliotecas CUDA/cuBLAS) e auditorias de enquadramento/legenda.
- **Controle de tamanho de 10 MB (`10.485.760 bytes`)**: Gerenciado por [`logger_papai.py`](./logger_papai.py), reciclando os registros mais antigos sempre que o arquivo se aproxima de 10 MB.
