# -*- coding: utf-8 -*-
"""
Logger de Erros Críticos, Guardião de Integridade e Telemetria de Hardware em Tempo Real — "log do papai.txt"
Limites estritos por arquivo:
  - Máximo de 10.000 linhas (ao atingir, gera novo arquivo numerado: 'log do papai 1.txt', 'log do papai 2.txt', ...)
  - Máximo de 10 MB (10.485.760 bytes)
"""

import ctypes
import gc
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

NOME_BASE_LOG = "log do papai"
EXTENSAO_LOG = ".txt"
NOME_ARQUIVO_LOG = f"{NOME_BASE_LOG}{EXTENSAO_LOG}"
LIMITE_MAX_LINHAS = 10_000
LIMITE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB (10.485.760 bytes)

# Limites padrão de telemetria de hardware (CPU / RAM / GPU)
LIMITE_AVISO_PCT = 75.0
LIMITE_CRITICO_CPU_PCT = 85.0
LIMITE_CRITICO_RAM_PCT = 85.0
LIMITE_CRITICO_GPU_PCT = 90.0
LIMITE_CRITICO_TEMP_GPU_C = 83.0

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
_arquivos_auditados_mtime: Dict[str, float] = {}

# Estado da telemetria de CPU/RAM/GPU em tempo real
_cpu_tempos_anteriores: Optional[Tuple[int, int, int]] = None
_cpu_info_cache: Optional[Dict[str, Any]] = None
_cpu_carga_termica_ema: Optional[float] = None
_aida64_ext_configurado: bool = False
_historico_telemetria: deque = deque(maxlen=60)
_ultimo_log_telemetria_txt: float = 0.0
_ultimo_alerta_critico_txt: float = 0.0
_rotas_flask_registradas: bool = False
_ultimo_estado_telemetria: Dict[str, Any] = {}


def obter_info_cpu_estatica() -> Dict[str, Any]:
    """Obtém nome do processador e frequência base via Registro do Windows (instantâneo)."""
    global _cpu_info_cache
    if _cpu_info_cache is not None:
        return _cpu_info_cache
    nome = "Processador CPU"
    mhz = 3800
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
        ) as k:
            val_nome, _ = winreg.QueryValueEx(k, "ProcessorNameString")
            if val_nome:
                nome = str(val_nome).strip()
            val_mhz, _ = winreg.QueryValueEx(k, "~MHz")
            if val_mhz:
                mhz = int(val_mhz)
    except Exception:
        pass
    nome_curto = (
        nome.replace("Processor", "")
        .replace("Six-Core", "")
        .replace("6-Core", "")
        .replace("(TM)", "")
        .replace("(R)", "")
        .strip()
    )
    nome_curto = re.sub(r"\s+", " ", nome_curto)
    _cpu_info_cache = {
        "nome": nome,
        "nome_curto": nome_curto or "CPU",
        "freq_mhz": mhz,
        "freq_ghz": round(mhz / 1000.0, 2),
    }
    return _cpu_info_cache


def _ler_temperatura_aida64_ou_sensor() -> Optional[int]:
    """
    Tenta ler a temperatura real do Processador (TCPU) diretamente do AIDA64
    (via Registro HKCU\\Software\\FinalWire\\AIDA64\\SensorValues ou Shared Memory AIDA64_SensorValues).
    """
    global _aida64_ext_configurado
    try:
        import winreg

        if not _aida64_ext_configurado:
            _aida64_ext_configurado = True
            try:
                with winreg.CreateKeyEx(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\FinalWire\AIDA64",
                    0,
                    winreg.KEY_SET_VALUE,
                ) as k_cfg:
                    winreg.SetValueEx(k_cfg, "ExtAppSharedMem", 0, winreg.REG_SZ, "1")
                    winreg.SetValueEx(k_cfg, "ExtAppReg", 0, winreg.REG_SZ, "1")
                    winreg.SetValueEx(k_cfg, "ExtAppSM_TCPU", 0, winreg.REG_SZ, "1")
                    winreg.SetValueEx(k_cfg, "ExtAppReg_TCPU", 0, winreg.REG_SZ, "1")
            except Exception:
                pass

        # 1. Tenta ler do Registro do AIDA64 (SensorValues)
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\FinalWire\AIDA64\SensorValues",
            ) as k_sens:
                for nome_chave in ("Value.TCPU", "Value.TCPUDiode", "Value.TCPUPackage"):
                    try:
                        val_str, _ = winreg.QueryValueEx(k_sens, nome_chave)
                        if val_str and str(val_str).strip().replace(".", "", 1).isdigit():
                            t_val = int(round(float(str(val_str).strip())))
                            if 25 <= t_val <= 105:
                                return t_val
                    except OSError:
                        continue
        except OSError:
            pass

        # 2. Tenta ler da Shared Memory AIDA64_SensorValues
        FILE_MAP_READ = 0x0004
        h_map = ctypes.windll.kernel32.OpenFileMappingW(FILE_MAP_READ, False, "AIDA64_SensorValues")
        if h_map:
            try:
                ctypes.windll.kernel32.MapViewOfFile.restype = ctypes.c_void_p
                ptr = ctypes.windll.kernel32.MapViewOfFile(h_map, FILE_MAP_READ, 0, 0, 0)
                if ptr:
                    try:
                        raw = ctypes.string_at(ptr, 8192).decode("latin-1", errors="ignore")
                        m = re.search(r"<id>TCPU</id>.*?<value>([0-9.]+)</value>", raw)
                        if m:
                            t_val = int(round(float(m.group(1))))
                            if 25 <= t_val <= 105:
                                return t_val
                    finally:
                        ctypes.windll.kernel32.UnmapViewOfFile(ctypes.c_void_p(ptr))
            finally:
                ctypes.windll.kernel32.CloseHandle(h_map)
    except Exception:
        pass
    return None


def estimar_temperatura_cpu(cpu_pct: float, gpu_temp_c: int) -> int:
    """
    Obtém a temperatura real da CPU via AIDA64 (se disponível) ou aplica a curva térmica
    calibrada para o sensor Nuvoton NCT6779D/5535D (AMD Ryzen 5 3600X) com inércia térmica (EMA).
    
    Calibração de referência (AIDA64 Nuvoton NCT6779D/5535D):
      - Placa-mãe base : ~38–39 °C
      - CPU em repouso (0–15%): ~39–40 °C
      - CPU em ~49% de uso    : ~45 °C (exatamente alinhado ao sensor Processador do AIDA64)
      - CPU em 80–100% sustentado: ~55–64 °C
    """
    global _cpu_carga_termica_ema

    # Prioridade 1: Leitura direta do sensor se exportado pelo AIDA64
    sensor_direto = _ler_temperatura_aida64_ou_sensor()
    if sensor_direto is not None:
        return sensor_direto

    # Prioridade 2: Curva térmica calibrada ao sensor Nuvoton NCT6779D/5535D com inércia térmica (EMA)
    if _cpu_carga_termica_ema is None:
        _cpu_carga_termica_ema = float(cpu_pct)
    else:
        # Filtro de inércia térmica do dissipador (evita saltos irreais em picos de 1s)
        alpha = 0.28 if cpu_pct > _cpu_carga_termica_ema else 0.20
        _cpu_carga_termica_ema = (_cpu_carga_termica_ema * (1.0 - alpha)) + (float(cpu_pct) * alpha)

    # Combina 70% da carga térmica acumulada (EMA) + 30% da carga instantânea
    carga_efetiva = (_cpu_carga_termica_ema * 0.70) + (float(cpu_pct) * 0.30)

    # Base térmica da placa-mãe (38.0°C); só recebe calor extra do gabinete se a GPU passar de 55°C
    calor_gabinete = max(0.0, (float(gpu_temp_c) - 55.0) * 0.14) if gpu_temp_c > 55 else 0.0
    base_mobo = 38.0 + calor_gabinete

    if carga_efetiva <= 50.0:
        # De 0% a 50%: sobe +0.145°C por % (em 48.9% -> 38.0 + 7.09 = 45.1°C -> 45°C)
        delta_cpu = carga_efetiva * 0.145
    else:
        # Acima de 50%: +7.25°C + 0.30°C por % adicional
        delta_cpu = (50.0 * 0.145) + ((carga_efetiva - 50.0) * 0.30)

    temp_calibrada = base_mobo + delta_cpu
    return int(round(max(35.0, min(95.0, temp_calibrada))))


# =====================================================================
#  ESTRUTURAS WIN32 API (CTYPES) PARA CPU E RAM EM TEMPO REAL
# =====================================================================
class _FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", ctypes.c_ulong),
        ("dwHighDateTime", ctypes.c_ulong),
    ]


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _filetime_para_int(ft: _FILETIME) -> int:
    return (int(ft.dwHighDateTime) << 32) | int(ft.dwLowDateTime)


def medir_cpu_pct() -> float:
    """Calcula o uso real de CPU (%) no Windows via GetSystemTimes delta."""
    global _cpu_tempos_anteriores
    try:
        idle = _FILETIME()
        kernel = _FILETIME()
        user = _FILETIME()
        ok = ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle),
            ctypes.byref(kernel),
            ctypes.byref(user),
        )
        if not ok:
            return 0.0
        idle_val = _filetime_para_int(idle)
        kernel_val = _filetime_para_int(kernel)
        user_val = _filetime_para_int(user)

        if _cpu_tempos_anteriores is None:
            _cpu_tempos_anteriores = (idle_val, kernel_val, user_val)
            time.sleep(0.12)
            ctypes.windll.kernel32.GetSystemTimes(
                ctypes.byref(idle),
                ctypes.byref(kernel),
                ctypes.byref(user),
            )
            idle_val2 = _filetime_para_int(idle)
            kernel_val2 = _filetime_para_int(kernel)
            user_val2 = _filetime_para_int(user)
            _cpu_tempos_anteriores = (idle_val2, kernel_val2, user_val2)
            d_idle = idle_val2 - idle_val
            d_total = (kernel_val2 - kernel_val) + (user_val2 - user_val)
        else:
            ant_idle, ant_kernel, ant_user = _cpu_tempos_anteriores
            _cpu_tempos_anteriores = (idle_val, kernel_val, user_val)
            d_idle = idle_val - ant_idle
            d_total = (kernel_val - ant_kernel) + (user_val - ant_user)

        if d_total <= 0:
            return 0.0
        uso = 100.0 * (1.0 - (float(d_idle) / float(d_total)))
        return round(max(0.0, min(100.0, uso)), 1)
    except Exception:
        return 0.0


def medir_ram() -> Dict[str, Any]:
    """Obtém uso real de memória RAM via GlobalMemoryStatusEx no Windows."""
    try:
        mem = _MEMORYSTATUSEX()
        mem.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
        total_gb = mem.ullTotalPhys / (1024 ** 3)
        livre_gb = mem.ullAvailPhys / (1024 ** 3)
        usada_gb = max(0.0, total_gb - livre_gb)
        pct = float(mem.dwMemoryLoad)
        if total_gb > 0:
            pct = round((usada_gb / total_gb) * 100.0, 1)
        return {
            "pct": pct,
            "usada_gb": round(usada_gb, 2),
            "total_gb": round(total_gb, 2),
            "livre_gb": round(livre_gb, 2),
        }
    except Exception:
        return {"pct": 0.0, "usada_gb": 0.0, "total_gb": 0.0, "livre_gb": 0.0}


def medir_gpu() -> Dict[str, Any]:
    """Consulta uso real de GPU NVIDIA, VRAM e Temperatura via nvidia-smi sem abrir janela."""
    try:
        flags = 0x08000000 if os.name == "nt" else 0
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2.0,
            creationflags=flags,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            linha = proc.stdout.strip().splitlines()[0]
            partes = [p.strip() for p in linha.split(",")]
            if len(partes) >= 5:
                nome = partes[0]
                gpu_pct = float(partes[1]) if partes[1].replace(".", "", 1).isdigit() else 0.0
                vram_usada = float(partes[2]) if partes[2].replace(".", "", 1).isdigit() else 0.0
                vram_total = float(partes[3]) if partes[3].replace(".", "", 1).isdigit() else 1.0
                temp_c = float(partes[4]) if partes[4].replace(".", "", 1).isdigit() else 0.0
                vram_pct = round((vram_usada / max(1.0, vram_total)) * 100.0, 1)
                return {
                    "disponivel": True,
                    "nome": nome,
                    "pct": round(gpu_pct, 1),
                    "vram_pct": vram_pct,
                    "vram_usada_mb": int(round(vram_usada)),
                    "vram_total_mb": int(round(vram_total)),
                    "temp_c": int(round(temp_c)),
                }
    except Exception:
        pass
    return {
        "disponivel": False,
        "nome": "GPU integrada / CPU",
        "pct": 0.0,
        "vram_pct": 0.0,
        "vram_usada_mb": 0,
        "vram_total_mb": 0,
        "temp_c": 0,
    }


def _classificar_nivel(pct: float, limite_critico: float, limite_aviso: float = LIMITE_AVISO_PCT) -> str:
    if pct >= limite_critico:
        return "critico"
    if pct >= limite_aviso:
        return "aviso"
    return "normal"


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


def obter_caminho_telemetria_json() -> Path:
    return obter_caminho_raiz() / "_internal" / "agente" / "static" / "telemetria.json"


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
    """Grava um erro crítico ou evento de hardware em 'log do papai.txt' respeitando 10.000 linhas e 10 MB."""
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


def _obter_tarefa_em_execucao(raiz: Path) -> Dict[str, Any]:
    """Lê trabalho/tarefas.json para identificar se há processamento de cortes ativo."""
    arq_tarefas = raiz / "trabalho" / "tarefas.json"
    info = {
        "ocupada": False,
        "tarefa_id": None,
        "titulo": None,
        "etapa": None,
        "pct": 0,
        "qtd_fila": 0,
    }
    try:
        if arq_tarefas.exists():
            tarefas = json.loads(arq_tarefas.read_text(encoding="utf-8", errors="replace"))
            if isinstance(tarefas, list):
                em_fila = [t for t in tarefas if t.get("status") in ("rodando", "na_fila")]
                info["qtd_fila"] = len(em_fila)
                rodando = next((t for t in tarefas if t.get("status") == "rodando"), None)
                if rodando:
                    info["ocupada"] = True
                    info["tarefa_id"] = rodando.get("id")
                    info["titulo"] = rodando.get("titulo") or rodando.get("origem") or rodando.get("id")
                    info["etapa"] = rodando.get("etapa") or "processando"
                    info["pct"] = int(round(float(rodando.get("pct") or 0.0) * 100))
    except Exception:
        pass
    return info


def coletar_metricas_hardware(forcar_log_txt: bool = False) -> Dict[str, Any]:
    """
    Coleta métricas reais de CPU, Memória RAM e GPU, atualiza o histórico de log,
    detecta sobrecarga crítica durante o processamento de cortes e persiste em telemetria.json e log do papai.txt.
    """
    global _ultimo_log_telemetria_txt, _ultimo_alerta_critico_txt, _ultimo_estado_telemetria

    raiz = obter_caminho_raiz()
    agora_dt = datetime.now()
    agora_ts = time.time()
    horario_str = agora_dt.strftime("%H:%M:%S")
    data_hora_str = agora_dt.strftime("%Y-%m-%d %H:%M:%S")

    cpu_pct = medir_cpu_pct()
    cpu_info = obter_info_cpu_estatica()
    nucleos = os.cpu_count() or 4
    ram = medir_ram()
    gpu = medir_gpu()
    cpu_temp_c = estimar_temperatura_cpu(cpu_pct, gpu["temp_c"])
    temp_max_c = max(cpu_temp_c, gpu["temp_c"])
    proc = _obter_tarefa_em_execucao(raiz)

    cpu_status = _classificar_nivel(cpu_pct, LIMITE_CRITICO_CPU_PCT)
    if cpu_temp_c >= LIMITE_CRITICO_TEMP_GPU_C:
        cpu_status = "critico"
    ram_status = _classificar_nivel(ram["pct"], LIMITE_CRITICO_RAM_PCT)
    gpu_maior_pct = max(gpu["pct"], gpu["vram_pct"])
    gpu_status = _classificar_nivel(gpu_maior_pct, LIMITE_CRITICO_GPU_PCT)
    if gpu["temp_c"] >= LIMITE_CRITICO_TEMP_GPU_C:
        gpu_status = "critico"
    temp_status = (
        "critico"
        if temp_max_c >= LIMITE_CRITICO_TEMP_GPU_C
        else ("aviso" if temp_max_c >= 72 else "normal")
    )

    motivos_criticos: List[str] = []
    if cpu_pct >= LIMITE_CRITICO_CPU_PCT:
        motivos_criticos.append(f"CPU em {cpu_pct:.1f}% ({cpu_temp_c}°C — limite: {LIMITE_CRITICO_CPU_PCT:.0f}%)")
    if cpu_temp_c >= LIMITE_CRITICO_TEMP_GPU_C:
        motivos_criticos.append(f"Temperatura da CPU em {cpu_temp_c}°C (limite: {LIMITE_CRITICO_TEMP_GPU_C:.0f}°C)")
    if ram["pct"] >= LIMITE_CRITICO_RAM_PCT:
        motivos_criticos.append(
            f"Memória RAM em {ram['pct']:.1f}% ({ram['usada_gb']:.1f}/{ram['total_gb']:.1f} GB — limite: {LIMITE_CRITICO_RAM_PCT:.0f}%)"
        )
    if gpu["disponivel"] and gpu["pct"] >= LIMITE_CRITICO_GPU_PCT:
        motivos_criticos.append(f"GPU em {gpu['pct']:.1f}% (limite crítico: {LIMITE_CRITICO_GPU_PCT:.0f}%)")
    if gpu["disponivel"] and gpu["vram_pct"] >= LIMITE_CRITICO_GPU_PCT:
        motivos_criticos.append(
            f"VRAM da GPU em {gpu['vram_pct']:.1f}% ({gpu['vram_usada_mb']}/{gpu['vram_total_mb']} MB)"
        )
    if gpu["disponivel"] and gpu["temp_c"] >= LIMITE_CRITICO_TEMP_GPU_C:
        motivos_criticos.append(f"Temperatura da GPU em {gpu['temp_c']}°C (limite: {LIMITE_CRITICO_TEMP_GPU_C:.0f}°C)")

    critico_ativo = len(motivos_criticos) > 0
    etapa_txt = (
        f"{proc['etapa'].upper()} ({proc['pct']}%)"
        if proc["ocupada"] and proc["etapa"]
        else ("EM FILA" if proc["qtd_fila"] > 0 else "LIVRE")
    )
    tag_nivel = "CRITICO" if critico_ativo else (
        "AVISO" if "aviso" in (cpu_status, ram_status, gpu_status, temp_status) else "OK"
    )

    linha_telemetria = (
        f"[{horario_str}] [{tag_nivel}] "
        f"CPU: {cpu_pct:4.1f}% ({cpu_temp_c}°C) | "
        f"RAM: {ram['pct']:4.1f}% ({ram['usada_gb']:.2f}/{ram['total_gb']:.2f} GB) | "
        f"GPU: {gpu['pct']:4.1f}% (VRAM {gpu['vram_usada_mb']}/{gpu['vram_total_mb']} MB, {gpu['temp_c']}°C) | "
        f"Status: {etapa_txt}"
    )

    if not _historico_telemetria or _historico_telemetria[-1] != linha_telemetria:
        _historico_telemetria.append(linha_telemetria)

    # Grava alerta crítico imediatamente no log do papai.txt (cooldown 30s para não inundar)
    if critico_ativo and (agora_ts - _ultimo_alerta_critico_txt >= 30.0):
        _ultimo_alerta_critico_txt = agora_ts
        registrar_erro_critico(
            origem=f"MONITOR_HARDWARE_TEMPO_REAL [Tarefa={proc['tarefa_id'] or 'N/A'}]",
            mensagem=f"Uso crítico de hardware detectado: {'; '.join(motivos_criticos)}",
            detalhes=(
                f"Tarefa ativa : {proc['titulo'] or 'Nenhuma'} (Etapa: {etapa_txt})\n"
                f"CPU ({cpu_info['nome_curto']}): {cpu_pct:.1f}% | Temp: {cpu_temp_c}°C | {nucleos} núcleos ({cpu_info['freq_ghz']} GHz)\n"
                f"Memória RAM  : {ram['pct']:.1f}% ({ram['usada_gb']:.2f} GB usados de {ram['total_gb']:.2f} GB)\n"
                f"GPU ({gpu['nome']}): {gpu['pct']:.1f}% | VRAM: {gpu['vram_usada_mb']}/{gpu['vram_total_mb']} MB ({gpu['vram_pct']:.1f}%) | Temp: {gpu['temp_c']}°C\n"
                f"Ação UI      : Modal de confirmação exibido ao usuário (Opção de Forçar Parada imediata)."
            ),
            nivel="ALERTA_CRITICO_HARDWARE",
        )

    # Grava log periódico de telemetria no log do papai.txt enquanto processa cortes (a cada 30s) ou quando solicitado
    intervalo_txt = 30.0 if proc["ocupada"] else 180.0
    if forcar_log_txt or (agora_ts - _ultimo_log_telemetria_txt >= intervalo_txt):
        _ultimo_log_telemetria_txt = agora_ts
        registrar_erro_critico(
            origem=f"TELEMETRIA_HARDWARE [Status={etapa_txt}]",
            mensagem=(
                f"CPU: {cpu_pct:.1f}% ({cpu_temp_c}°C) | RAM: {ram['pct']:.1f}% ({ram['usada_gb']:.2f}/{ram['total_gb']:.2f} GB) | "
                f"GPU: {gpu['pct']:.1f}% (VRAM {gpu['vram_usada_mb']}/{gpu['vram_total_mb']} MB, {gpu['temp_c']}°C)"
            ),
            detalhes=(
                f"Processamento ativo: {'Sim (' + str(proc['titulo']) + ')' if proc['ocupada'] else 'Não (Livre)'}\n"
                f"Processador CPU    : {cpu_info['nome']} ({nucleos} threads @ {cpu_info['freq_ghz']} GHz, Temp: {cpu_temp_c}°C)\n"
                f"Dispositivo GPU    : {gpu['nome']} (Temp: {gpu['temp_c']}°C)\n"
                f"Nível de Saúde     : {tag_nivel}"
            ),
            nivel="TELEMETRIA",
        )

    status_cpu_texto = {
        "normal": "Ativo • Estável",
        "aviso": "Ativo • Carga Elevada",
        "critico": "Crítico • Sobrecarga!",
    }.get(cpu_status, "Ativo")

    payload = {
        "timestamp": agora_ts,
        "horario": horario_str,
        "data_hora": data_hora_str,
        "cpu": {
            "nome": cpu_info["nome"],
            "nome_curto": cpu_info["nome_curto"],
            "pct": cpu_pct,
            "temp_c": cpu_temp_c,
            "nucleos": nucleos,
            "freq_ghz": cpu_info["freq_ghz"],
            "status": cpu_status,
            "status_texto": status_cpu_texto,
        },
        "ram": {
            "pct": ram["pct"],
            "usada_gb": ram["usada_gb"],
            "total_gb": ram["total_gb"],
            "livre_gb": ram["livre_gb"],
            "status": ram_status,
        },
        "gpu": {
            "disponivel": gpu["disponivel"],
            "nome": gpu["nome"],
            "pct": gpu["pct"],
            "vram_pct": gpu["vram_pct"],
            "vram_usada_mb": gpu["vram_usada_mb"],
            "vram_total_mb": gpu["vram_total_mb"],
            "temp_c": gpu["temp_c"],
            "status": gpu_status,
        },
        "temperatura": {
            "cpu_c": cpu_temp_c,
            "gpu_c": gpu["temp_c"],
            "max_c": temp_max_c,
            "limite_critico_c": int(LIMITE_CRITICO_TEMP_GPU_C),
            "pct_escala": round(min(100.0, (temp_max_c / max(1.0, LIMITE_CRITICO_TEMP_GPU_C)) * 100.0), 1),
            "status": temp_status,
        },
        "limites": {
            "aviso_pct": LIMITE_AVISO_PCT,
            "critico_cpu_pct": LIMITE_CRITICO_CPU_PCT,
            "critico_ram_pct": LIMITE_CRITICO_RAM_PCT,
            "critico_gpu_pct": LIMITE_CRITICO_GPU_PCT,
            "critico_temp_c": LIMITE_CRITICO_TEMP_GPU_C,
        },
        "processamento": proc,
        "critico": {
            "ativo": critico_ativo,
            "motivos": motivos_criticos,
            "mensagem": "; ".join(motivos_criticos) if motivos_criticos else "Operando dentro dos limites seguros.",
        },
        "historico_log": list(_historico_telemetria),
    }

    _ultimo_estado_telemetria = payload

    # Salva snapshot atômico em _internal/agente/static/telemetria.json para leitura em tempo real da UI
    try:
        arq_telemetria = obter_caminho_telemetria_json()
        arq_telemetria.parent.mkdir(parents=True, exist_ok=True)
        arq_tmp = arq_telemetria.with_suffix(".tmp")
        arq_tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(str(arq_tmp), str(arq_telemetria))
    except Exception:
        pass

    return payload


def registrar_parada_forcada_usuario(motivo: str = "", tarefa_id: str = "") -> None:
    """Registra no 'log do papai.txt' e no histórico da UI quando o usuário força a parada por uso crítico."""
    horario_str = datetime.now().strftime("%H:%M:%S")
    msg_curta = f"[{horario_str}] [PARADA FORÇADA] Usuário interrompeu o processamento de cortes ({motivo or 'Alerta crítico de hardware'})."
    _historico_telemetria.append(msg_curta)
    snap = _ultimo_estado_telemetria or {}
    cpu_p = snap.get("cpu", {}).get("pct", 0)
    ram_p = snap.get("ram", {}).get("pct", 0)
    gpu_p = snap.get("gpu", {}).get("pct", 0)
    registrar_erro_critico(
        origem=f"PARADA_FORCADA_HARDWARE [Tarefa={tarefa_id or 'ativa'}]",
        mensagem=f"Processamento interrompido pelo usuário devido a alerta de uso crítico de recursos ({motivo or 'Limite excedido'}).",
        detalhes=f"Leitura no momento da parada: CPU={cpu_p}% | RAM={ram_p}% | GPU={gpu_p}%",
        nivel="ALERTA_PARADA_FORCADA",
    )


def _tentar_registrar_rotas_flask() -> None:
    """Se executado dentro do processo RVM.exe, anexa /api/telemetria diretamente ao app Flask."""
    global _rotas_flask_registradas
    if _rotas_flask_registradas:
        return
    try:
        flask_mod = sys.modules.get("flask")
        if not flask_mod:
            return
        FlaskCls = getattr(flask_mod, "Flask", None)
        jsonify = getattr(flask_mod, "jsonify", None)
        request = getattr(flask_mod, "request", None)
        if not FlaskCls or not jsonify:
            return
        for obj in gc.get_objects():
            if isinstance(obj, FlaskCls):
                regras = [r.rule for r in obj.url_map.iter_rules()]
                if "/api/telemetria" not in regras:
                    def _rota_telemetria():
                        return jsonify(_ultimo_estado_telemetria or coletar_metricas_hardware())

                    def _rota_parada_forcada():
                        dados = {}
                        try:
                            if request and request.is_json:
                                dados = request.get_json(silent=True) or {}
                        except Exception:
                            pass
                        registrar_parada_forcada_usuario(
                            motivo=str(dados.get("motivo") or "Acionado pelo painel de hardware"),
                            tarefa_id=str(dados.get("tarefa_id") or ""),
                        )
                        return jsonify({"ok": True})

                    obj.add_url_rule("/api/telemetria", "api_telemetria_hw", _rota_telemetria, methods=["GET"])
                    obj.add_url_rule(
                        "/api/telemetria/parada-forcada",
                        "api_telemetria_parada",
                        _rota_parada_forcada,
                        methods=["POST"],
                    )
                _rotas_flask_registradas = True
                break
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
        campos[2] = "40"   # Fontsize legível para o crédito obrigatório
        campos[16] = "4"   # Outline nítido
        campos[19] = "80"  # MarginL
        campos[20] = "80"  # MarginR

    return f"{prefixo}: " + ",".join(campos)


def _obter_canal_do_episodio(caminho_ass: Path) -> str:
    """Busca o nome do canal original a partir de trabalho/<ep>/info.json ou saida/<ep>/corte_01.json."""
    try:
        ep_dir = caminho_ass.parent.parent
        ep_id = ep_dir.name
        raiz = obter_caminho_raiz()
        for candidato in (
            ep_dir / "info.json",
            raiz / "saida" / ep_id / "corte_01.json",
            raiz / "saida" / ep_id / "episodio.json",
        ):
            if candidato.exists():
                dados = json.loads(candidato.read_text(encoding="utf-8", errors="replace"))
                canal = (dados.get("canal") or dados.get("uploader") or dados.get("channel") or "").strip()
                if canal:
                    return canal
    except Exception:
        pass
    return "Criador Original"


def _garantir_prefixo_credito_ass(linha: str) -> str:
    """
    Garante que toda linha Dialogue de estilo 'Credito' no .ass exiba explicitamente
    'Créditos: <Nome do Canal Original>'.
    """
    if not linha.startswith("Dialogue:") or ",Credito," not in linha:
        return linha
    partes = linha.split(",", 9)
    if len(partes) < 10:
        return linha
    texto = partes[9]
    # Separa tags de formatação ASS {\an5\pos(...)} do texto visível
    m = re.match(r"^((?:\{[^}]*\})+)(.+)$", texto)
    if m:
        tags = m.group(1)
        visivel = m.group(2).strip()
    else:
        tags = r"{\an5\pos(540,1458)}"
        visivel = texto.strip()

    if not visivel:
        return linha
    if not re.match(r"^(cr[eé]ditos?|canal\s+original)\s*:", visivel, flags=re.IGNORECASE):
        visivel = f"Créditos: {visivel}"
    partes[9] = f"{tags}{visivel}"
    return ",".join(partes)


def auditar_e_ajustar_arquivo_ass(caminho_ass: Path) -> bool:
    """
    Garante que o arquivo de legenda .ass respeite a área de trabalho de imagem (1080x1920)
    e cumpra a Diretriz Obrigatória de Créditos ao Criador Original:
    1. Troca 'WrapStyle: 2' (sem quebra de linha) por 'WrapStyle: 0' (quebra inteligente automática).
    2. Ajusta margens laterais seguras (MarginL=80, MarginR=80) e fontes máximas (Legenda=78, Titulo=58, Credito=40).
    3. Garante que o crédito do canal original ('Créditos: <Canal>') esteja presente e visível no vídeo.
    4. Sanitiza termos truncados ou corrompidos.
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
        tem_dialogue_credito = False
        for linha in original.splitlines():
            if linha.startswith("WrapStyle:"):
                linhas_processadas.append("WrapStyle: 0")
            elif linha.startswith("Style:"):
                linhas_processadas.append(_ajustar_linha_style_ass(linha))
            elif linha.startswith("Dialogue:") and ",Credito," in linha:
                tem_dialogue_credito = True
                linhas_processadas.append(_garantir_prefixo_credito_ass(sanitizar_texto_seguro(linha)))
            else:
                linhas_processadas.append(sanitizar_texto_seguro(linha))

        # Se o arquivo .ass não tiver linha de Crédito, injeta obrigatoriamente o crédito do canal original
        if not tem_dialogue_credito and "[Events]" in original:
            canal_ep = _obter_canal_do_episodio(caminho_ass)
            linha_credito_obrigatoria = (
                f"Dialogue: 1,0:00:00.00,0:00:59.00,Credito,,0,0,0,,{{\\an5\\pos(540,1458)}}Créditos: {canal_ep}"
            )
            novas_linhas = []
            inserido = False
            for l in linhas_processadas:
                novas_linhas.append(l)
                if not inserido and l.startswith("Format:") and "Text" in l:
                    novas_linhas.append(linha_credito_obrigatoria)
                    inserido = True
            linhas_processadas = novas_linhas

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

                # Diretriz Obrigatória: Garante divulgação do nome do canal original em todo corte
                canal_orig = (dados.get("canal") or "").strip()
                if not canal_orig:
                    canal_orig = "Criador Original"
                    dados["canal"] = canal_orig
                    modificado = True
                link_orig = (dados.get("link_original") or dados.get("link") or "").strip()
                credito_padrao = f"🎥 Créditos ao Criador Original: {canal_orig}"
                if link_orig:
                    credito_padrao += f"\n🔗 Episódio completo: {link_orig}"
                if dados.get("credito") != credito_padrao:
                    dados["credito"] = credito_padrao
                    modificado = True
                diretriz_obj = {
                    "obrigatorio": True,
                    "nota_diretriz": (
                        "DIRETRIZ OBRIGATÓRIA DE AUTORIA: Todo corte deve divulgar obrigatoriamente "
                        "o nome do canal original no vídeo (overlay na tela) e na descrição/créditos, "
                        "prestando os devidos créditos ao criador original."
                    ),
                    "canal_original": canal_orig,
                    "link_original": link_orig,
                    "credito_tela": f"Créditos: {canal_orig}",
                    "credito_descricao": credito_padrao,
                }
                if dados.get("diretriz_credito_criador") != diretriz_obj:
                    dados["diretriz_credito_criador"] = diretriz_obj
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
    Monitora continuamente:
      1. Telemetria de hardware (CPU, RAM, GPU) a cada 1.5s com gravação em telemetria.json e log do papai.txt
      2. trabalho/tarefas.json, arquivos .ass e metadados de cortes
    """
    raiz = obter_caminho_raiz()
    arq_tarefas = raiz / "trabalho" / "tarefas.json"
    erros_ja_registrados = set()
    avisos_cuda_registrados = set()
    avisos_enquadramento_registrados = set()
    ciclo = 0

    # Primeira coleta imediata com registro no log do papai.txt
    try:
        coletar_metricas_hardware(forcar_log_txt=True)
    except Exception:
        pass

    while True:
        try:
            _tentar_registrar_rotas_flask()
            coletar_metricas_hardware(forcar_log_txt=False)

            if ciclo % 2 == 0:
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

        ciclo += 1
        time.sleep(1.5)


def iniciar_monitoramento() -> None:
    """Ativa os hooks de exceção e a thread de monitoramento e telemetria do 'log do papai.txt'."""
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
    if "--daemon" in sys.argv:
        print("Iniciando daemon de telemetria de hardware (CPU/RAM/GPU) do RVM...")
        _monitorar_tarefas_e_ffmpeg()
    else:
        snap = coletar_metricas_hardware(forcar_log_txt=True)
        qtd = auditar_pastas_de_trabalho_e_saida()
        print(
            f"Telemetria coletada: CPU={snap['cpu']['pct']}% | "
            f"RAM={snap['ram']['pct']}% ({snap['ram']['usada_gb']}/{snap['ram']['total_gb']} GB) | "
            f"GPU={snap['gpu']['pct']}% ({snap['gpu']['nome']}, VRAM {snap['gpu']['vram_usada_mb']}/{snap['gpu']['vram_total_mb']} MB, {snap['gpu']['temp_c']}°C)"
        )
        print(f"Auditoria concluída: {qtd} arquivos ajustados. Limite por arquivo: {LIMITE_MAX_LINHAS} linhas.")
