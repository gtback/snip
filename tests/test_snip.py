# SPDX-License-Identifier: MIT
import os

import pytest

from snip import cli


@pytest.fixture
def clip(monkeypatch):
    """Capture clipboard writes instead of touching the real clipboard."""
    monkeypatch.delenv("SNIP_ALIASES", raising=False)
    got = []
    monkeypatch.setattr(cli, "copy", got.append)
    return got


def test_parse_commands():
    text = "# c\n\necho a\nprintf '%s' \\\n  b\n  # note\nls\n"
    assert cli.parse_commands(text) == ["echo a", "printf '%s' \\\n  b", "ls"]


def test_args_exit_and_home(clip, capsys):
    rc = cli.main(["echo hi", "false", "echo $HOME"])
    assert rc == 0
    out = clip[0]
    assert out.startswith("$ echo hi\nhi\n$ false\n# exit 1\n$ echo $HOME\n")
    assert out.endswith("\n~\n")
    assert "copied 3 commands, 6 lines (1 non-zero exit)" in capsys.readouterr().err


def test_status_hides_zero_exits_and_singulars(clip, capsys):
    cli.main(["echo hi"])
    assert capsys.readouterr().err.endswith("snip: copied 1 command, 2 lines\n")


def test_status_colored_on_tty(clip, monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(
        "sys.stderr",
        type(
            "E",
            (),
            {
                "isatty": lambda self: True,
                "write": lambda self, s: got.append(s),
                "flush": lambda self: None,
                "buffer": None,
            },
        )(),
    )
    got = []
    cli.note("snip: hi")
    assert "".join(got).startswith("\x1b[1;36msnip: hi\x1b[0m")


def test_state_persists(clip):
    cli.main(["cd /", "pwd"])
    assert clip[0] == "$ cd /\n$ pwd\n/\n"


def test_no_aliases_or_rc(clip, monkeypatch, tmp_path):
    rc_file = tmp_path / "env.sh"
    rc_file.write_text("alias k=kubectl\nexport LEAKED=1\n")
    monkeypatch.setenv("BASH_ENV", str(rc_file))
    cli.main(["type k", "echo ${LEAKED:-unset}"])
    assert "bash: type: k: not found" in clip[0]
    assert clip[0].endswith("unset\n")


def test_stdin_is_devnull(clip):
    cli.main(["cat"])
    assert clip[0] == "$ cat\n"


def test_continuation_from_stdin(clip, monkeypatch):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("printf '%s-%s\\n' \\\n  a b\n"))
    cli.main([])
    assert clip[0] == "$ printf '%s-%s\\n' \\\n  a b\na-b\n"


def test_ansi_stripped(clip):
    cli.main([r"printf '\033[31mred\033[0m\n'"])
    assert clip[0].endswith("red\n")
    assert "\x1b" not in clip[0].split("\n", 1)[1]


def test_secret_blocks_copy(clip, capsys):
    rc = cli.main(["echo ghp_abcdefghijklmnopqrstuvwxyz0123456789"])
    assert rc == 1
    assert clip == []
    assert "line(s) 1, 2" in capsys.readouterr().err


def test_secret_force(clip):
    assert cli.main(["-f", "echo ghp_abcdefghijklmnopqrstuvwxyz0123456789"]) == 0
    assert len(clip) == 1


def test_n_prints_without_copy(clip, capsys):
    assert cli.main(["-n", "echo hi"]) == 0
    assert clip == []
    assert capsys.readouterr().out == "$ echo hi\nhi\n"


def test_empty_stdin_aborts(clip, monkeypatch):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("# nothing\n\n"))
    assert cli.main([]) == 1
    assert clip == []


def test_home_replacement_is_literal(clip, monkeypatch):
    monkeypatch.setenv("HOME", "/h.me")
    assert os.path.expanduser("~") == "/h.me"
    cli.main(["echo /hxme /h.me/x"])
    assert clip[0].endswith("/hxme ~/x\n")


def test_alias_expansion(clip, monkeypatch):
    monkeypatch.setenv("SNIP_ALIASES", "alias say='echo hello'\n")
    cli.main(["say there | tr a-z A-Z"])
    assert clip[0] == "$ echo hello there | tr a-z A-Z\nHELLO THERE\n"


def test_args_are_stripped(clip):
    cli.main(["\techo hi \n"])
    assert clip[0] == "$ echo hi\nhi\n"


def test_editor_replacing_file(clip, monkeypatch, tmp_path):
    # Mimic editors (vim) that save by renaming a new file over the original.
    editor = tmp_path / "editor.sh"
    editor.write_text(
        '#!/bin/sh\nprintf "echo edited\\n" > "$1.new" && mv "$1.new" "$1"\n'
    )
    editor.chmod(0o755)
    monkeypatch.setenv("VISUAL", str(editor))
    monkeypatch.setattr("sys.stdin", type("TTY", (), {"isatty": lambda self: True})())
    assert cli.main([]) == 0
    assert clip[0] == "$ echo edited\nedited\n"


def test_editor_unchanged_aborts(clip, monkeypatch):
    monkeypatch.setenv("VISUAL", "true")
    monkeypatch.setattr("sys.stdin", type("TTY", (), {"isatty": lambda self: True})())
    assert cli.main([]) == 1
    assert clip == []


@pytest.mark.parametrize("shell", ["zsh", "bash"])
def test_init(shell, capsys):
    assert cli.main(["init", shell]) == 0
    assert "resnip()" in capsys.readouterr().out


def test_init_bad_shell():
    assert cli.main(["init", "fish"]) == 2
