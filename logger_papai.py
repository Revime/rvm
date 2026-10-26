# -*- coding: utf-8 -*-
"""
Logger de Erros Críticos e Guardião de Integridade do RVM — "log do papai.txt"
Limites estritos por arquivo:
  - Máximo de 10.000 linhas (ao atingir, gera novo arquivo numerado: 'log do papai 1.txt', 'log do papai 2.txt', ...)
  - Máximo de 10 MB (10.485.760 bytes)
"""

import json
import os
import re
import shutil
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

NOME_BASE_LOG = "log do papai"
EXTENSAO_LOG = ".txt"
NOME_ARQUIVO_LOG = f"{NOME_BASE_LOG}{EXTENSAO_LOG}"
LIMITE_MAX_LINHAS = 10_000
LIMITE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB (10.485.760 bytes)

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
_erros_internos_registrados = set()
_arquivos_auditados_mtime = {}


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


def obter_proximo_caminho_numerado(pasta_raiz: Path) -> Path:
    """
    Retorna o próximo arquivo numerado disponível com o mesmo nome:
    'log do papai 1.txt', 'log do papai 2.txt', 'log do papai 3.txt', ...
    """
    indice = 1
    while True:
        candidato = pasta_raiz / f"{NOME_BASE_LOG} {indice}{EXTENSAO_LOG}"
        if not candidato.exists():
            return candidato
        indice += 1


def _contar_linhas(caminho: Path) -> int:
    if not caminho.exists():
        return 0
    with open(caminho, "rb") as f:
        return sum(1 for _ in f)


def _rotacionar_se_necessario(caminho_log: Path, novas_linhas: int, novos_bytes: int) -> None:
    """
    Verifica se 'log do papai.txt' atingiu 10.000 linhas ou 10 MB.
    Caso atinja qualquer um dos limites, gera um novo arquivo com o mesmo nome
    acrescido de um número ('log do papai 1.txt', 'log do papai 2.txt', ...)
    e inicia um novo 'log do papai.txt' limpo.
    """
    if not caminho_log.exists():
        return

    tamanho_atual = caminho_log.stat().st_size
    linhas_atuais = _contar_linhas(caminho_log)

    if (linhas_atuais + novas_linhas <= LIMITE_MAX_LINHAS) and (tamanho_atual + novos_bytes <= LIMITE_MAX_BYTES):
        return

    pasta_raiz = caminho_log.parent
    destino_numerado = obter_proximo_caminho_numerado(pasta_raiz)
    shutil.move(str(caminho_log), str(destino_numerado))

    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cabecalho = (
        "================================================================================\n"
        "                        LOG DO PAPAI — RVM (AGENTE DE CORTES)\n"
        "          REGISTRO CENTRAL DE ERROS CRÍTICOS E AUDITORIA DE FALHAS\n"
        "       LIMITE MÁXIMO: 10.000 LINHAS OU 10 MB POR ARQUIVO (ROTATIVO)\n"
        "================================================================================\n"
        f"[{agora}] [SISTEMA] Limite atingido ({linhas_atuais} linhas / {tamanho_atual} bytes). "
        f"Histórico anterior arquivado em: '{destino_numerado.name}'.\n\n"
    )
    caminho_log.write_text(cabecalho, encoding="utf-8")


def registrar_erro_critico(
    origem: str,
    mensagem: str,
    detalhes: str = "",
    nivel: str = "CRITICO",
) -> None:
    """Grava um erro crítico em 'log do papai.txt' respeitando o limite de 10.000 linhas e 10 MB."""
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
    qtd_novas_linhas = texto.count("\n")

    with _lock:
        try:
            _rotacionar_se_necessario(caminho_log, qtd_novas_linhas, len(dados))
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


def _ajustar_linha_style_ass(linha: str) -> str:
    """
    Ajusta de forma determinística (sem regex ambíguo) as linhas 'Style:' do formato .ass:
    Formato V4+ Styles (23 campos):
    0:Name, 1:Fontname, 2:Fontsize, ..., 16:Outline, 17:Shadow, 18:Alignment, 19:MarginL, 20:MarginR, 21:MarginV, 22:Encoding
    """
    if not linha.startswith("Style:"):
        return linha
    prefixo, _, resto = linha.partition(":")
    campos = [c.strip() for c in resto.split(",")]
    if len(campos) < 23:
        return linha

    nome_estilo = campos[0]
    if nome_estilo == "Legenda":
        campos[2] = "78"   # Fontsize seguro para 1080px
        campos[16] = "6"   # Outline
        campos[19] = "80"  # MarginL
        campos[20] = "80"  # MarginR
    elif nome_estilo == "Titulo":
        campos[2] = "58"   # Fontsize seguro para gancho superior
        campos[19] = "80"  # MarginL
        campos[20] = "80"  # MarginR
    elif nome_estilo == "Credito":
        campos[19] = "80"
        campos[20] = "80"

    return f"{prefixo}: " + ",".join(campos)


def auditar_e_ajustar_arquivo_ass(caminho_ass: Path) -> bool:
    """
    Garante que o arquivo de legenda .ass respeite a área de trabalho de imagem (1080x1920):
    1. Troca 'WrapStyle: 2' (sem quebra de linha) por 'WrapStyle: 0' (quebra inteligente automática).
    2. Ajusta margens laterais seguras (MarginL=80, MarginR=80) e fontes máximas (Legenda=78, Titulo=58).
    3. Sanitiza termos truncados ou corrompidos.
    """
    try:
        if not caminho_ass.exists():
            return False

        mtime = caminho_ass.stat().st_mtime
        chave_cache = str(caminho_ass)
        if _arquivos_auditados_mtime.get(chave_cache) == mtime:
            return False

        original = caminho_ass.read_text(encoding="utf-8", errors="replace")
        linhas_processadas = []
        for linha in original.splitlines():
            if linha.startswith("WrapStyle:"):
                linhas_processadas.append("WrapStyle: 0")
            elif linha.startswith("Style:"):
                linhas_processadas.append(_ajustar_linha_style_ass(linha))
            else:
                linhas_processadas.append(sanitizar_texto_seguro(linha))

        novo = "\n".join(linhas_processadas) + ("\n" if original.endswith("\n") else "")

        if novo != original:
            caminho_ass.write_text(novo, encoding="utf-8")
            _arquivos_auditados_mtime[chave_cache] = caminho_ass.stat().st_mtime
            return True

        _arquivos_auditados_mtime[chave_cache] = mtime
    except Exception as e:
        chave_err = f"ASS:{caminho_ass.name}:{type(e).__name__}:{e}"
        if chave_err not in _erros_internos_registrados:
            _erros_internos_registrados.add(chave_err)
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
                mtime = arq_json.stat().st_mtime
                chave_cache = str(arq_json)
                if _arquivos_auditados_mtime.get(chave_cache) == mtime:
                    continue
                conteudo = arq_json.read_text(encoding="utf-8", errors="replace")
                dados = json.loads(conteudo)
                modificado = False
                for campo in ("titulo", "gancho", "descricao", "texto", "motivo"):
                    if campo in dados and isinstance(dados[campo], str):
                        limpo = sanitizar_texto_seguro(dados[campo])
                        if limpo != dados[campo]:
                            dados[campo] = limpo
                            modificado = True
                if "ypp_monetization" not in dados or "titles" not in dados:
                    try:
                        from pipeline.orchestrator import YPPPipelineOrchestrator
                        YPPPipelineOrchestrator().process_all_episodes()
                        conteudo = arq_json.read_text(encoding="utf-8", errors="replace")
                        dados = json.loads(conteudo)
                        modificado = True
                    except Exception:
                        pass
                if modificado:
                    arq_json.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
                    _arquivos_auditados_mtime[chave_cache] = arq_json.stat().st_mtime
                    ajustados += 1
                else:
                    _arquivos_auditados_mtime[chave_cache] = mtime
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
    para evitar estouro de área de imagem e registrar falhas críticas sem duplicação.
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
                                    mensagem="Placa NVIDIA detectada sem cuBLAS/cuDNN — usando CPU (ajustado dispositivo='cpu' no config.yaml).",
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
    qtd = auditar_pastas_de_trabalho_e_saida()
    print(f"Auditoria concluída com sucesso: {qtd} arquivos ajustados. Limite por arquivo: {LIMITE_MAX_LINHAS} linhas.")
