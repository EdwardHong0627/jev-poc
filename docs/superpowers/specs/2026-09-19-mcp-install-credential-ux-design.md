# MCP Install Credential UX Design

## Goal

Make first-time `jev install` setup usable without requiring a separate configuration command, while never exposing an OpenRouter token or writing partial harness installation state.

## Trigger

The credential check runs only from the MCP-aware `jev install` flow. It resolves the token using the existing runtime precedence:

1. `JEV_API_TOKEN` in the process environment;
2. project `.env` loaded by the existing configuration loader;
3. valid secure user configuration at `$XDG_CONFIG_HOME/jev-poc/config.json`.

When any source resolves a non-blank token, installation continues without prompting and without modifying user configuration.

## First-time interactive flow

When no token resolves and standard input is a terminal:

1. Prompt exactly once with hidden input: `OpenRouter API token:`.
2. Reject blank input before touching skills or harness MCP config.
3. Store the token with the existing atomic, mode-`0600` user-config writer.
4. Store `https://openrouter.ai/api/alpha/decisions` as the persistent endpoint.
5. Continue ordinary skill-plus-MCP installation only after configuration persistence succeeds.

The endpoint is written only alongside an interactively collected token. Existing environment-provided credentials remain ephemeral and are not copied into persistent storage.

## Non-interactive flow

When no token resolves and stdin is not a terminal, fail before any installation mutation. The error must direct users to either set `JEV_API_TOKEN` or run:

```sh
jev config set token --stdin
```

The command never falls back to echoing a token argument, never inserts credentials into harness configuration, and never prompts in CI/piped execution.

## Boundaries and failure behavior

- The prompt is CLI-only. The pure installer and MCP registration domain remain free of Typer, stdin, environment prompting, or secret storage.
- Credential persistence reuses the existing secure config store; no new secret file format is introduced.
- Prompt cancellation, blank input, config-write failure, and non-interactive missing credentials leave both skill and MCP configuration unchanged.
- A pre-existing malformed user config surfaces its existing actionable configuration error rather than being overwritten.

## Verification

Behavior tests cover prompt only when unresolved, no prompt for environment/.env/stored tokens, default endpoint persistence, hidden token capture, blank/cancel/non-interactive failures, config-write failure with no installation mutation, and unchanged behavior when credentials already resolve. An interactive smoke test verifies a first-time install creates secure user configuration and the expected harness skill/MCP registration without exposing the token in output.
