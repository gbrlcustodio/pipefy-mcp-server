---
name: login
description: Authenticate with Pipefy via OAuth (browser login). Stores the session in the OS keychain so the Pipefy MCP server's stored-session tier can use it.
disable-model-invocation: true
argument-hint: "[--no-browser] [--callback-timeout <seconds>]"
---

Run the following command. The user must confirm before it executes — do not pre-approve.

```
uvx --from "git+https://github.com/gbrlcustodio/pipefy-mcp-server#subdirectory=packages/cli" pipefy auth login $ARGUMENTS
```

On success the OAuth session is written to the OS keychain. A live MCP server picks up the rotated session on its next tool call; if the server failed to start because credentials were missing, restart it (or restart Claude Code) after login completes.

Pass `--no-browser` to print the authorization URL instead of opening a browser, and `--callback-timeout <seconds>` to override the default 180-second loopback wait.
