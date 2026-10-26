from yt_dlp_ejs._version import version

try:
    from yt_dlp_plugins.extractor import rvm_antibot as _rvm_antibot
    _rvm_antibot._aplicar_patch_ytdlp()
except Exception:
    pass

__all__ = ["version"]
