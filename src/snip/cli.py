# SPDX-License-Identifier: MIT
"""Run commands in a clean bash and copy a plain-text transcript.

Commands come from arguments, else stdin (one per line), else $EDITOR.
They all run in one `bash --noprofile --norc` session so `cd` and `export`
carry over, with no aliases, functions or prompt from the user's shell.
"""

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

from snip import __version__
from snip.aliases import expand_aliases, parse_aliases

EDITOR_HEADER = """\
# snip: enter one command per line, then save and quit to run them.
# Blank lines and lines starting with '#' are skipped.
# A line ending in '\\' continues onto the next line.
"""

ANSI_RE = re.compile(
    r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC
    r"|\x1b\[[0-?]*[ -/]*[@-~]"  # CSI
)

SECRET_RE = re.compile(
    r"gh[pos]_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|xox[abprs]-[A-Za-z0-9-]{10,}"
    r"|Bearer\s+[A-Za-z0-9._~+/=-]{20,}"
    r"|eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY"
)

EXIT_RE = re.compile(r"^# exit \d+$")

# Shell integration: the `snip` function hands the shell's aliases to snip,
# `resnip` snips the previous command, and Ctrl-X s rewrites the current
# (or previous) command line into `snip '<line>'` for review.
INIT = {
    "zsh": """\
snip() { SNIP_ALIASES=$(alias -L) command snip "$@"; }
resnip() { snip "$(fc -ln -1)"; }
_snip_widget() {
  BUFFER="snip ${(qq)${BUFFER:-$history[$((HISTCMD-1))]}}"
  CURSOR=${#BUFFER}
}
zle -N _snip_widget
bindkey '^Xs' _snip_widget
""",
    "bash": """\
snip() { SNIP_ALIASES=$(alias -p) command snip "$@"; }
resnip() { snip "$(fc -ln -1)"; }
_snip_widget() {
  local line=${READLINE_LINE:-$(fc -ln -1)} q="'\\''"
  line=${line#"${line%%[![:space:]]*}"}
  READLINE_LINE="snip '${line//\\'/$q}'"
  READLINE_POINT=${#READLINE_LINE}
}
bind -x '"\\C-xs": _snip_widget'
""",
}


def note(msg, color="36"):
    """Print a `snip:` status line to stderr, colored so it's clearly not output."""
    if sys.stderr.isatty() and "NO_COLOR" not in os.environ:
        msg = f"\x1b[1;{color}m{msg}\x1b[0m"
    print(msg, file=sys.stderr)


def parse_commands(text):
    """Split text into commands: skip blanks/comments, join `\\` continuations."""
    commands, pending = [], []
    for line in text.splitlines():
        if not pending and (not line.strip() or line.lstrip().startswith("#")):
            continue
        pending.append(line)
        if not line.endswith("\\"):
            commands.append("\n".join(pending))
            pending = []
    if pending:
        commands.append("\n".join(pending))
    return commands


def read_editor():
    editor = shlex.split(os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi")
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "snip.sh")
        with open(path, "w") as f:
            f.write(EDITOR_HEADER)
        subprocess.run([*editor, path], check=True)
        # Reopen by path: many editors save by replacing the file.
        with open(path) as f:
            return f.read()


def build_driver(commands):
    """Bash script that echoes each command, runs it, and reports failures."""
    parts = []
    for cmd in commands:
        q = shlex.quote(cmd)
        parts.append(
            f"printf '$ %s\\n' {q}\n"
            f"eval {q}\n"
            "rc=$?; [ $rc -eq 0 ] || printf '# exit %d\\n' $rc\n"
        )
    return "".join(parts)


def run(commands):
    """Run commands in one clean bash, streaming output to stderr; return it."""
    skip = ("BASH_ENV", "ENV", "SNIP_ALIASES")
    env = {k: v for k, v in os.environ.items() if k not in skip}
    env.update(PAGER="cat", GIT_PAGER="cat", AWS_PAGER="", NO_COLOR="1")
    proc = subprocess.Popen(
        ["bash", "--noprofile", "--norc", "-c", build_driver(commands)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )
    chunks = []
    for chunk in iter(lambda: proc.stdout.read1(65536), b""):
        sys.stderr.buffer.write(chunk)
        sys.stderr.buffer.flush()
        chunks.append(chunk)
    proc.wait()
    return b"".join(chunks).decode(errors="replace")


def sanitize(text):
    home = os.path.expanduser("~")
    if home and home != "/":
        text = text.replace(home, "~")
    text = ANSI_RE.sub("", text)
    # Line numbers refer to the generated driver script, not anything the reader has.
    return re.sub(r"^bash: line \d+: ", "bash: ", text, flags=re.M)


def copy(text):
    for cmd in (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"]):
        if shutil.which(cmd[0]):
            subprocess.run(cmd, input=text.encode(), check=True)
            return
    raise RuntimeError("no clipboard tool found (pbcopy, wl-copy, xclip)")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["init"]:
        if len(argv) != 2 or argv[1] not in INIT:
            print(f"usage: snip init {{{','.join(INIT)}}}", file=sys.stderr)
            return 2
        sys.stdout.write(INIT[argv[1]])
        return 0
    ap = argparse.ArgumentParser(
        prog="snip",
        description="Run commands in a clean bash and copy the transcript. "
        "Commands come from arguments, else stdin (one per line), else $EDITOR.",
    )
    ap.add_argument("commands", nargs="*", metavar="CMD", help="a command to run")
    ap.add_argument("-f", action="store_true", help="copy even if a secret matched")
    ap.add_argument("-n", action="store_true", help="print transcript, don't copy")
    ap.add_argument("-V", "--version", action="version", version=__version__)
    args = ap.parse_args(argv)

    try:
        if args.commands:
            commands = [c.strip() for c in args.commands]
        else:
            text = read_editor() if sys.stdin.isatty() else sys.stdin.read()
            commands = parse_commands(text)
    except (OSError, subprocess.CalledProcessError) as e:
        note(f"snip: editor failed: {e}", "31")
        return 1
    if not commands:
        note("snip: no commands, aborting", "31")
        return 1

    aliases = parse_aliases(os.environ.get("SNIP_ALIASES", ""))
    commands = [expand_aliases(c, aliases) for c in commands]

    out = sanitize(run(commands))
    if out and not out.endswith("\n"):
        out += "\n"
    lines = out.splitlines()

    hits = [i for i, line in enumerate(lines, 1) if SECRET_RE.search(line)]
    blocked = bool(hits) and not args.f
    if blocked:
        nums = ", ".join(map(str, hits))
        note(f"snip: possible secret on line(s) {nums}", "33")
        if not args.n:
            note("snip: not copied (use -f to override)", "33")

    if args.n:
        sys.stdout.write(out)
    elif not blocked:
        try:
            copy(out)
        except (RuntimeError, subprocess.CalledProcessError) as e:
            note(f"snip: {e}", "31")
            return 1
        failed = sum(1 for line in lines if EXIT_RE.match(line))
        msg = f"snip: copied {len(commands)} command{'s' * (len(commands) != 1)}"
        msg += f", {len(lines)} line{'s' * (len(lines) != 1)}"
        if failed:
            msg += f" ({failed} non-zero exit{'s' * (failed != 1)})"
        note(msg)
    return 1 if blocked else 0
