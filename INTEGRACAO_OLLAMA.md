# Guia de Integração com Ollama Local — RVM

Este documento descreve como configurar e utilizar o **Ollama** localmente no projeto **RVM (Agente de Cortes)** sem necessidade de chaves de API pagas.

---

## 1. Instalação do Ollama na Máquina Local

1. Execute o instalador **`OllamaSetup.exe`** (disponível na pasta `Teste` ou em https://ollama.com/download).
2. Conclua a instalação. O serviço do Ollama iniciará automaticamente em segundo plano no endereço padrão:
   ```
   http://localhost:11434
   ```

---

## 2. Modelo de IA Instalado

Verificando com `ollama list`, sua máquina já possui o modelo **`gemma4:e4b`** instalado (6.6 GB).

Caso precise instalá-lo novamente em outra máquina:

```powershell
ollama pull gemma4:e4b
```

Para verificar os modelos instalados na máquina:

```powershell
ollama list
```

---

## 3. Configuração no RVM

O arquivo [`config.yaml`](./config.yaml) foi configurado para usar o **`gemma4:e4b`** no Ollama como provedor padrão:

```yaml
ia:
  # Qual IA escolhe os melhores trechos: claude | gemini | ollama
  provedor: "ollama"
  modelo_claude: "claude-sonnet-5-5"
  modelo_gemini: "gemini-flash-latest"
  modelo_ollama: "gemma4:e4b"        # modelo instalado localmente no Ollama
  ollama_url: "http://localhost:11434"
```

### Pela Interface Web (`RVM.exe`)
1. Abra o **`RVM.exe`** (o painel abrirá em `http://localhost:5050`).
2. Acesse a aba **Ajustes** (`#ajustes`).
3. Em **Inteligência artificial → Quem escolhe os trechos**, confirme que está selecionado **`Ollama (grátis, no seu PC)`**.
4. Expanda a seção **Modelos** para conferir ou alterar:
   - **Modelo do Ollama**: `gemma4:e4b`
   - **Endereço do Ollama**: `http://localhost:11434`
5. Clique em **Salvar ajustes**.

---

## 4. Uso via Docker Compose

Caso esteja executando via [`docker-compose.yml`](./docker-compose.yml):

1. Suba os containers:
   ```powershell
   docker compose up -d
   ```
2. Baixe o modelo dentro do container do Ollama:
   ```powershell
   docker exec -it rvm-ollama ollama pull gemma4:e4b
   ```
3. Para comunicação entre containers, utilize `http://ollama:11434` como URL do Ollama (ou `http://host.docker.internal:11434` caso queira usar o Ollama instalado diretamente no Windows).

---

## 5. Diagnóstico e Teste

1. Com o RVM aberto no navegador, vá até a aba **Diagnóstico** (`#diagnostico`).
2. Clique em **Verificar de novo** e depois em **Testar a IA**.
3. Se o Ollama estiver ativo e com o modelo baixado, o teste confirmará que a integração local está pronta para gerar cortes.
