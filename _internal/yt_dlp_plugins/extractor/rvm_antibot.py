# -*- coding: utf-8 -*-
"""
Plugin Anti-Bot do RVM para yt-dlp (carregado automaticamente por YoutubeDL).
- Remove códigos ANSI de cores (evita '\x1b[0;31mERROR:\x1b[0m' na interface).
- Detecta automaticamente 'cookies.txt' na raiz do RVM ou configurações em 'config.yaml'.
- Realiza fallback automático entre clientes do YouTube (tv_embedded, android_vr, ios, mweb)
  e cookies do navegador caso o YouTube exiba 'Sign in to confirm you're not a bot'.
"""

import os
import re
from pathlib import Path
import yt_dlp

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_RAIZ_RVM = Path(r"c:\Users\Renan\Desktop\Teste\RVM")


def _limpar_ansi(texto: str) -> str:
    if not texto:
        return ""
    return _ANSI_RE.sub("", str(texto)).strip()


def _ler_config_youtube() -> dict:
    cfg_path = _RAIZ_RVM / "config.yaml"
    if not cfg_path.exists():
        return {}
    try:
        import yaml
        dados = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        return dados.get("youtube", {}) if isinstance(dados, dict) else {}
    except Exception:
        return {}


def _aplicar_patch_ytdlp():
    ydl_cls = yt_dlp.YoutubeDL
    if getattr(ydl_cls, "_rvm_antibot_patched", False):
        return

    orig_init = ydl_cls.__init__
    orig_extract_info = ydl_cls.extract_info

    def _novo_init(self, params=None, auto_init=True):
        params = dict(params or {})
        # Desativa códigos ANSI de terminal para nunca poluir a UI do RVM
        params["no_color"] = True
        params["color"] = "no_color"

        yt_cfg = _ler_config_youtube()

        # 1. Se existir cookies.txt na raiz do RVM (ou definido no config.yaml), aplica automaticamente
        arq_cookies = yt_cfg.get("cookies_arquivo") or "cookies.txt"
        caminho_cookies = Path(arq_cookies)
        if not caminho_cookies.is_absolute():
            caminho_cookies = _RAIZ_RVM / caminho_cookies
        if caminho_cookies.exists() and caminho_cookies.stat().st_size > 30:
            params.setdefault("cookiefile", str(caminho_cookies))

        # 2. Se o usuário configurou cookies_navegador no config.yaml (ex: firefox, edge, chrome, brave)
        nav = (yt_cfg.get("cookies_navegador") or "").strip().lower()
        if nav and nav not in ("nenhum", "false", "off", "0") and "cookiefile" not in params:
            params.setdefault("cookiesfrombrowser", (nav,))

        # 3. Clientes de player resilientes contra bloqueio de bot
        clientes_cfg = yt_cfg.get("player_clients")
        if clientes_cfg and isinstance(clientes_cfg, list):
            ext_args = dict(params.get("extractor_args") or {})
            yt_args = dict(ext_args.get("youtube") or {})
            yt_args.setdefault("player_client", clientes_cfg)
            ext_args["youtube"] = yt_args
            params["extractor_args"] = ext_args

        orig_init(self, params=params, auto_init=auto_init)

    def _novo_extract_info(self, url, download=True, ie_key=None, extra_info=None, process=True, force_generic_extractor=False):
        try:
            return orig_extract_info(
                self, url, download=download, ie_key=ie_key,
                extra_info=extra_info, process=process,
                force_generic_extractor=force_generic_extractor
            )
        except Exception as exc:
            msg_limpa = _limpar_ansi(str(exc))
            eh_bloqueio_bot = (
                "Sign in to confirm" in msg_limpa
                or "not a bot" in msg_limpa
                or "--cookies-from-browser" in msg_limpa
            )
            if not eh_bloqueio_bot or getattr(self, "_rvm_em_fallback", False):
                raise yt_dlp.utils.DownloadError(_formatar_erro_amigavel(msg_limpa)) from None

            # Tenta estratégias automáticas de contorno antes de falhar
            estrategias = [
                (
                    "Clientes alternativos (tv_embedded / android_vr / ios / mweb)",
                    {
                        "extractor_args": {
                            "youtube": {
                                "player_client": ["tv_embedded", "android_vr", "ios", "mweb", "web_creator"]
                            }
                        }
                    },
                ),
            ]

            caminho_cookies = _RAIZ_RVM / "cookies.txt"
            if caminho_cookies.exists() and caminho_cookies.stat().st_size > 30:
                estrategias.insert(0, (
                    "Arquivo cookies.txt local",
                    {"cookiefile": str(caminho_cookies)},
                ))

            yt_cfg = _ler_config_youtube()
            nav_cfg = (yt_cfg.get("cookies_navegador") or "").strip().lower()
            navegadores_teste = [nav_cfg] if nav_cfg and nav_cfg not in ("nenhum", "false", "0") else ["firefox", "edge", "chrome", "brave"]
            for nav in navegadores_teste:
                estrategias.append((
                    f"Cookies do navegador ({nav})",
                    {"cookiesfrombrowser": (nav,)},
                ))

            for nome_est, extra_params in estrategias:
                try:
                    novos_params = dict(self.params or {})
                    novos_params["no_color"] = True
                    novos_params["color"] = "no_color"
                    novos_params.pop("cookiesfrombrowser", None)
                    novos_params.update(extra_params)
                    ydl_retry = ydl_cls(novos_params)
                    ydl_retry._rvm_em_fallback = True
                    return orig_extract_info(
                        ydl_retry, url, download=download, ie_key=ie_key,
                        extra_info=extra_info, process=process,
                        force_generic_extractor=force_generic_extractor
                    )
                except Exception:
                    continue

            raise yt_dlp.utils.DownloadError(_formatar_erro_amigavel(msg_limpa)) from None

    ydl_cls.__init__ = _novo_init
    ydl_cls.extract_info = _novo_extract_info
    ydl_cls._rvm_antibot_patched = True


def _formatar_erro_amigavel(msg_limpa: str) -> str:
    if "Sign in to confirm" in msg_limpa or "not a bot" in msg_limpa or "--cookies-from-browser" in msg_limpa:
        return (
            "Bloqueio Anti-Bot do YouTube detectado ('Sign in to confirm you’re not a bot'). "
            "O YouTube exigiu autenticação de conta para permitir o download deste vídeo. "
            "Soluções: (1) Salve seus cookies do YouTube no arquivo 'cookies.txt' na pasta do RVM; "
            "(2) Configure 'cookies_navegador' no config.yaml (ex: firefox, edge ou chrome); "
            "ou (3) Baixe o arquivo .mp4 e arraste para a tela do RVM. "
            f"[Detalhe original: {msg_limpa}]"
        )
    return msg_limpa


_aplicar_patch_ytdlp()
