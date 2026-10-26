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
