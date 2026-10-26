# -*- coding: utf-8 -*-
"""
Logger de Erros Críticos do RVM — "log do papai.txt"
Limite máximo estrito: 10 MB (10.485.760 bytes)
"""

import json
import os
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

NOME_ARQUIVO_LOG = "log do papai.txt"
LIMITE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB (10.485.760 bytes)
BYTES_MANTER_APOS_CORTE = int(LIMITE_MAX_BYTES * 0.85)  # Mantém os últimos 8.5 MB ao atingir 10 MB

_lock = threading.Lock()
_iniciado = False


def obter_caminho_raiz() -> Path:
    """Retorna a pasta raiz onde fica o RVM.exe / config.yaml."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    atual = Path(__file__).resolve().parent
    if atual.name == "_internal":
        return atual.parent
    if atual.parent.name == "_internal":
        return atual.parent.parent
    return atual


def obter_caminho_log() -> Path:
    return obter_caminho_raiz() / NOME_ARQUIVO_LOG


def _garantir_limite_10mb(caminho_log: Path, novos_bytes: int) -> None:
    """
    Garante que o arquivo 'log do papai.txt' nunca ultrapasse 10 MB.
    Quando o tamanho atual + novo registro passa de 10 MB, descarta os logs mais antigos
    do início do arquivo preservando os mais recentes.
    """
    if not caminho_log.exists():
        return
    tamanho_atual = caminho_log.stat().st_size
    if tamanho_atual + novos_bytes <= LIMITE_MAX_BYTES:
        return

    with open(caminho_log, "rb") as f:
        if tamanho_atual > BYTES_MANTER_APOS_CORTE:
            f.seek(tamanho_atual - BYTES_MANTER_APOS_CORTE)
        resto = f.read()

    # Alinha na próxima quebra de linha para não cortar uma linha ao meio
    pos_nl = resto.find(b"\n")
    if pos_nl != -1:
        resto = resto[pos_nl + 1:]

    cabecalho_rotacao = (
        f"================================================================================\n"
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SISTEMA] "
        f"Limite de 10 MB atingido — registros antigos reciclados automaticamente.\n"
        f"================================================================================\n"
    ).encode("utf-8")

    with open(caminho_log, "wb") as f:
        f.write(cabecalho_rotacao + resto)


def registrar_erro_critico(
    origem: str,
    mensagem: str,
    detalhes: str = "",
    nivel: str = "CRITICO",
) -> None:
    """Grava um erro crítico em 'log do papai.txt' respeitando o limite de 10 MB."""
    caminho_log = obter_caminho_log()
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bloco = [
        "--------------------------------------------------------------------------------",
        f"DATA/HORA : {agora}",
        f"NIVEL     : {nivel}",
        f"ORIGEM    : {origem}",
        f"MENSAGEM  : {mensagem}",
    ]
    if detalhes:
        bloco.append("DETALHES  :")
        for linha in str(detalhes).rstrip().splitlines():
            bloco.append(f"  {linha}")
    bloco.append("--------------------------------------------------------------------------------\n")
    texto = "\n".join(bloco) + "\n"
    dados = texto.encode("utf-8", errors="replace")

    with _lock:
        try:
            _garantir_limite_10mb(caminho_log, len(dados))
            with open(caminho_log, "ab") as f:
                f.write(dados)
        except Exception:
            pass


def _hook_excecao_global(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    registrar_erro_critico(
        origem="PYTHON_RUNTIME (Exceção Não Tratada)",
        mensagem=f"{exc_type.__name__}: {exc_value}",
        detalhes=tb_str,
        nivel="CRITICO",
    )
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


def _hook_excecao_thread(args):
    if issubclass(args.exc_type, SystemExit):
        return
    tb_str = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    nome_thread = getattr(args.thread, "name", "ThreadDesconhecida")
    registrar_erro_critico(
        origem=f"THREAD ({nome_thread})",
        mensagem=f"{args.exc_type.__name__}: {args.exc_value}",
        detalhes=tb_str,
        nivel="CRITICO",
    )


def _monitorar_tarefas_e_ffmpeg():
    """
    Monitora continuamente trabalho/tarefas.json e logs do ffmpeg para capturar
    automaticamente qualquer falha de tarefa, IA (Ollama/Claude/Gemini), YouTube ou renderização.
    """
    raiz = obter_caminho_raiz()
    arq_tarefas = raiz / "trabalho" / "tarefas.json"
    erros_ja_registrados = set()
    avisos_cuda_registrados = set()

    while True:
        try:
            if arq_tarefas.exists():
                conteudo = arq_tarefas.read_text(encoding="utf-8", errors="replace")
                tarefas = json.loads(conteudo)
                if isinstance(tarefas, list):
                    for t in tarefas:
                        tid = t.get("id", "sem-id")
                        status = t.get("status", "")
                        erro = t.get("erro")
                        logs = t.get("log") or []

                        # Captura alerta crítico de falta de bibliotecas CUDA/cuBLAS
                        for linha_log in logs:
                            if "faltam as bibliotecas cuBLAS/cuDNN" in linha_log and tid not in avisos_cuda_registrados:
                                avisos_cuda_registrados.add(tid)
                                registrar_erro_critico(
                                    origem=f"HARDWARE / GPU (Tarefa {tid})",
                                    mensagem="Placa NVIDIA detectada, mas bibliotecas cuBLAS/cuDNN ausentes — fallback para CPU.",
                                    detalhes="\n".join(logs[-10:]),
                                    nivel="ALERTA_CRITICO",
                                )

                        # Captura erro de execução da tarefa
                        if status == "erro" or erro:
                            chave_erro = f"{tid}:{status}:{erro}"
                            if chave_erro not in erros_ja_registrados:
                                erros_ja_registrados.add(chave_erro)
                                tipo = t.get("tipo", "processar")
                                etapa = t.get("etapa", "desconhecida")
                                titulo = t.get("titulo") or t.get("origem") or tid
                                ultimos_logs = "\n".join(logs[-20:]) if logs else "Sem linhas de log adicionais."
                                registrar_erro_critico(
                                    origem=f"FILA_RVM [tipo={tipo} | etapa={etapa} | id={tid}]",
                                    mensagem=f"Falha em '{titulo}': {erro or 'Erro sem mensagem detalhada'}",
                                    detalhes=f"Origem: {t.get('origem', '-')}\nEpisódio: {t.get('episodio', '-')}\nÚltimos registros:\n{ultimos_logs}",
                                    nivel="CRITICO",
                                )
        except Exception:
            pass

        time.sleep(3)


def iniciar_monitoramento() -> None:
    """Ativa os hooks de exceção e a thread de monitoramento do 'log do papai.txt'."""
    global _iniciado
    if _iniciado:
        return
    _iniciado = True

    sys.excepthook = _hook_excecao_global
    if hasattr(threading, "excepthook"):
        threading.excepthook = _hook_excecao_thread

    t = threading.Thread(target=_monitorar_tarefas_e_ffmpeg, name="MonitorLogDoPapai", daemon=True)
    t.start()


if __name__ == "__main__":
    iniciar_monitoramento()
    registrar_erro_critico(
        origem="TESTE_MANUAL",
        mensagem="Verificação manual do logger 'log do papai.txt' executada com sucesso.",
        detalhes=f"Arquivo: {obter_caminho_log()}\nLimite configurado: {LIMITE_MAX_BYTES} bytes (10 MB).",
        nivel="INFO_AUDITORIA",
    )
    print(f"Log atualizado em: {obter_caminho_log()}")
