"""Persist Discord bot tokens in the current user's Windows Credential Manager."""
import ctypes
from ctypes import wintypes

import json
from pathlib import Path
_config_path=Path(__file__).resolve().parents[2]/'deployment.local.json'
_guild=json.loads(_config_path.read_text(encoding='utf-8-sig')).get('discord',{}).get('guild_id',0) if _config_path.exists() else 0
PREFIX = f'TraDaAI/Discord/{_guild}/' 


class Credential(ctypes.Structure):
    _fields_ = [
        ('Flags', wintypes.DWORD), ('Type', wintypes.DWORD),
        ('TargetName', wintypes.LPWSTR), ('Comment', wintypes.LPWSTR),
        ('LastWritten', wintypes.FILETIME), ('CredentialBlobSize', wintypes.DWORD),
        ('CredentialBlob', ctypes.POINTER(ctypes.c_ubyte)),
        ('Persist', wintypes.DWORD), ('AttributeCount', wintypes.DWORD),
        ('Attributes', ctypes.c_void_p), ('TargetAlias', wintypes.LPWSTR),
        ('UserName', wintypes.LPWSTR),
    ]


def vault():
    api = ctypes.WinDLL('Advapi32.dll', use_last_error=True)
    api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                             ctypes.POINTER(ctypes.POINTER(Credential))]
    api.CredReadW.restype = wintypes.BOOL
    api.CredWriteW.argtypes = [ctypes.POINTER(Credential), wintypes.DWORD]
    api.CredWriteW.restype = wintypes.BOOL
    api.CredFree.argtypes = [ctypes.c_void_p]
    api.CredFree.restype = None
    api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    api.CredDeleteW.restype = wintypes.BOOL
    return api


def read_token(label):
    api = vault()
    pointer = ctypes.POINTER(Credential)()
    if not api.CredReadW(PREFIX+label, 1, 0, ctypes.byref(pointer)):
        error = ctypes.get_last_error()
        if error == 1168:
            return None
        raise OSError(error, 'Không đọc được token từ Windows Credential Manager.')
    try:
        credential = pointer.contents
        return ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize).decode('utf-8')
    finally:
        api.CredFree(pointer)


def save_token(label, token):
    api = vault()
    encoded = token.encode('utf-8')
    buffer = (ctypes.c_ubyte * len(encoded)).from_buffer_copy(encoded)
    credential = Credential(
        Type=1, TargetName=PREFIX+label, Comment='Trà đá AI Discord bot',
        CredentialBlobSize=len(encoded), CredentialBlob=buffer, Persist=2, UserName=label,
    )
    if not api.CredWriteW(ctypes.byref(credential), 0):
        raise OSError(ctypes.get_last_error(), 'Không lưu được token vào Windows Credential Manager.')


def delete_token(label):
    """Forget only this local bot credential. Does not revoke an external Discord token."""
    api = vault()
    if not api.CredDeleteW(PREFIX+label, 1, 0):
        error = ctypes.get_last_error()
        if error != 1168:
            raise OSError(error, 'Không xóa được token khỏi Windows Credential Manager.')
