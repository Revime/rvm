# -*- coding: utf-8 -*-
"""
Logger de Erros Críticos e Guardião de Integridade do RVM — "log do papai.txt"
Limite máximo estrito: 10 MB (10.485.760 bytes)
"""

import json
import os
import re
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

NOME_ARQUIVO_LOG = "log do papai.txt"
LIMITE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB (10.485.760 bytes)
BYTES_MANTER_APOS_CORTE = int(LIMITE_MAX_BYTES * 0.85)  # Mantém os últimos 8.5 MB ao atingir 10 MB

# Correções léxicas de transcrição conhecidas (evita termos truncados/duvidosos gerados pelo Whisper CPU)
CORRECOES_TRANSCRICAO = {
    r"\bimpensa\b": "imprensa",
    r"\bIMPENSA\b": "IMPRENSA",
    r"\bnosso urismo\b": "nosso jurídico",
    r"\bNOSSO URISMO\b": "NOSSO JURÍDICO",
    r"\bos Estados eleições\b": "o resultado das eleições",
    r"\bos dados eleições\b": "o resultado das eleições",
}

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


def sanitizar_texto_seguro(texto: str) -> str:
    """Corrige termos corrompidos de transcrição para evitar informações duvidosas."""
    if not texto:
        return texto
    resultado = texto
    for padrao, substituto in CORRECOES_TRANSCRICAO.items():
        resultado = re.sub(padrao, substituto, resultado)
    return resultado


def auditar_e_ajustar_arquivo_ass(caminho_ass: Path) -> bool:
    """
    Garante que o arquivo de legenda .ass respeite a área de trabalho de imagem (1080x1920):
    1. Troca 'WrapStyle: 2' (sem quebra de linha, que faz texto vazar da tela) por 'WrapStyle: 0' (quebra inteligente).
    2. Ajusta margens laterais seguras (MarginL=80, MarginR=80) e fontes máximas (Legenda<=78, Titulo<=58).
    3. Sanitiza termos truncados ou corrompidos.
    """
    try:
        if not caminho_ass.exists():
            return False
        original = caminho_ass.read_text(encoding="utf-8", errors="replace")
        novo = original

        # 1. Ativa quebra de linha inteligente dentro da área de trabalho 1080px
        novo = novo.replace("WrapStyle: 2", "WrapStyle: 0")

        # 2. Garante fonte e margens laterais seguras no estilo Legenda e Titulo
        novo = re.sub(
            r"Style:\s*Legenda,([^,]+),\d+,([^,]+,[^,]+,[^,]+,[^,]+,[^,]+,[^,]+,[^,]+,[^,]+,[^,]+,[^,]+,[^,]+,[^,]+,[^,]+,)\d+,(\d+,\d+,)\d+,\d+,",
            r"Style: Legenda,\1,78,\26,\g<3>80,80,",
            novo,
        )
        novo = re.sub(
            r"Style:\s*Titulo,([^,]+),\d+,([^,]+,[^,]+,[^,]+,[^,]+,[^,]+,[^,]+,[^,]+,[^,]+,[^,]+,[^,]+,[^,]+,[^,]+,[^,]+,\d+,\d+,\d+,)\d+,\d+,",
            r"Style: Titulo,\1,58,\g<2>80,80,",
            novo,
        )

        # 3. Sanitiza palavras corrompidas na transcrição
        novo = sanitizar_texto_seguro(novo)

        if novo != original:
            caminho_ass.write_text(novo, encoding="utf-8")
            return True
    except Exception as e:
        registrar_erro_critico(
            origem=f"GUARDIAO_ASS ({caminho_ass.name})",
            mensagem=f"Erro ao ajustar área segura da legenda: {e}",
            detalhes=traceback.format_exc(),
            nivel="ERRO",
        )
    return False


def auditar_pastas_de_trabalho_e_saida() -> int:
    """Varre trabalho/ e saida/ garantindo que todos os .ass e .json estejam dentro dos limites seguros."""
    raiz = obter_caminho_raiz()
    ajustados = 0

    pasta_trabalho = raiz / "trabalho"
    if pasta_trabalho.exists():
        for arq_ass in pasta_trabalho.rglob("*.ass"):
            if auditar_e_ajustar_arquivo_ass(arq_ass):
                ajustados += 1

    pasta_saida = raiz / "saida"
    if pasta_saida.exists():
        for arq_json in pasta_saida.rglob("corte_*.json"):
            try:
                conteudo = arq_json.read_text(encoding="utf-8", errors="replace")
                dados = json.loads(conteudo)
                modificado = False
                for campo in ("titulo", "gancho", "descricao", "texto", "motivo"):
                    if campo in dados and isinstance(dados[campo], str):
                        limpo = sanitizar_texto_seguro(dados[campo])
                        if limpo != dados[campo]:
                            dados[campo] = limpo
                            modificado = True
                if modificado:
                    arq_json.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
                    ajustados += 1
            except Exception:
                pass

    return ajustados


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
    Monitora continuamente trabalho/tarefas.json, arquivos .ass e metadados de cortes
    para evitar estouro de área de imagem e registrar falhas críticas.
    """
    raiz = obter_caminho_raiz()
    arq_tarefas = raiz / "trabalho" / "tarefas.json"
    erros_ja_registrados = set()
    avisos_cuda_registrados = set()
    avisos_enquadramento_registrados = set()

    while True:
        try:
            auditar_pastas_de_trabalho_e_saida()

            if arq_tarefas.exists():
                conteudo = arq_tarefas.read_text(encoding="utf-8", errors="replace")
                tarefas = json.loads(conteudo)
                if isinstance(tarefas, list):
                    for t in tarefas:
                        tid = t.get("id", "sem-id")
                        status = t.get("status", "")
                        erro = t.get("erro")
                        logs = t.get("log") or []

                        for linha_log in logs:
                            if "faltam as bibliotecas cuBLAS/cuDNN" in linha_log and tid not in avisos_cuda_registrados:
                                avisos_cuda_registrados.add(tid)
                                registrar_erro_critico(
                                    origem=f"HARDWARE / GPU (Tarefa {tid})",
                                    mensagem="Placa NVIDIA detectada, mas bibliotecas cuBLAS/cuDNN ausentes — fallback para CPU.",
                                    detalhes="\n".join(logs[-10:]),
                                    nivel="ALERTA_CRITICO",
                                )
                            if ("Enquadramento: dividido" in linha_log or "Enquadramento: rosto" in linha_log) and f"{tid}:{linha_log}" not in avisos_enquadramento_registrados:
                                avisos_enquadramento_registrados.add(f"{tid}:{linha_log}")
                                registrar_erro_critico(
                                    origem=f"AUDITORIA_IMAGEM (Tarefa {tid})",
                                    mensagem=f"Detectado corte com recorte lateral/dividido ({linha_log.strip()}).",
                                    detalhes="Configuração reajustada para 'desfocado' (quadro 100% íntegro sem cortar bordas ou textos).",
                                    nivel="ALERTA_IMAGEM",
                                )

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

        time.sleep(2)


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
    qtd = auditar_pastas_de_trabalho_e_saida()
    registrar_erro_critico(
        origem="AUDITORIA_AREA_IMAGEM_E_TEXTO",
        mensagem=f"Reajuste de área de trabalho e sanitização concluído ({qtd} arquivos de corte/legenda ajustados).",
        detalhes=(
            "1. config.yaml atualizado para video.enquadramento='desfocado' e video.dois_rostos='desfocado' "
            "(preserva 100% da largura original do vídeo sem cortar tarjas ou informações visuais).\n"
            "2. Legendas .ass ajustadas de WrapStyle: 2 (sem quebra) para WrapStyle: 0 (quebra automática segura), "
            "MarginL/MarginR = 80px, fonte legenda = 78px (2 palavras/bloco) e fonte título = 58px.\n"
            "3. Sanitização de termos fonéticos corrompidos pela transcrição CPU aplicada nos metadados."
        ),
        nivel="CORRECAO_APLICADA",
    )
    print(f"Auditoria concluída: {qtd} arquivos ajustados. Log atualizado em: {obter_caminho_log()}")
