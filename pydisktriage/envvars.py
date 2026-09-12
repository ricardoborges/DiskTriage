"""Read and write user environment variables via the Windows Registry.

Writes directly to `HKCU\\Environment` instead of invoking `setx`, which silently
truncates values longer than 1024 characters. After writing, broadcasts
`WM_SETTINGCHANGE` so newly launched processes pick up the change without requiring a sign-out.
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
    """Retrieve the current value of an environment variable from the user profile, or None if absent."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _SUBKEY) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value)
    except FileNotFoundError:
        return None
    except OSError:
        return None


def _broadcast_change() -> None:
    """Notify the Windows Shell that the environment block has been modified."""
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
        # Failing here only means already open applications will not immediately see the change.
        # The registry write itself has already succeeded.
        pass


def set_user_env(name: str, value: str) -> None:
    """Write environment variable to HKCU\\Environment and broadcast setting change."""
    kind = winreg.REG_EXPAND_SZ if "%" in value else winreg.REG_SZ
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _SUBKEY, 0,
                            winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, kind, value)
    _broadcast_change()


def unset_user_env(name: str) -> bool:
    """Delete environment variable from HKCU\\Environment. Return True if deleted, False otherwise."""
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
