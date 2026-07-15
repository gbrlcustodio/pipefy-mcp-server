---
name: pipefy-login
description: Authenticate with Pipefy via OAuth and store the session in the OS keychain.
disable-model-invocation: true
argument-hint: "[--no-browser] [--callback-timeout <seconds>]"
---

If `command -v pipefy` fails, stop and tell the user to run `/pipefy:install` first.

Otherwise prompt the user to confirm running:

```
pipefy auth login $ARGUMENTS
```

This targets Pipefy production by default. Only set `PIPEFY_AUTH_URL` (the OIDC issuer URL) in the shell environment when logging in to a non-prod IdP; it defaults to `https://signin.pipefy.com/realms/pipefy`.
