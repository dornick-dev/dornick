"""Windows 'Open with Dornick' registration helpers."""

from __future__ import annotations

import sys

import pytest

from dornick import shell_assoc


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_shell_assoc_command_uses_open_flag() -> None:
    line = shell_assoc.command_line(open_arg="%1")
    assert "--open" in line
    assert "%1" in line
    assert "dornick" in line


def test_shell_assoc_keys_cover_file_dir_background() -> None:
    assert len(shell_assoc._KEYS) == 3
    assert any("Background" in k for k in shell_assoc._KEYS)
