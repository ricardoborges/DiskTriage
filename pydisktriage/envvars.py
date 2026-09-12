"""Leitura e escrita de variáveis de ambiente do usuário.

Escreve direto em `HKCU\\Environment` em vez de chamar `setx`, que trunca
silenciosamente qualquer valor acima de 1024 caracteres. Depois de gravar,
transmite `WM_SETTINGCHANGE` para que processos novos enxerguem a mudança sem
precisar de logoff.
"""

from __future__ import annotations

import ctypes
import winreg
from ctypes import wintypes

HWND_BROADCAST = 0xFFFF
WM_SETTINGCHANGE = 0x001A
SMTO_ABORTIFHUNG = 0x0002

_SUBKEY = "Environment"


def get_user_env(name: str) -> str | None:
    """Valor atual da variável no perfil do usuário, ou None se não existir."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _SUBKEY) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value)
    except FileNotFoundError:
        return None
    except OSError:
        return None


def _broadcast_change() -> None:
    """Avisa o shell de que o bloco de ambiente mudou."""
    try:
        send = ctypes.windll.user32.SendMessageTimeoutW
        send.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
            wintypes.LPCWSTR, wintypes.UINT, wintypes.UINT,
            ctypes.POINTER(wintypes.DWORD),
        ]
        result = wintypes.DWORD()
        send(HWND_BROADCAST, WM_SETTINGCHANGE, 0, _SUBKEY,
             SMTO_ABORTIFHUNG, 5000, ctypes.byref(result))
    except Exception:
        # Falhar aqui só significa que apps já abertos não veem a mudança na
        # hora. A gravação no registro, que é o que importa, já aconteceu.
        pass


def set_user_env(name: str, value: str) -> None:
    """Grava a variável no perfil do usuário e notifica o sistema."""
    kind = winreg.REG_EXPAND_SZ if "%" in value else winreg.REG_SZ
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _SUBKEY, 0,
                            winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, kind, value)
    _broadcast_change()


def unset_user_env(name: str) -> bool:
    """Remove a variável. True se ela existia."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _SUBKEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)
    except FileNotFoundError:
        return False
    except OSError:
        return False
    _broadcast_change()
    return True
