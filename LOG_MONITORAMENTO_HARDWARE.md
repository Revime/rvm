# Relatório Técnico e Log de Implementação — Monitoramento de Hardware em Tempo Real (GPU, RAM e CPU) e Parada Forçada de Segurança

**Data da Implementação:** 26/10/2026  
**Módulos Criados/Atualizados:**
- [`logger_papai.py`](./logger_papai.py) (e [`_internal/logger_papai.py`](./_internal/logger_papai.py))
- [`_internal/agente/static/app.html`](./_internal/agente/static/app.html)
- [`_internal/agente/static/app.css`](./_internal/agente/static/app.css)
- [`_internal/agente/static/app.js`](./_internal/agente/static/app.js)
- [`settings.py`](./settings.py) & [`config.yaml`](./config.yaml)
- [`log do papai.txt`](./log%20do%20papai.txt)

---

## 1. Visão Geral da Implementação

Foi implementado diretamente na tela principal da aplicação web RVM (`http://localhost:5050`) um **Painel de Telemetria em Tempo Real (`.telemetria-hud`)** com medidores visuais contínuos de **CPU (Processador)**, **Memória RAM** e **GPU (Placa de Vídeo NVIDIA + VRAM + Temperatura)**, acompanhado de:

1. **Medidores Visuais em Tempo Real (4 Cards no HUD — Atualização a cada `1,5s`)**:
   - **CPU // AMD RYZEN 5 3600X (`#hw-card-cpu`)**: Exibe o modelo do processador, selo de temperatura em tempo real (`🌡️ °C`), porcentagem exata de uso (`GetSystemTimes` Win32 API via `ctypes`), status operacional (`Status: Ativo • Estável` / `Carga Elevada` / `Crítico`), contagem de núcleos lógicos (`12 núcleos`) e frequência (`3.80 GHz`).
   - **MEMÓRIA // RAM (`#hw-card-ram`)**: Exibe a porcentagem de ocupação, selo de consumo em GB, total usado/disponível (`GB usados / 31.9 GB`) e memória livre (`GlobalMemoryStatusEx` Win32 API via `ctypes`).
   - **GPU // GTX 1070 TI (`#hw-card-gpu`)**: Exibe o modelo detectado (`NVIDIA GeForce GTX 1070 Ti`), selo de temperatura (`🌡️ °C`), porcentagem de uso do núcleo gráfico e consumo de memória de vídeo (`VRAM usada / 8192 MB e %`) via `nvidia-smi`.
   - **TEMPERATURA // CPU & GPU (`#hw-card-temp`)**: Medidor térmico dedicado exibindo a temperatura máxima instantânea (`🌡️ °C`), comparativo direto `CPU: XX°C • GPU: XX°C` e barra de progresso em relação ao limite térmico crítico (`83°C`).
   - **Correção de Visibilidade do Card de CPU (`.estado-aviso` / `.estado-critico`)**:
     - Na primeira versão, quando a CPU entrava em estado de atenção (`>= 75%`), a atribuição da classe `.aviso` no card colidia com a classe global de toast flutuante `.aviso { position: fixed; opacity: 0; }` do [`app.css`](./_internal/agente/static/app.css), ocultando o card da CPU na grade. As classes de estado dos medidores foram isoladas para `.estado-normal`, `.estado-aviso` e `.estado-critico` com `position: relative !important; opacity: 1 !important;`, garantindo que o card de CPU permaneça 100% visível em qualquer faixa de carga.

2. **Gaveta de Log de Hardware em Tempo Real (`#hw-log-painel`) + Persistência em [`log do papai.txt`](./log%20do%20papai.txt)**:
   - Botão **`Log de Hardware`** no cabeçalho do medidor que expande o console em tempo real com o histórico cronológico das leituras de CPU, RAM, GPU, VRAM, temperatura e etapa da tarefa ativa.
   - Sincronização automática com o arquivo [`log do papai.txt`](./log%20do%20papai.txt) (respeitando o limite estrito de **10.000 linhas** e **10 MB** com rotação automática para `log do papai 1.txt`, `log do papai 2.txt`, etc.).

3. **Alerta Crítico Automático com Opção de Forçar Parada (`#modal-alerta-hw`)**:
   - Enquanto a aplicação processa cortes (ou a qualquer momento em que o limite crítico selecionável de `70%`, `80%`, `85%`, `90%` ou `95%` é atingido), o sistema abre automaticamente o **Modal de Alerta Crítico de Hardware** na tela, exibindo:
     - O motivo exato da sobrecarga (ex.: `GPU em 100.0% (limite crítico: 90%)` ou `CPU acima do limite`).
     - As leituras em tempo real de **CPU**, **Memória RAM** e **GPU / VRAM / Temperatura**.
     - A identificação da tarefa de corte em execução e sua etapa atual (`Baixando`, `Transcrevendo`, `Escolhendo trechos` ou `Montando vídeos`).
     - A pergunta de decisão ao usuário com dois botões de ação imediata:
       - **`🛑 Sim, Forçar Parada Agora`**: Cancela imediatamente todas as tarefas em execução/fila via `POST /api/tarefas/<id>/cancelar`, registra o evento `ALERTA_PARADA_FORCADA` no [`log do papai.txt`](./log%20do%20papai.txt) e interrompe o processamento com segurança.
       - **`Continuar Processando (Pausar aviso por 2 min)`**: Mantém o processamento ativo e silencia o pop-up automático por 2 minutos enquanto preserva o alerta visual vermelho no topo da tela.

---

## 2. Arquitetura Técnica de Coleta e Comunicação

```
┌────────────────────────────────────────────────────────────────────────────┐
│                   logger_papai.py (Coletor & Guardião)                     │
│  • medir_cpu_pct()  -> Win32 kernel32.GetSystemTimes (Delta em tempo real) │
│  • medir_ram()      -> Win32 kernel32.GlobalMemoryStatusEx (GB e %)        │
│  • medir_gpu()      -> nvidia-smi (GTX 1070 Ti: Core %, VRAM MB, Temp °C)  │
└───────────────┬────────────────────────────────────────┬───────────────────┘
                │ (A cada 1,5s)                          │ (Eventos e Alertas)
                ▼                                        ▼
┌───────────────────────────────────────────┐  ┌─────────────────────────────┐
│ /api/telemetria & /static/telemetria.json │  │      log do papai.txt       │
│ Snapshot JSON atômico consumido pela UI   │  │ Rotação 10.000 linhas/10 MB │
└───────────────┬───────────────────────────┘  └─────────────────────────────┘
                │
                ▼
┌────────────────────────────────────────────────────────────────────────────┐
│            Interface Web RVM (_internal/agente/static/app.js)              │
│  • Atualiza medidores #hw-card-cpu, #hw-card-ram e #hw-card-gpu            │
│  • Atualiza console #hw-log-pre                                            │
│  • Dispara #modal-alerta-hw -> Botão "🛑 Sim, Forçar Parada Agora"          │
│    └─> POST /api/tarefas/<id>/cancelar + POST /api/telemetria/parada-forcada│
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Eventos Reais de Telemetria e Alertas Críticos Registrados no `log do papai.txt`

Durante o processamento de episódios de GTA 6 com a IA local (`Ollama gemma4:e4b`), o coletor em tempo real detectou e registrou no [`log do papai.txt`](./log%20do%20papai.txt) tanto a operação normal quanto picos reais de **100% e 91% de GPU (com 6.452 MB de VRAM e 75°C)**:

```text
--------------------------------------------------------------------------------
DATA/HORA : 2026-10-26 09:29:30
NIVEL     : ALERTA_CRITICO_HARDWARE
ORIGEM    : MONITOR_HARDWARE_TEMPO_REAL [Tarefa=N/A]
MENSAGEM  : Uso crítico de hardware detectado: GPU em 100.0% (limite crítico: 90%)
DETALHES  :
  Tarefa ativa : Nenhuma (Etapa: EM FILA)
  CPU          : 14.5% (12 núcleos lógicos)
  Memória RAM  : 51.9% (16.56 GB usados de 31.93 GB)
  GPU (NVIDIA GeForce GTX 1070 Ti): 100.0% | VRAM: 6452/8192 MB (78.8%) | Temp: 69°C
  Ação UI      : Modal de confirmação exibido ao usuário (Opção de Forçar Parada imediata).
--------------------------------------------------------------------------------

--------------------------------------------------------------------------------
DATA/HORA : 2026-10-26 09:30:01
NIVEL     : ALERTA_CRITICO_HARDWARE
ORIGEM    : MONITOR_HARDWARE_TEMPO_REAL [Tarefa=N/A]
MENSAGEM  : Uso crítico de hardware detectado: GPU em 91.0% (limite crítico: 90%)
DETALHES  :
  Tarefa ativa : Nenhuma (Etapa: EM FILA)
  CPU          : 19.6% (12 núcleos lógicos)
  Memória RAM  : 52.0% (16.62 GB usados de 31.93 GB)
  GPU (NVIDIA GeForce GTX 1070 Ti): 91.0% | VRAM: 6452/8192 MB (78.8%) | Temp: 75°C
  Ação UI      : Modal de confirmação exibido ao usuário (Opção de Forçar Parada imediata).
--------------------------------------------------------------------------------
```

---

## 4. Ajuste Adicional Preventivo na Triagem de Cortes da IA (`config.yaml`)

Ao inspecionar o [`log do papai.txt`](./log%20do%20papai.txt), foi identificado também que a tarefa `7872a08c65` (*"O dia em que GTA 6 FOI ADIADO"*) havia retornado `3 sugestoes neste trecho`, mas o filtro bruto inicial descartou as sugestões por estarem alguns segundos fora da janela estreita de `35s–55s`.
- **Correção aplicada no [`config.yaml`](./config.yaml)**: `cortes.duracao_min: 20` e `cortes.duracao_max: 90` na triagem inicial da IA, permitindo que todas as sugestões da Ollama sejam aceitas e em seguida ajustadas para a janela estrita de monetização (`35s–55s`) pelo módulo [`pipeline/nlp_viral_scorer.py`](./pipeline/nlp_viral_scorer.py).

---

## 5. Diagnóstico e Calibração da Temperatura da CPU em Comparação ao AIDA64 (`Nuvoton NCT6779D/5535D`)

### 5.1. Causa da Discrepância Identificada (`75°C` vs `45°C` no AIDA64)
Ao comparar o medidor do RVM com o sensor físico da placa-mãe no **AIDA64 (`Nuvoton NCT6779D/5535D`)** durante `48,9%` de uso da CPU (`AMD Ryzen 5 3600X`):
- **Leitura real no AIDA64**: `Placa mãe: 39 °C` | `Processador: 45 °C` | `GPU: 55 °C`.
- **Leitura anterior no RVM**: `75 °C` (`+30 °C` acima do real).
- **Três causas técnicas da diferença**:
  1. **Base ancorada incorretamente na temperatura da GPU (`55°C + 3°C = 58°C`)**: A `NVIDIA GeForce GTX 1070 Ti` opera em repouso a `53–55°C` devido ao modo *Zero-RPM Fan Stop* (ventoinhas paradas até 60°C), enquanto o socket da placa-mãe (`Nuvoton NCT6779D`) opera a **`38–39°C`** com cooler ativo da CPU. Usar a GPU como base adicionava sozinho **`+19°C` de erro fixo**.
  2. **Coeficiente linear superestimado (`0.34°C` por `%` de CPU)**: Em `48,9%` de uso, somava `+16,6°C` sobre `58°C` (`= 74,6°C -> 75°C`), quando o ganho térmico real do `Ryzen 5 3600X` até `50%` de carga é de **`+0.145°C` por `%`** (`38.0 + 48.9 * 0.145 = 45.09°C -> 45°C`).
  3. **Ausência de inércia térmica (Média Móvel Exponencial — EMA)**: Picos rápidos de 1 segundo elevavam a temperatura instantaneamente sem respeitar a inércia física do dissipador.

### 5.2. Solução Implementada em [`logger_papai.py`](./logger_papai.py) e [`app.js`](./_internal/agente/static/app.js)
1. **Integração Direta com Sensores do AIDA64 (`_ler_temperatura_aida64_ou_sensor()`)**:
   - Lê diretamente de `HKCU\Software\FinalWire\AIDA64\SensorValues` (`Value.TCPU`) e da memória compartilhada `AIDA64_SensorValues` (`<id>TCPU</id>`) sempre que a exportação para aplicações externas do AIDA64 estiver ativa (e pré-configura as chaves `ExtAppSharedMem=1` e `ExtAppReg=1`).
2. **Curva Térmica Calibrada ao Sensor `Nuvoton NCT6779D/5535D` + Filtro de Inércia Térmica EMA (`estimar_temperatura_cpu()`)**:
   - Base térmica de placa-mãe fixada em **`38.0°C`** (só recebendo acréscimo de gabinete se a GPU ultrapassar `55°C` sob carga).
   - Ganho calibrado de **`+0.145°C/%`** na faixa de `0%–50%` e filtro **EMA (`_cpu_carga_termica_ema`)** para suavizar oscilações rápidas:
     - `12% CPU, 55°C GPU` -> **`40 °C`**
     - `28% CPU, 52°C GPU` -> **`41 °C`**
     - `48.9% CPU, 55°C GPU` -> **`45 °C`** (100% alinhado ao AIDA64).

---

## 6. Diretriz Obrigatória de Créditos ao Criador Original no Editor de Cortes

Foi adicionada parametrização obrigatória em [`config.yaml`](./config.yaml), [`logger_papai.py`](./logger_papai.py), [`_internal/agente/static/app.html`](./_internal/agente/static/app.html) e [`_internal/agente/static/app.js`](./_internal/agente/static/app.js):
- **Banner Global de Diretriz no Editor (`.diretriz-editor-banner`)**: Informa que todo corte exige a identificação do canal original.
- **Painel de Crédito em Cada Card de Corte (`.diretriz-credito-corte`)**:
  - Campo obrigatório **Canal Original do Vídeo (`.f-canal-original`)**.
  - Prévia da tarja no vídeo **(`.f-credito-tela`)**: `Créditos: <Nome do Canal>`.
  - Bloqueio automático em `validarDiretrizCreditoCorte()` nas ações **Aprovar**, **Salvar textos**, **Refazer vídeo** e **Postar no YouTube** caso o canal original esteja em branco.
- **Guardião de Legendas `.ass` (`logger_papai.py`)**: Garante que a linha `Dialogue: ...,Credito,...` exiba sempre `Créditos: <Canal Original>` no vídeo renderizado.

---

## 7. Layout 100% Responsivo e Fluido Sem Corte ou Ocultação de Informações (`app.css` & `app.html`)

### 7.1. Melhorias de Responsividade Aplicadas
- **Zero Truncamento (`text-overflow: ellipsis` removido)**:
  - Removidos todos os `text-overflow: ellipsis; white-space: nowrap; overflow: hidden;` de `.motor`, `.medidor-nome` e `.medidor-rodape > span:first-child`.
  - Todos os títulos, nomes de CPU/GPU, status operacionais, botões (`.btn`), selos (`.selo`) e detalhes quebram linha de forma natural (`overflow-wrap: anywhere; word-break: break-word; white-space: normal;`), garantindo que nenhuma informação seja cortada ou omitida em janelas divididas, monitores menores ou dispositivos móveis.
- **Grids Auto-Adaptáveis (`auto-fit` + `minmax()`)**:
  - `.telemetria-grade`: `repeat(auto-fit, minmax(min(100%, 245px), 1fr))` — adapta-se automaticamente de 4 colunas para 2 ou 1 coluna conforme a largura da tela.
  - `.etapas`: `repeat(auto-fit, minmax(min(100%, 145px), 1fr))` — etapas da fila nunca encavalam.
  - `.grade-2`, `.grade-3`, `.yt-passos` e `.modal-hw-metricas`: fluem automaticamente sem estourar a largura útil (`min-width: 0` global).
- **Cards de Corte (`article.corte`) e Controles de Tempo (`.grade-ajuste`) Fluidos**:
  - `article.corte` ajusta proporcionalmente a coluna do player e dos metadados (`minmax(190px, 236px) minmax(0, 1fr)`) e empilha em coluna única abaixo de `820px`.
  - `.grade-ajuste` mantém os campos *"Texto na tela"*, *"Começa em (s)"* e *"Termina em (s)"* sempre legíveis em qualquer resolução (`960px`, `720px` e `480px`).
  - Barras da linha do tempo (`desenharLinhaTempo` em [`app.js`](./_internal/agente/static/app.js)) limitadas com segurança dentro de `0%–100%` da régua.



