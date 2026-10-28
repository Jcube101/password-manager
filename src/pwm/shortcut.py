"""
Start menu and desktop shortcuts for Signet.

Typing ``pwm`` does not open the window. These shortcuts run
``pythonw.exe -m pwm.signet`` from the interpreter that created them.
``pythonw.exe`` has no console. A setuptools ``signet.exe`` is not used:
those stubs store an absolute path to Python and break when the virtual
environment moves. Recreate the shortcuts with ``python -m pwm.shortcut``
after a move.
"""

from __future__ import annotations

import ctypes
import os
import struct
import subprocess
import sys
import uuid
from pathlib import Path

SHORTCUT_NAME = "Signet.lnk"
ICON_NAME = "Signet.ico"
ARGUMENTS = "-m pwm.signet"
DESCRIPTION = "Signet"

# Known-folder ids from Microsoft’s KNOWNFOLDERID list.
# Desktop follows a OneDrive redirect.
# Programs is %APPDATA%\Microsoft\Windows\Start Menu\Programs, which is
# what Start search and All apps list. FOLDERID_StartMenu
# (625B53C3-AB48-4EC1-BA1F-A1EF4146FC19) is the parent folder. A shortcut
# there does not show up as an app.
_FOLDER_DESKTOP = "B4BFCC3A-DB2C-424C-B029-7FE99A87C641"  # FOLDERID_Desktop
_FOLDER_PROGRAMS = "A77F5D77-2E2B-44C3-A6A2-ABA601054A51"  # FOLDERID_Programs

_INK = (0x14, 0x14, 0x14, 0xFF)  # B, G, R, A
_BRASS = (0x5E, 0xA2, 0xD6, 0xFF)


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def window_python(executable: Path | None = None) -> Path:
    """``pythonw.exe`` beside this interpreter, so the window has no console."""
    exe = Path(executable or sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    if not pythonw.is_file():
        raise FileNotFoundError(
            f"pythonw.exe is not next to {exe}. Signet would open a console window."
        )
    return pythonw


def launch_workdir(pythonw: Path) -> Path:
    """Directory used as the shortcut's working directory.

    For a virtual environment at ``<repo>/.venv``, this is the repository.
    The import itself does not depend on it. ``-m pwm.signet`` uses the
    interpreter's path.
    """
    venv_root = pythonw.resolve().parent.parent
    if (venv_root / "pyvenv.cfg").is_file():
        return venv_root.parent
    return Path.home()


def known_folder(folder_id: str) -> Path:
    """A Windows known folder. ``folder_id`` is a GUID string."""
    if sys.platform != "win32":
        raise OSError("Signet shortcuts are created on Windows.")
    parsed = uuid.UUID(folder_id)
    guid = _GUID.from_buffer_copy(parsed.bytes_le)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    shell32.SHGetKnownFolderPath.argtypes = [
        ctypes.POINTER(_GUID),
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    shell32.SHGetKnownFolderPath.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    pointer = ctypes.c_wchar_p()
    result = shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(pointer))
    if result != 0 or not pointer.value:
        raise OSError(f"Windows did not return folder {folder_id} ({result})")
    try:
        return Path(pointer.value)
    finally:
        ole32.CoTaskMemFree(pointer)


def signet_icon() -> bytes:
    """A small Ink-and-brass seal. Windows uses this instead of the Python icon."""
    images = [(16, _dib(16)), (32, _dib(32))]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = bytearray()
    blob = bytearray()
    for size, image in images:
        entries += struct.pack(
            "<BBBBHHII",
            size,
            size,
            0,
            0,
            1,
            32,
            len(image),
            offset,
        )
        blob += image
        offset += len(image)
    return bytes(header + entries + blob)


def install_shortcuts(
    *,
    programs_dir: Path | None = None,
    desktop_dir: Path | None = None,
    pythonw: Path | None = None,
) -> list[Path]:
    """Write Signet.lnk on the Start menu and on the desktop.

    Passing the directories keeps tests off the real desktop. The default
    is this user's Start menu Programs folder and their real Desktop.
    """
    programs = Path(programs_dir) if programs_dir is not None else known_folder(_FOLDER_PROGRAMS)
    desktop = Path(desktop_dir) if desktop_dir is not None else known_folder(_FOLDER_DESKTOP)
    target = window_python(pythonw)
    workdir = launch_workdir(target)
    programs.mkdir(parents=True, exist_ok=True)
    desktop.mkdir(parents=True, exist_ok=True)
    icon_path = programs / ICON_NAME
    icon_path.write_bytes(signet_icon())
    written: list[Path] = []
    for folder in (programs, desktop):
        destination = folder / SHORTCUT_NAME
        write_shortcut(
            destination,
            target=target,
            arguments=ARGUMENTS,
            working_directory=workdir,
            description=DESCRIPTION,
            icon=icon_path,
        )
        written.append(destination)
    return written


def write_shortcut(
    path: Path,
    *,
    target: Path,
    arguments: str,
    working_directory: Path,
    description: str,
    icon: Path | None = None,
) -> None:
    """Write one ``.lnk`` through Windows Script Host. No extra package."""
    if sys.platform != "win32":
        raise OSError("Signet shortcuts are created on Windows.")
    path.parent.mkdir(parents=True, exist_ok=True)
    script = """
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($env:SIGNET_LNK)
$lnk.TargetPath = $env:SIGNET_TARGET
$lnk.Arguments = $env:SIGNET_ARGS
$lnk.WorkingDirectory = $env:SIGNET_WORKDIR
$lnk.Description = $env:SIGNET_DESC
if ($env:SIGNET_ICON) { $lnk.IconLocation = $env:SIGNET_ICON }
$lnk.Save()
"""
    env = os.environ.copy()
    env["SIGNET_LNK"] = str(path)
    env["SIGNET_TARGET"] = str(target)
    env["SIGNET_ARGS"] = arguments
    env["SIGNET_WORKDIR"] = str(working_directory)
    env["SIGNET_DESC"] = description
    env["SIGNET_ICON"] = str(icon) if icon is not None else ""
    _powershell(script, env)


def read_shortcut(path: Path) -> dict[str, str]:
    """Read the fields this installer sets. Used to check a shortcut without opening it."""
    script = """
$lnk = (New-Object -ComObject WScript.Shell).CreateShortcut($env:SIGNET_LNK)
Write-Output $lnk.TargetPath
Write-Output $lnk.Arguments
Write-Output $lnk.WorkingDirectory
Write-Output $lnk.Description
Write-Output $lnk.IconLocation
"""
    env = os.environ.copy()
    env["SIGNET_LNK"] = str(path)
    lines = _powershell(script, env).splitlines()
    while len(lines) < 5:
        lines.append("")
    return {
        "target": lines[0],
        "arguments": lines[1],
        "working_directory": lines[2],
        "description": lines[3],
        "icon": lines[4],
    }


def _powershell(script: str, env: dict[str, str]) -> str:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(detail or "Could not write the Signet shortcut.")
    return completed.stdout.strip()


def _dib(size: int) -> bytes:
    """One 32-bit icon image, bottom-up, with an empty AND mask."""
    cx = (size - 1) / 2
    outer = size * 0.42
    inner = size * 0.26
    pixels = bytearray()
    for file_y in range(size):
        screen_y = size - 1 - file_y
        for x in range(size):
            dx = x - cx
            dy = screen_y - cx
            distance = (dx * dx + dy * dy) ** 0.5
            pixels += bytes(_BRASS if inner <= distance <= outer else _INK)
    mask_stride = ((size + 31) // 32) * 4
    mask = bytes(mask_stride * size)
    header = struct.pack(
        "<IiiHHIIiiII",
        40,
        size,
        size * 2,
        1,
        32,
        0,
        len(pixels) + len(mask),
        0,
        0,
        0,
        0,
    )
    return header + bytes(pixels) + mask


def main() -> None:
    paths = install_shortcuts()
    print("Signet is on the Start menu and the desktop.")
    for path in paths:
        print(path)
    print("Typing pwm does not open the window.")


if __name__ == "__main__":
    main()
