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

import platformdirs

SHORTCUT_NAME = "Signet.lnk"
ICON_NAME = "Signet.ico"
ARGUMENTS = "-m pwm.signet"
DESCRIPTION = "Signet"
# Same string as the Windows Hello relying party. The taskbar groups the
# pythonw process under this id, so the button can show the Signet seal
# instead of the Python logo. The shortcuts carry the same id.
APP_ID = "signet.pwm.local"

# Known-folder ids from Microsoft’s KNOWNFOLDERID list.
# Desktop follows a OneDrive redirect.
# Programs is %APPDATA%\Microsoft\Windows\Start Menu\Programs, which is
# what Start search and All apps list. FOLDERID_StartMenu
# (625B53C3-AB48-4EC1-BA1F-A1EF4146FC19) is the parent folder. A shortcut
# there does not show up as an app.
_FOLDER_DESKTOP = "B4BFCC3A-DB2C-424C-B029-7FE99A87C641"  # FOLDERID_Desktop
_FOLDER_PROGRAMS = "A77F5D77-2E2B-44C3-A6A2-ABA601054A51"  # FOLDERID_Programs

# Sizes Windows actually asks a shortcut and a taskbar for. 256 is stored
# as 0 in the icon directory. Each size is drawn on its own grid so the
# ring stays sharp when Windows picks a small image.
_ICON_SIZES = (16, 32, 48, 64, 128, 256)
_ICON_CACHE: bytes | None = None

_INK = (0x14 / 255, 0x14 / 255, 0x14 / 255)
_BRASS = (0xD6 / 255, 0xA2 / 255, 0x5E / 255)
_BRASS_LIGHT = (0xF6 / 255, 0xDC / 255, 0xA8 / 255)
_BRASS_DARK = (0x6E / 255, 0x48 / 255, 0x20 / 255)


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
    """Ink seal with a brass ring, at every size Windows uses for an icon.

    Drawn in code so the brass stays ``#d6a25e`` and the corners stay
    transparent. A generated picture would blur at 16 pixels.
    """
    global _ICON_CACHE
    if _ICON_CACHE is None:
        _ICON_CACHE = _pack_icon()
    return _ICON_CACHE


def claim_app_id() -> None:
    """Name this process Signet before any window exists.

    pythonw.exe is the host. Without an explicit id, the taskbar keeps
    Python's icon no matter what image the window sets later.
    """
    if sys.platform != "win32":
        return
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
    shell32.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
    shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)


def window_icon_file() -> Path:
    """Write the seal where the running window can load it.

    The Start menu copy is only created by ``python -m pwm.shortcut``.
    Opening from a terminal still needs a file, and ``iconbitmap`` reads
    a path. The cache is not the vault.
    """
    folder = Path(platformdirs.user_cache_dir("pwm", "pwm"))
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ICON_NAME
    path.write_bytes(signet_icon())
    return path


def apply_window_icon(root) -> None:
    """Title bar and taskbar both use the seal, including the 256 image."""
    path = str(window_icon_file())
    root.iconbitmap(default=path)
    root.iconbitmap(path)
    if sys.platform != "win32":
        return
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.LoadImageW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_uint,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    user32.LoadImageW.restype = ctypes.c_void_p
    user32.SendMessageW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_size_t,
        ctypes.c_void_p,
    ]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.GetParent.argtypes = [ctypes.c_void_p]
    user32.GetParent.restype = ctypes.c_void_p
    hwnd = int(root.winfo_id())
    parent = int(user32.GetParent(hwnd) or 0)
    targets = [hwnd] if parent in (0, hwnd) else [hwnd, parent]
    for target in targets:
        big = user32.LoadImageW(None, path, 1, 256, 256, 0x0010)
        small = user32.LoadImageW(None, path, 1, 16, 16, 0x0010)
        if big:
            user32.SendMessageW(target, 0x0080, 1, big)
        if small:
            user32.SendMessageW(target, 0x0080, 0, small)


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
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

namespace Signet {
  [ComImport, Guid("00021401-0000-0000-C000-000000000046")]
  public class ShellLink {}

  [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("0000010b-0000-0000-C000-000000000046")]
  public interface IPersistFile {
    void GetClassID(out Guid pClassID);
    [PreserveSig] int IsDirty();
    void Load([MarshalAs(UnmanagedType.LPWStr)] string pszFileName, uint dwMode);
    void Save([MarshalAs(UnmanagedType.LPWStr)] string pszFileName, bool fRemember);
    void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string pszFileName);
    void GetCurFile([MarshalAs(UnmanagedType.LPWStr)] out string ppszFileName);
  }

  [StructLayout(LayoutKind.Sequential, Pack = 4)]
  public struct PropertyKey {
    public Guid fmtid;
    public uint pid;
  }

  [StructLayout(LayoutKind.Explicit)]
  public struct PropVariant {
    [FieldOffset(0)] public ushort vt;
    [FieldOffset(8)] public IntPtr pointer;
    public static PropVariant FromString(string value) {
      var pv = new PropVariant();
      pv.vt = 31;
      pv.pointer = Marshal.StringToCoTaskMemUni(value);
      return pv;
    }
  }

  [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")]
  public interface IPropertyStore {
    void GetCount(out uint cProps);
    void GetAt(uint iProp, out PropertyKey pkey);
    void GetValue(ref PropertyKey key, out PropVariant pv);
    void SetValue(ref PropertyKey key, ref PropVariant pv);
    void Commit();
  }

  public static class AppId {
    public static void Set(string path, string appId) {
      var shell = new ShellLink();
      var file = (IPersistFile)shell;
      file.Load(path, 2);
      var store = (IPropertyStore)shell;
      var key = new PropertyKey();
      key.fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");
      key.pid = 5;
      var pv = PropVariant.FromString(appId);
      store.SetValue(ref key, ref pv);
      store.Commit();
      file.Save(path, true);
      Marshal.FreeCoTaskMem(pv.pointer);
    }
  }
}
"@
[Signet.AppId]::Set($env:SIGNET_LNK, $env:SIGNET_APPID)
"""
    env = os.environ.copy()
    env["SIGNET_LNK"] = str(path)
    env["SIGNET_TARGET"] = str(target)
    env["SIGNET_ARGS"] = arguments
    env["SIGNET_WORKDIR"] = str(working_directory)
    env["SIGNET_DESC"] = description
    env["SIGNET_ICON"] = str(icon) if icon is not None else ""
    env["SIGNET_APPID"] = APP_ID
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
$dir = Split-Path -Parent $env:SIGNET_LNK
$name = Split-Path -Leaf $env:SIGNET_LNK
$item = (New-Object -ComObject Shell.Application).NameSpace($dir).ParseName($name)
$id = $item.ExtendedProperty("System.AppUserModel.ID")
if (-not $id) { $id = "" }
Write-Output $id
"""
    env = os.environ.copy()
    env["SIGNET_LNK"] = str(path)
    lines = _powershell(script, env).splitlines()
    while len(lines) < 6:
        lines.append("")
    return {
        "target": lines[0],
        "arguments": lines[1],
        "working_directory": lines[2],
        "description": lines[3],
        "icon": lines[4],
        "app_id": lines[5],
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


def _pack_icon() -> bytes:
    images = [(size, _dib(size)) for size in _ICON_SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = bytearray()
    blob = bytearray()
    for size, image in images:
        stored = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII",
            stored,
            stored,
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


def _cover(inside: float) -> float:
    """How much of a pixel sits inside an edge. ``inside`` is in pixels."""
    edge = 0.75
    if inside >= edge:
        return 1.0
    if inside <= -edge:
        return 0.0
    t = (inside + edge) / (2 * edge)
    return t * t * (3 - 2 * t)


def _lerp(a: tuple[float, float, float], b: tuple[float, float, float], t: float):
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    )


def _over(dst, src, coverage: float):
    """Straight-alpha composite. ``dst`` is red, green, blue, alpha in 0..1."""
    if coverage <= 0.0:
        return dst
    sa = 1.0 if coverage > 1.0 else coverage
    da = dst[3]
    out_a = sa + da * (1.0 - sa)
    if out_a <= 0.0:
        return (0.0, 0.0, 0.0, 0.0)
    keep = da * (1.0 - sa)
    return (
        (src[0] * sa + dst[0] * keep) / out_a,
        (src[1] * sa + dst[1] * keep) / out_a,
        (src[2] * sa + dst[2] * keep) / out_a,
        out_a,
    )


def _rgba(size: int) -> bytes:
    """Top-down seal. Transparent corners, ink face, brass ring, brass diamond."""
    cx = (size - 1) / 2.0
    outer = size * 0.42
    inner = size * 0.26
    mark = size * 0.11
    raw = bytearray(size * size * 4)
    index = 0
    for y in range(size):
        dy = y - cx
        for x in range(size):
            dx = x - cx
            distance = (dx * dx + dy * dy) ** 0.5
            color = (0.0, 0.0, 0.0, 0.0)
            disk = _cover(outer - distance)
            if disk:
                color = _over(color, _INK, disk)
            ring = _cover(min(outer - distance, distance - inner))
            if ring:
                if distance > 1e-6:
                    facing = (dx / distance) * -0.55 + (dy / distance) * -0.84
                else:
                    facing = 1.0
                if facing >= 0.0:
                    brass = _lerp(_BRASS, _BRASS_LIGHT, min(1.0, facing) * 0.9)
                else:
                    brass = _lerp(_BRASS, _BRASS_DARK, min(1.0, -facing) * 0.85)
                color = _over(color, brass, ring)
            diamond = _cover(mark - (abs(dx) + abs(dy)))
            if diamond:
                color = _over(color, _BRASS, diamond)
            raw[index] = int(color[0] * 255 + 0.5)
            raw[index + 1] = int(color[1] * 255 + 0.5)
            raw[index + 2] = int(color[2] * 255 + 0.5)
            raw[index + 3] = int(min(1.0, color[3]) * 255 + 0.5)
            index += 4
    return bytes(raw)


def _dib(size: int) -> bytes:
    """One 32-bit icon image, bottom-up, plus an AND mask for clear corners."""
    rgba = _rgba(size)
    pixels = bytearray(size * size * 4)
    mask_stride = ((size + 31) // 32) * 4
    mask = bytearray(mask_stride * size)
    for screen_y in range(size):
        file_y = size - 1 - screen_y
        for x in range(size):
            src = (screen_y * size + x) * 4
            red, green, blue, alpha = rgba[src : src + 4]
            dst = (file_y * size + x) * 4
            pixels[dst : dst + 4] = bytes((blue, green, red, alpha))
            if alpha < 128:
                mask[file_y * mask_stride + (x // 8)] |= 0x80 >> (x % 8)
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


def _refresh_shell_icons() -> None:
    """Ask Explorer to drop a cached copy of the old seal."""
    if sys.platform != "win32":
        return
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.SHChangeNotify(0x08000000, 0x0000, None, None)


def main() -> None:
    paths = install_shortcuts()
    _refresh_shell_icons()
    print("Signet is on the Start menu and the desktop.")
    for path in paths:
        print(path)
    print("Typing pwm does not open the window.")


if __name__ == "__main__":
    main()
