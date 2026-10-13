# SPDX-License-Identifier: MIT
"""Shell alias parsing and expansion that leaves the rest of the text verbatim.

`expand_aliases` is a small quote-aware scanner, not a full shell parser. It
expands an alias only where a command can start: the beginning of the text and
after `|`, `||`, `&&`, `;`, `&`, a newline, `(`, `$(` or a backtick. Known gaps:
heredoc bodies are scanned like commands, and shell keywords (`if`, `then`, ...)
are not treated as command starts.
"""

import re
import shlex

# NAME=value (value may contain quotes) is skipped, as the command follows it.
_ASSIGN = re.compile(r"""[A-Za-z_]\w*=(?:"[^"]*"|'[^']*'|[^\s|&;()<>'"`$\\])*""")
_WORD = re.compile(r"""[^\s|&;()<>'"`$\\#]+""")


def parse_aliases(text):
    """Parse `alias NAME=VALUE` lines (zsh `alias -L`, bash `alias -p`)."""
    aliases = {}
    for line in text.splitlines():
        try:
            tokens = shlex.split(line)
        except ValueError:
            continue
        if len(tokens) < 2 or tokens[0] != "alias" or tokens[1].startswith("-"):
            continue
        for token in tokens[1:]:
            name, sep, value = token.partition("=")
            if sep and name:
                aliases[name] = value
    return aliases


def expand_aliases(cmd, aliases, _seen=frozenset()):
    """Expand aliases at command positions in `cmd`; an alias expands once."""
    if not aliases:
        return cmd
    out = []
    stack = ["cmd"]  # open quote/substitution contexts, innermost last
    start = True  # True where the next word is in command position
    i, n = 0, len(cmd)
    while i < n:
        c = cmd[i]
        top = stack[-1]
        if top == "sq":
            if c == "'":
                stack.pop()
            out.append(c)
            i += 1
            continue
        if c == "\\":
            out.append(cmd[i : i + 2])
            i += 2
            start = False
            continue
        if cmd.startswith("$(", i):
            stack.append("sub")
            start = True
            out.append("$(")
            i += 2
            continue
        if top == "dq":
            if c == '"':
                stack.pop()
            elif c == "`":
                stack.append("bt")
                start = True
            out.append(c)
            i += 1
            continue
        # Command contexts: cmd, sub, bt.
        if c == "'":
            stack.append("sq")
            start = False
        elif c == '"':
            stack.append("dq")
            start = False
        elif c == "(":
            stack.append("sub")
            start = True
        elif c == ")":
            if top == "sub":
                stack.pop()
            start = False
        elif c == "`":
            if top == "bt":
                stack.pop()
                start = False
            else:
                stack.append("bt")
                start = True
        elif c == "&" and (cmd[i - 1 : i] in ("<", ">") or cmd[i + 1 : i + 2] == ">"):
            # Redirection (`2>&1`, `>&2`, `&>file`), not a command separator.
            start = False
        elif c in "|&;\n":
            start = True
        elif c.isspace() or c in "<>":
            pass
        elif c == "#" and (i == 0 or cmd[i - 1].isspace()):
            end = cmd.find("\n", i)
            end = n if end == -1 else end
            out.append(cmd[i:end])
            i = end
            continue
        elif start:
            m = _ASSIGN.match(cmd, i)
            if m:
                out.append(m.group())
                i = m.end()
                continue
            m = _WORD.match(cmd, i)
            if m:
                word = m.group()
                if word in aliases and word not in _seen:
                    word = expand_aliases(aliases[word], aliases, _seen | {word})
                out.append(word)
                i = m.end()
                start = False
                continue
            start = False
        else:
            start = False
        out.append(c)
        i += 1
    return "".join(out)
