# Log de Diagnóstico e Correção — Duplicidade na Imagem dos Cortes

**Data:** 26/10/2026  
**Episódio analisado:** `Flávio diz que pedirá anulação das eleições e cita adiamento de votação; medida foi pedida pelo PL` (`flavio-diz-que-pedira-anulacao-d-ny1mspspk-8`)  
**Status:** Corrigido

---

## 1. Sintoma Observado

Nos vídeos gerados (`corte_01.mp4`, `corte_02.mp4` e `corte_03.mp4`), a imagem do vídeo vertical (9:16) apareceu **duplicada/dividida verticalmente** (um recorte na metade superior mostrando pessoas ao fundo e outro recorte na metade inferior mostrando o entrevistado principal), além de exibir duas legendas simultâneas (a legenda original embutida no vídeo da UOL e a legenda gerada pelo RVM).

---

## 2. Evidências nos Logs de Processamento

Na análise do arquivo `trabalho/tarefas.json` (tarefa `3f5e04165a`) e dos metadados em `saida/flavio-diz-que-pedira-anulacao-d-ny1mspspk-8/corte_01.json`, foi registrado:

```text
00:46:31  Detector de rosto: yunet
00:46:31  Corte 1: O Supremo deveria ter anulado as eleições: O que o Ministro   (30s)
00:46:37    Enquadramento: dividido 100%
...
00:46:50  Corte 2: Decisão 'Inaceitável' do Supremo: Regra do jogo mudou em cim  (36s)
00:46:57    Enquadramento: dividido 100%
...
00:47:12  Corte 3: Ex-sócio do Zanin foi o responsável por essa manobra eleitor  (34s)
00:47:18    Enquadramento: dividido 100%
```

E no JSON de saída de cada corte (`corte_01.json`, `corte_02.json`, `corte_03.json`):

```json
"layouts": {
  "dividido": 1.0
}
```

---

## 3. Causa Raiz

1. **Detecção de múltiplos rostos em cena de coletiva/multidão (`YuNet`)**:
   O vídeo original possui várias pessoas próximas e ao fundo do orador principal (apoiadores e imprensa). O detector facial `face_detection_yunet_2023mar.onnx` identificou múltiplos rostos simultâneos afastados entre si em 100% dos quadros.
2. **Configuração `dois_rostos: "dividido"` ativa por padrão**:
   No arquivo [`config.yaml`](./config.yaml), as opções estavam definidas como:
   ```yaml
   video:
     enquadramento: "auto"
     dois_rostos: "dividido"
   ```
   Quando o modo `auto` detecta 2 ou mais rostos distantes, a regra `dois_rostos: "dividido"` divide o quadro vertical 9:16 em **duas metades empilhadas** (uma caixa superior focada no segundo rosto detectado ao fundo e uma caixa inferior focada no rosto principal), gerando o efeito visual de imagem duplicada.

---

## 4. Correções Aplicadas

### 4.1. Ajuste de Enquadramento no [`config.yaml`](./config.yaml)
Alterado o padrão de vídeo para focar sempre em **quadro único** no rosto principal e, caso o modo automático seja usado em cenas com mais de uma pessoa, utilizar o modo `desfocado` em vez de dividir a tela:

```yaml
video:
  enquadramento: "rosto"
  dois_rostos: "desfocado"
```

### 4.2. Indicador e Alerta de Layout na Interface ([`_internal/agente/static/app.js`](./_internal/agente/static/app.js))
- Adicionada exibição do modo de enquadramento aplicado nos metadados de cada card de corte (`Quadro único` vs `Tela dividida`).
- Quando um corte antigo tiver sido gerado com `dividido`, o card informa como refazer o corte em quadro único clicando em **Refazer vídeo**.

---

## 5. Como Regerar Cortes Já Processados

Para corrigir cortes que já haviam sido renderizados antes desta alteração:
1. Na aba **Cortes**, clique no botão **Refazer vídeo** dentro do corte desejado (ou desmarque antes *"Colocar a legenda do RVM"* se o vídeo original da fonte já possuir legenda embutida).
2. O RVM irá reprocessar apenas a montagem do vídeo (leva ~19 segundos por corte) já aplicando o quadro único sem duplicidade.



---

## 6. Segunda Auditoria — Correção de Corte Lateral de Imagem e Estouro de Texto (26/10/2026 - 01:06)

**Episódio analisado:** `FLÁVIO BOLSONARO NÃO RECONHECE DERROTA E VAI PEDIR ANULAÇÃO DAS ELEIÇÕES` (`flavio-bolsonaro-nao-reconhece-d-bhbubcnvg-o` — Canal Itatiaia)

### 6.1. O que houve
1. **Corte lateral de informações do vídeo original (`Enquadramento: rosto 100%`)**:
   O modo `rosto` recortou verticalmente (9:16) o centro da imagem original 16:9 da Itatiaia. Com isso, a tarja jornalística inferior do próprio vídeo (`"Flávio Bolsonaro diz que..." / "...pedirá anulação das..."`) teve suas extremidades esquerda e direita cortadas fora da área de trabalho da imagem.
2. **Estouro horizontal de texto nas legendas `.ass` (`WrapStyle: 2` + fonte `110px` + `3 palavras/bloco`)**:
   Os arquivos `.ass` gerados tinham `WrapStyle: 2` (que desativa a quebra automática de linha no `libass`/`FFmpeg`) e fonte tamanho `110` com 3 palavras por bloco, fazendo palavras extensas em caixa alta passarem dos limites laterais de `1080px`.
3. **Termos duvidosos na transcrição CPU (`Whisper small`)**:
   Palavras como `"impensa"` (imprensa), `"nosso urismo"` (nosso jurídico) e `"os Estados eleições"` (o resultado das eleições) foram geradas pela transcrição em CPU.

### 6.2. Correção Definitiva Aplicada
- **[`config.yaml`](./config.yaml)**:
  - `video.enquadramento: "desfocado"` e `video.dois_rostos: "desfocado"`: preserva **100% da área horizontal e vertical da imagem original** centralizada nos `1080px`, sem jamais cortar tarjas, textos ou bordas do vídeo.
  - `legenda.tamanho: 78` (antes `110`), `legenda.palavras_por_bloco: 2` (antes `3`), `legenda.contorno: 6` e `titulo_na_tela.tamanho: 58` (antes `76`).
- **[`logger_papai.py`](./logger_papai.py)**:
  - Adicionada auditoria contínua (`auditar_pastas_de_trabalho_e_saida()`) que converte `WrapStyle: 2` para `WrapStyle: 0` (quebra automática de linha respeitando margens), aplica `MarginL=80` e `MarginR=80` nos arquivos `.ass` e corrige termos corrompidos nos arquivos `.ass` e `.json`.
