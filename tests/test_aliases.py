# SPDX-License-Identifier: MIT
from snip.aliases import expand_aliases, parse_aliases

A = {"k": "kubectl", "ll": "ls -l", "ls": "ls --color", "g": "k get"}


def test_parse_zsh_and_bash_formats():
    text = (
        "alias k=kubectl\n"
        "alias ll='ls -l'\n"
        "alias -g L='| less'\n"
        "alias q='it'\\''s'\n"
        "not an alias\n"
    )
    assert parse_aliases(text) == {"k": "kubectl", "ll": "ls -l", "q": "it's"}


def test_leading_word():
    assert expand_aliases("k get pods", A) == "kubectl get pods"
    assert expand_aliases("echo k", A) == "echo k"


def test_segments():
    cmd = "k get ns | grep x && ll; k a || ll & k b\nk c"
    want = (
        "kubectl get ns | grep x && ls --color -l; kubectl a || ls --color -l"
        " & kubectl b\nkubectl c"
    )
    assert expand_aliases(cmd, A) == want


def test_recursive_and_self_reference():
    assert expand_aliases("g ns", A) == "kubectl get ns"
    assert expand_aliases("ls /", A) == "ls --color /"


def test_substitutions():
    assert expand_aliases("echo $(k get ns)", A) == "echo $(kubectl get ns)"
    assert expand_aliases('echo "$(k get ns)"', A) == 'echo "$(kubectl get ns)"'
    assert expand_aliases("echo `k get ns`", A) == "echo `kubectl get ns`"
    assert expand_aliases("(k a; k b)", A) == "(kubectl a; kubectl b)"
    assert expand_aliases('echo "$(echo "x" | k y)"', A) == (
        'echo "$(echo "x" | kubectl y)"'
    )


def test_quotes_and_escapes_untouched():
    for cmd in ("echo 'k | k'", 'echo "k | k"', r"\k get", '"k" get', "echo a\\;k"):
        assert expand_aliases(cmd, A) == cmd
    assert expand_aliases("echo '$(k)'", A) == "echo '$(k)'"


def test_assignments_and_comments():
    assert expand_aliases("FOO=1 BAR='a b' k x", A) == "FOO=1 BAR='a b' kubectl x"
    assert expand_aliases("echo hi # don't k\nk z", A) == "echo hi # don't k\nkubectl z"


def test_verbatim_whitespace_and_continuations():
    cmd = "k   get \\\n    pods  |  k  x"
    assert expand_aliases(cmd, A) == "kubectl   get \\\n    pods  |  kubectl  x"


def test_no_aliases():
    assert expand_aliases("k get", {}) == "k get"
