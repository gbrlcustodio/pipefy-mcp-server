---
name: pipefy-login
description: Authenticate with Pipefy via OAuth (browser login). Stores the session in the OS keychain so the Pipefy MCP server's stored-session tier can use it.
disable-model-invocation: true
argument-hint: "[--no-browser] [--callback-timeout <seconds>]"
---

Run the following command. The user must confirm before it executes — do not pre-approve.

```
uvx --from git+https://github.com/gbrlcustodio/pipefy-mcp-server pipefy auth login $ARGUMENTS
```

On success the OAuth session is written to the OS keychain. The Pipefy MCP server picks it up on its next tool call without a restart; if the server failed to start because of missing credentials, restart it after login completes.

Pass `--no-browser` to print the authorization URL instead of opening a browser, and `--callback-timeout <seconds>` to override the default 180-second loopback wait.
