# snip

Run shell commands in a clean bash and copy a plain-text transcript, ready to
paste into docs and PR comments.

Copying from an interactive shell drags in your aliases, prompt and alias hints.
`snip` runs the commands in `bash --noprofile --norc` (keeping your environment
such as `PATH` and `KUBECONFIG`), prints a plain `$ cmd` before each one, and
copies the result to the clipboard.

## Features

- **Clean environment:** commands run in `bash --noprofile --norc`, so no aliases,
  functions or prompt from your shell leak in. Your environment variables are kept.
- **Plain transcript:** a `$ cmd` line before each command, output below it, and a
  `# exit N` line after any command that fails. No code fence.
- **One session:** all commands share a bash session, so `cd` and `export` carry
  over between steps.
- **Flexible input:** commands as arguments, one per line on stdin, or typed into
  `$VISUAL`/`$EDITOR`. Stdin and the editor support `#` comments and `\`
  continuations.
- **Alias expansion:** aliases from your shell are expanded in the transcript, so
  readers see commands they can run.
- **Edit and re-run:** `snip -e` reopens the previous commands in your editor.
- **Snip what you just ran:** `resnip` and a key binding (`Ctrl-X s`) for zsh and
  bash.
- **Tidy output:** `$HOME` becomes `~`, ANSI escapes are stripped, and the status
  line is colored so it's clearly not part of the transcript.
- **Secret check:** refuses to copy output that looks like a token or private key
  unless you pass `-f`.
- **Portable clipboard:** `pbcopy`, `wl-copy` or `xclip`, or `-n` to print to stdout.

## Install

```sh
pipx install .        # or: uv tool install .
```

## Usage

```sh
snip 'kubectl get ns' 'kubectl get pods -A'   # each argument is a command
snip < repro.txt                              # one command per line on stdin
snip                                          # opens $VISUAL/$EDITOR
snip -e                                       # edit and re-run the previous snip
```

From stdin or the editor, blank lines and `#` lines are skipped and a trailing
`\` continues a command onto the next line.

All commands share one bash session, so `cd` and `export` carry over. Stdin is
`/dev/null`, pagers are disabled and `NO_COLOR=1` is set. A failing command adds
a `# exit N` line and the run continues.

Output has `$HOME` replaced by `~` and ANSI escapes stripped. If it looks like it
contains a secret (GitHub/AWS/Slack tokens, bearer tokens, JWTs, private keys),
`snip` reports the line numbers, copies nothing and exits non-zero.

Aliases are expanded to their definitions (see Shell integration), so the
transcript shows commands a reader can actually run.

| Flag | Effect |
| ---- | ------ |
| `-f` | copy even if a secret pattern matched |
| `-n` | print the transcript to stdout instead of copying |
| `-e` | edit the previous commands in `$VISUAL`/`$EDITOR`, then run |

The commands of each run are saved as typed (aliases unexpanded) in
`${XDG_STATE_HOME:-~/.local/state}/snip/last.sh`, readable only by you. A
multi-line command passed as a single argument without `\` continuations comes
back from `-e` as separate lines.

Clipboard: `pbcopy`, else `wl-copy`, else `xclip`.

## Shell integration

Add to `~/.zshrc` (or `~/.bashrc` with `bash`):

```sh
eval "$(snip init zsh)"
```

This provides:

- `snip`: a wrapper that passes your shell's aliases to snip. An alias is
  expanded at the start of each command: the beginning of the text and after
  `|`, `||`, `&&`, `;`, `&`, a newline, `(`, `$(` or a backtick. Text in quotes
  is left alone. Shell functions can't be expanded.
- `resnip`: snip the previous command.
- `Ctrl-X s`: rewrite the current command line (or the previous command, if the
  line is empty) into `snip '<line>'`, quoted, for review before you press Enter.

The expansion is in `snip/aliases.py` and has no other dependencies. Known gaps:
heredoc bodies are scanned like commands, and shell keywords such as `then` are
not treated as command starts.

## Development

```sh
uv run pytest
uv run ruff check
```
