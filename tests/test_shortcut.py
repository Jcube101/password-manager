"""Signet shortcuts. These tests do not open the window or the real desktop."""

import struct

import pytest

from pwm.shortcut import (
    _FOLDER_DESKTOP,
    _FOLDER_PROGRAMS,
    ARGUMENTS,
    install_shortcuts,
    launch_workdir,
    read_shortcut,
    signet_icon,
    window_python,
)


def test_start_menu_folder_is_folderid_programs():
    # Pinned so a future edit does not swap in FOLDERID_StartMenu, the parent.
    assert _FOLDER_PROGRAMS.upper() == "A77F5D77-2E2B-44C3-A6A2-ABA601054A51"
    assert _FOLDER_DESKTOP.upper() == "B4BFCC3A-DB2C-424C-B029-7FE99A87C641"
    assert _FOLDER_PROGRAMS.upper() != "625B53C3-AB48-4EC1-BA1F-A1EF4146FC19"


def test_signet_icon_is_an_ico_with_two_sizes():
    blob = signet_icon()
    reserved, kind, count = struct.unpack_from("<HHH", blob, 0)
    assert (reserved, kind, count) == (0, 1, 2)
    sizes = []
    for index in range(count):
        width, height = struct.unpack_from("<BB", blob, 6 + 16 * index)
        sizes.append((width, height))
    assert sizes == [(16, 16), (32, 32)]


def test_shortcuts_point_at_pythonw_and_not_at_pwm(tmp_path):
    pythonw = tmp_path / "pythonw.exe"
    pythonw.write_bytes(b"")
    programs = tmp_path / "Programs"
    desktop = tmp_path / "Desktop"

    written = install_shortcuts(
        programs_dir=programs,
        desktop_dir=desktop,
        pythonw=pythonw,
    )

    assert [path.name for path in written] == ["Signet.lnk", "Signet.lnk"]
    assert (programs / "Signet.ico").is_file()
    for path, folder in zip(written, (programs, desktop), strict=True):
        assert path.parent == folder
        info = read_shortcut(path)
        assert info["target"].casefold().endswith("pythonw.exe")
        assert info["arguments"] == ARGUMENTS
        assert "pwm.exe" not in info["arguments"].casefold()
        assert info["description"] == "Signet"
        assert info["icon"].casefold().startswith(str(programs / "Signet.ico").casefold())


def test_venv_shortcuts_start_in_the_repository(tmp_path):
    repo = tmp_path / "repo"
    scripts = repo / ".venv" / "Scripts"
    scripts.mkdir(parents=True)
    (repo / ".venv" / "pyvenv.cfg").write_text("home = C:/Python\n", encoding="utf-8")
    pythonw = scripts / "pythonw.exe"
    pythonw.write_bytes(b"")

    assert window_python(pythonw) == pythonw
    assert launch_workdir(pythonw) == repo


def test_shortcuts_outside_a_venv_start_at_home(tmp_path, monkeypatch):
    pythonw = tmp_path / "pythonw.exe"
    pythonw.write_bytes(b"")
    home = tmp_path / "home"
    monkeypatch.setattr("pwm.shortcut.Path.home", lambda: home)
    assert launch_workdir(pythonw) == home


def test_window_python_refuses_a_console_interpreter(tmp_path):
    python = tmp_path / "python.exe"
    python.write_bytes(b"")
    with pytest.raises(FileNotFoundError, match="pythonw.exe"):
        window_python(python)
