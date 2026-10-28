"""
Windows Hello PRF for Signet.

Talks to webauthn.dll. The PIN stays inside Windows. This module returns
the PRF output and the caller drops it. Struct offsets were checked against
the Windows SDK 10.0.26100 header, then confirmed when Hello returned a
PRF secret on this PC. See LEARNINGS.md.
"""

from __future__ import annotations

import ctypes
import json
import os
from base64 import urlsafe_b64encode
from ctypes import (
    HRESULT,
    POINTER,
    Structure,
    WinDLL,
    byref,
    c_ubyte,
    c_void_p,
    sizeof,
    string_at,
)
from ctypes.wintypes import BOOL, DWORD, HWND, LONG, LPCWSTR

LOAD_LIBRARY_SEARCH_SYSTEM32 = 0x00000800
PBYTE = POINTER(c_ubyte)

RP_ID = "signet.pwm.local"
RP_NAME = "Signet"
TIMEOUT_MS = 180_000

# Sizes and offsets from cl.exe against webauthn.h. A unit test checks the
# ctypes copies still match, so a field added in the wrong place fails
# before any Hello prompt.
EXPECTED_SIZE = {
    "MakeOptions": 200,
    "GetOptions": 200,
    "Attestation": 192,
    "Assertion": 168,
    "HmacSalt": 32,
}
EXPECTED_OFFSET = {
    ("MakeOptions", "bEnablePrf"): 96,
    ("MakeOptions", "pPRFGlobalEval"): 128,
    ("GetOptions", "pHmacSecretSaltValues"): 104,
    ("Attestation", "pbCredentialId"): 88,
    ("Attestation", "bPrfEnabled"): 128,
    ("Attestation", "pHmacSecret"): 144,
    ("Assertion", "pHmacSecret"): 112,
}


class HelloError(Exception):
    """Windows Hello did not return a PRF output."""


class HelloCancelled(HelloError):
    """The user dismissed the Hello prompt."""


class HmacSalt(Structure):
    _fields_ = [
        ("cbFirst", DWORD),
        ("pbFirst", PBYTE),
        ("cbSecond", DWORD),
        ("pbSecond", PBYTE),
    ]


class CredWithHmacSalt(Structure):
    _fields_ = [
        ("cbCredID", DWORD),
        ("pbCredID", PBYTE),
        ("pHmacSecretSalt", POINTER(HmacSalt)),
    ]


class HmacSaltValues(Structure):
    _fields_ = [
        ("pGlobalHmacSalt", POINTER(HmacSalt)),
        ("cCredWithHmacSecretSaltList", DWORD),
        ("pCredWithHmacSecretSaltList", POINTER(CredWithHmacSalt)),
    ]


class Extension(Structure):
    _fields_ = [
        ("pwszExtensionIdentifier", LPCWSTR),
        ("cbExtension", DWORD),
        ("pvExtension", c_void_p),
    ]


class Extensions(Structure):
    _fields_ = [
        ("cExtensions", DWORD),
        ("pExtensions", POINTER(Extension)),
    ]


class Credential(Structure):
    _fields_ = [
        ("dwVersion", DWORD),
        ("cbId", DWORD),
        ("pbId", PBYTE),
        ("pwszCredentialType", LPCWSTR),
    ]


class Credentials(Structure):
    _fields_ = [
        ("cCredentials", DWORD),
        ("pCredentials", POINTER(Credential)),
    ]


class RpInfo(Structure):
    _fields_ = [
        ("dwVersion", DWORD),
        ("pwszId", LPCWSTR),
        ("pwszName", LPCWSTR),
        ("pwszIcon", LPCWSTR),
    ]


class UserInfo(Structure):
    _fields_ = [
        ("dwVersion", DWORD),
        ("cbId", DWORD),
        ("pbId", PBYTE),
        ("pwszName", LPCWSTR),
        ("pwszIcon", LPCWSTR),
        ("pwszDisplayName", LPCWSTR),
    ]


class ClientData(Structure):
    _fields_ = [
        ("dwVersion", DWORD),
        ("cbClientDataJSON", DWORD),
        ("pbClientDataJSON", PBYTE),
        ("pwszHashAlgId", LPCWSTR),
    ]


class CoseParam(Structure):
    _fields_ = [
        ("dwVersion", DWORD),
        ("pwszCredentialType", LPCWSTR),
        ("lAlg", LONG),
    ]


class CoseParams(Structure):
    _fields_ = [
        ("cCredentialParameters", DWORD),
        ("pCredentialParameters", POINTER(CoseParam)),
    ]


class MakeOptions(Structure):
    _fields_ = [
        ("dwVersion", DWORD),
        ("dwTimeoutMilliseconds", DWORD),
        ("CredentialList", Credentials),
        ("Extensions", Extensions),
        ("dwAuthenticatorAttachment", DWORD),
        ("bRequireResidentKey", BOOL),
        ("dwUserVerificationRequirement", DWORD),
        ("dwAttestationConveyancePreference", DWORD),
        ("dwFlags", DWORD),
        ("pCancellationId", c_void_p),
        ("pExcludeCredentialList", c_void_p),
        ("dwEnterpriseAttestation", DWORD),
        ("dwLargeBlobSupport", DWORD),
        ("bPreferResidentKey", BOOL),
        ("bBrowserInPrivateMode", BOOL),
        ("bEnablePrf", BOOL),
        ("pLinkedDevice", c_void_p),
        ("cbJsonExt", DWORD),
        ("pbJsonExt", PBYTE),
        ("pPRFGlobalEval", POINTER(HmacSalt)),
        ("cCredentialHints", DWORD),
        ("ppwszCredentialHints", c_void_p),
        ("bThirdPartyPayment", BOOL),
        ("pwszRemoteWebOrigin", LPCWSTR),
        ("cbPublicKeyCredentialCreationOptionsJSON", DWORD),
        ("pbPublicKeyCredentialCreationOptionsJSON", PBYTE),
        ("cbAuthenticatorId", DWORD),
        ("pbAuthenticatorId", PBYTE),
    ]


class GetOptions(Structure):
    _fields_ = [
        ("dwVersion", DWORD),
        ("dwTimeoutMilliseconds", DWORD),
        ("CredentialList", Credentials),
        ("Extensions", Extensions),
        ("dwAuthenticatorAttachment", DWORD),
        ("dwUserVerificationRequirement", DWORD),
        ("dwFlags", DWORD),
        ("pwszU2fAppId", LPCWSTR),
        ("pbU2fAppId", c_void_p),
        ("pCancellationId", c_void_p),
        ("pAllowCredentialList", c_void_p),
        ("dwCredLargeBlobOperation", DWORD),
        ("cbCredLargeBlob", DWORD),
        ("pbCredLargeBlob", PBYTE),
        ("pHmacSecretSaltValues", POINTER(HmacSaltValues)),
        ("bBrowserInPrivateMode", BOOL),
        ("pLinkedDevice", c_void_p),
        ("bAutoFill", BOOL),
        ("cbJsonExt", DWORD),
        ("pbJsonExt", PBYTE),
        ("cCredentialHints", DWORD),
        ("ppwszCredentialHints", c_void_p),
        ("pwszRemoteWebOrigin", LPCWSTR),
        ("cbPublicKeyCredentialRequestOptionsJSON", DWORD),
        ("pbPublicKeyCredentialRequestOptionsJSON", PBYTE),
        ("cbAuthenticatorId", DWORD),
        ("pbAuthenticatorId", PBYTE),
    ]


class Attestation(Structure):
    _fields_ = [
        ("dwVersion", DWORD),
        ("pwszFormatType", LPCWSTR),
        ("cbAuthenticatorData", DWORD),
        ("pbAuthenticatorData", PBYTE),
        ("cbAttestation", DWORD),
        ("pbAttestation", PBYTE),
        ("dwAttestationDecodeType", DWORD),
        ("pvAttestationDecode", c_void_p),
        ("cbAttestationObject", DWORD),
        ("pbAttestationObject", PBYTE),
        ("cbCredentialId", DWORD),
        ("pbCredentialId", PBYTE),
        ("Extensions", Extensions),
        ("dwUsedTransport", DWORD),
        ("bEpAtt", BOOL),
        ("bLargeBlobSupported", BOOL),
        ("bResidentKey", BOOL),
        ("bPrfEnabled", BOOL),
        ("cbUnsignedExtensionOutputs", DWORD),
        ("pbUnsignedExtensionOutputs", PBYTE),
        ("pHmacSecret", POINTER(HmacSalt)),
        ("bThirdPartyPayment", BOOL),
        ("dwTransports", DWORD),
        ("cbClientDataJSON", DWORD),
        ("pbClientDataJSON", PBYTE),
        ("cbRegistrationResponseJSON", DWORD),
        ("pbRegistrationResponseJSON", PBYTE),
    ]


class Assertion(Structure):
    _fields_ = [
        ("dwVersion", DWORD),
        ("cbAuthenticatorData", DWORD),
        ("pbAuthenticatorData", PBYTE),
        ("cbSignature", DWORD),
        ("pbSignature", PBYTE),
        ("Credential", Credential),
        ("cbUserId", DWORD),
        ("pbUserId", PBYTE),
        ("Extensions", Extensions),
        ("cbCredLargeBlob", DWORD),
        ("pbCredLargeBlob", PBYTE),
        ("dwCredLargeBlobStatus", DWORD),
        ("pHmacSecret", POINTER(HmacSalt)),
        ("dwUsedTransport", DWORD),
        ("cbUnsignedExtensionOutputs", DWORD),
        ("pbUnsignedExtensionOutputs", PBYTE),
        ("cbClientDataJSON", DWORD),
        ("pbClientDataJSON", PBYTE),
        ("cbAuthenticationResponseJSON", DWORD),
        ("pbAuthenticationResponseJSON", PBYTE),
    ]


_STRUCTS = {
    "MakeOptions": MakeOptions,
    "GetOptions": GetOptions,
    "Attestation": Attestation,
    "Assertion": Assertion,
    "HmacSalt": HmacSalt,
}


def assert_layout() -> None:
    """Raise AssertionError when the ctypes copies drift from webauthn.h."""
    for name, cls in _STRUCTS.items():
        actual = sizeof(cls)
        expected = EXPECTED_SIZE[name]
        if actual != expected:
            raise AssertionError(f"{name} size {actual}, expected {expected}")
    for (struct_name, field_name), offset in EXPECTED_OFFSET.items():
        actual = getattr(_STRUCTS[struct_name], field_name).offset
        if actual != offset:
            raise AssertionError(
                f"{struct_name}.{field_name} offset {actual}, expected {offset}"
            )


class _Keep:
    """Hold buffers the WebAuthn structs point at until the call returns."""

    def __init__(self) -> None:
        self._items: list[object] = []

    def text(self, value: str):
        buf = ctypes_unicode(value)
        self._items.append(buf)
        return ctypes_cast_text(buf)

    def bytes(self, value: bytes):
        buf = (c_ubyte * len(value)).from_buffer_copy(value)
        self._items.append(buf)
        return ctypes_cast_bytes(buf)

    def keep(self, obj):
        self._items.append(obj)
        return obj


def ctypes_unicode(value: str):
    return ctypes.create_unicode_buffer(value)


def ctypes_cast_text(buf):
    return ctypes.cast(buf, LPCWSTR)


def ctypes_cast_bytes(buf):
    return ctypes.cast(buf, PBYTE)


_DLL = None


def webauthn():
    """Load webauthn.dll from System32 once."""
    global _DLL
    if _DLL is not None:
        return _DLL
    assert_layout()
    dll = WinDLL("webauthn.dll", winmode=LOAD_LIBRARY_SEARCH_SYSTEM32)
    dll.WebAuthNGetApiVersionNumber.argtypes = []
    dll.WebAuthNGetApiVersionNumber.restype = DWORD
    dll.WebAuthNIsUserVerifyingPlatformAuthenticatorAvailable.argtypes = [POINTER(BOOL)]
    dll.WebAuthNIsUserVerifyingPlatformAuthenticatorAvailable.restype = HRESULT
    dll.WebAuthNAuthenticatorMakeCredential.argtypes = [
        HWND,
        POINTER(RpInfo),
        POINTER(UserInfo),
        POINTER(CoseParams),
        POINTER(ClientData),
        POINTER(MakeOptions),
        POINTER(POINTER(Attestation)),
    ]
    dll.WebAuthNAuthenticatorMakeCredential.restype = HRESULT
    dll.WebAuthNAuthenticatorGetAssertion.argtypes = [
        HWND,
        LPCWSTR,
        POINTER(ClientData),
        POINTER(GetOptions),
        POINTER(POINTER(Assertion)),
    ]
    dll.WebAuthNAuthenticatorGetAssertion.restype = HRESULT
    dll.WebAuthNFreeCredentialAttestation.argtypes = [POINTER(Attestation)]
    dll.WebAuthNFreeCredentialAttestation.restype = None
    dll.WebAuthNFreeAssertion.argtypes = [POINTER(Assertion)]
    dll.WebAuthNFreeAssertion.restype = None
    dll.WebAuthNGetErrorName.argtypes = [HRESULT]
    dll.WebAuthNGetErrorName.restype = LPCWSTR
    _DLL = dll
    return dll


def _hr_text(hr: int) -> str:
    code = ctypes.c_long(hr & 0xFFFFFFFF).value
    name = webauthn().WebAuthNGetErrorName(code) or "Unknown"
    return f"0x{hr & 0xFFFFFFFF:08X} {name}"


def _raise_for_hr(hr: int) -> None:
    if hr == 0:
        return
    text = _hr_text(hr)
    if "NotAllowedError" in text or "CANCEL" in text.upper():
        raise HelloCancelled(text)
    raise HelloError(text)


def _b64url(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _client_json(kind: str) -> bytes:
    payload = {
        "type": kind,
        "challenge": _b64url(os.urandom(32)),
        "origin": "https://signet.pwm.local",
        "crossOrigin": False,
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _read_buf(ptr, size: int) -> bytes:
    if not ptr or size <= 0:
        return b""
    return string_at(ptr, size)


def _read_first(ptr) -> bytes:
    if not ptr:
        return b""
    salt = ptr.contents
    return _read_buf(salt.pbFirst, salt.cbFirst)


def _client(keep: _Keep, kind: str) -> ClientData:
    raw = _client_json(kind)
    data = ClientData()
    data.dwVersion = 1
    data.cbClientDataJSON = len(raw)
    data.pbClientDataJSON = keep.bytes(raw)
    data.pwszHashAlgId = keep.text("SHA-256")
    return data


def _allow(keep: _Keep, cred_id: bytes) -> Credentials:
    cred = keep.keep(Credential())
    cred.dwVersion = 1
    cred.cbId = len(cred_id)
    cred.pbId = keep.bytes(cred_id)
    cred.pwszCredentialType = keep.text("public-key")
    creds = Credentials()
    creds.cCredentials = 1
    creds.pCredentials = ctypes_pointer(cred)
    return creds


def ctypes_pointer(obj):
    return ctypes.pointer(obj)


def platform_available() -> bool:
    flag = BOOL()
    hr = webauthn().WebAuthNIsUserVerifyingPlatformAuthenticatorAvailable(byref(flag))
    return hr == 0 and bool(flag.value)


def enroll(hwnd: int, prf_salt: bytes) -> tuple[bytes, bytes]:
    """Create a platform passkey. Returns (credential id, PRF output).

    ``prf_salt`` is the 32 bytes that will be stored in the sidecar. Windows
    applies the WebAuthn PRF derivation. The raw hmac-secret flag stays off.
    """
    if len(prf_salt) != 32:
        raise ValueError("PRF salt must be 32 bytes")
    if not platform_available():
        raise HelloError("Windows Hello is not available on this PC.")

    dll = webauthn()
    api = int(dll.WebAuthNGetApiVersionNumber())
    if api < 6:
        raise HelloError(f"WebAuthn API version {api} cannot enable PRF.")

    keep = _Keep()
    salt = keep.keep(HmacSalt())
    salt.cbFirst = len(prf_salt)
    salt.pbFirst = keep.bytes(prf_salt)

    enabled = keep.keep(BOOL(1))
    extension = keep.keep(Extension())
    extension.pwszExtensionIdentifier = keep.text("hmac-secret")
    extension.cbExtension = sizeof(BOOL)
    extension.pvExtension = _bool_ptr(enabled)
    extensions = keep.keep(Extensions())
    extensions.cExtensions = 1
    extensions.pExtensions = ctypes_pointer(extension)

    cose = keep.keep(CoseParam())
    cose.dwVersion = 1
    cose.pwszCredentialType = keep.text("public-key")
    cose.lAlg = -7
    cose_list = keep.keep(CoseParams())
    cose_list.cCredentialParameters = 1
    cose_list.pCredentialParameters = ctypes_pointer(cose)

    rp = keep.keep(RpInfo())
    rp.dwVersion = 1
    rp.pwszId = keep.text(RP_ID)
    rp.pwszName = keep.text(RP_NAME)

    user_id = os.urandom(32)
    user = keep.keep(UserInfo())
    user.dwVersion = 1
    user.cbId = len(user_id)
    user.pbId = keep.bytes(user_id)
    user.pwszName = keep.text(RP_NAME)
    user.pwszDisplayName = keep.text(RP_NAME)

    options = keep.keep(MakeOptions())
    options.dwVersion = 8 if api >= 8 else 6
    options.dwTimeoutMilliseconds = TIMEOUT_MS
    options.Extensions = extensions
    options.dwAuthenticatorAttachment = 1
    options.bRequireResidentKey = 1
    options.dwUserVerificationRequirement = 1
    options.dwAttestationConveyancePreference = 1
    options.bEnablePrf = 1
    if api >= 8:
        options.pPRFGlobalEval = ctypes_pointer(salt)

    client = keep.keep(_client(keep, "webauthn.create"))
    out = POINTER(Attestation)()
    hr = dll.WebAuthNAuthenticatorMakeCredential(
        hwnd, byref(rp), byref(user), byref(cose_list), byref(client), byref(options), byref(out)
    )
    _raise_for_hr(hr)
    if not out:
        raise HelloError("Windows Hello returned no credential.")

    try:
        att = out.contents
        version = int(att.dwVersion)
        cred_id = _read_buf(att.pbCredentialId, att.cbCredentialId)
        prf_output = _read_first(att.pHmacSecret) if version >= 7 else b""
        prf_enabled = bool(att.bPrfEnabled) if version >= 5 else False
    finally:
        dll.WebAuthNFreeCredentialAttestation(out)

    if not cred_id:
        raise HelloError("Windows Hello returned no credential id.")
    if not prf_output:
        prf_output = evaluate(hwnd, cred_id, prf_salt)
    if len(prf_output) == 0 or prf_output == b"\x00" * len(prf_output):
        raise HelloError("Windows Hello returned an empty PRF output.")
    if api >= 6 and not prf_enabled and not prf_output:
        raise HelloError("Windows Hello did not enable PRF on the new passkey.")
    return cred_id, prf_output


def _bool_ptr(flag: BOOL):
    return ctypes.cast(ctypes.pointer(flag), c_void_p)


def evaluate(hwnd: int, credential_id: bytes, prf_salt: bytes) -> bytes:
    """Ask Hello for the PRF output of an existing passkey."""
    if not credential_id:
        raise ValueError("Credential id is empty")
    if len(prf_salt) != 32:
        raise ValueError("PRF salt must be 32 bytes")

    dll = webauthn()
    keep = _Keep()
    salt = keep.keep(HmacSalt())
    salt.cbFirst = len(prf_salt)
    salt.pbFirst = keep.bytes(prf_salt)
    values = keep.keep(HmacSaltValues())
    values.pGlobalHmacSalt = ctypes_pointer(salt)

    options = keep.keep(GetOptions())
    options.dwVersion = 6
    options.dwTimeoutMilliseconds = TIMEOUT_MS
    options.CredentialList = _allow(keep, credential_id)
    options.dwAuthenticatorAttachment = 1
    options.dwUserVerificationRequirement = 1
    options.pHmacSecretSaltValues = ctypes_pointer(values)

    client = keep.keep(_client(keep, "webauthn.get"))
    rp = keep.text(RP_ID)
    out = POINTER(Assertion)()
    hr = dll.WebAuthNAuthenticatorGetAssertion(hwnd, rp, byref(client), byref(options), byref(out))
    _raise_for_hr(hr)
    if not out:
        raise HelloError("Windows Hello returned no assertion.")
    try:
        assertion = out.contents
        if int(assertion.dwVersion) < 3:
            raise HelloError("Windows Hello did not return a PRF output.")
        output = _read_first(assertion.pHmacSecret)
    finally:
        dll.WebAuthNFreeAssertion(out)
    if not output or output == b"\x00" * len(output):
        raise HelloError("Windows Hello returned an empty PRF output.")
    return output
