# pipefy-cli

Typer-based CLI for Pipefy. Consumes **`pipefy-ai-sdk`** for GraphQL calls.

Install via the workspace root (`uv sync`) or build this package's wheel from the repo.

See the repository **`README.md`** and **`docs/setup.md`** for `PIPEFY_*` environment variables (same as `pipefy-mcp-server`).

Example:

```bash
PIPEFY_GRAPHQL_URL=https://api.pipefy.com/graphql \\
PIPEFY_OAUTH_URL=… PIPEFY_OAUTH_CLIENT=… PIPEFY_OAUTH_SECRET=… \\
pipefy card get 12345 --json
```

Bearer tokens: prefer `PIPEFY_TOKEN` over `--token` so secrets do not appear in shell history or process listings.

## Shell completion

Typer adds `--install-completion` and `--show-completion`. With a normal TTY, `pipefy --install-completion` detects your shell (via shellingham). For a **named shell** (CI, scripts, or when you want no process-tree scan), set `_TYPER_COMPLETE_TEST_DISABLE_SHELL_DETECTION=1` so the CLI accepts `--install-completion bash` or `zsh` and writes the usual Typer paths (`~/.bash_completions/pipefy.sh` + `~/.bashrc` for bash; `~/.zfunc/_pipefy` + `~/.zshrc` for zsh). Automated checks live in `packages/cli/tests/test_completion.py`.
