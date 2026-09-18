# Harness MCP Registration Design

## Goal

Extend the existing `jev install` and `jev uninstall` commands so they manage the JEV skill and one harness-native, local stdio MCP registration for Claude Code, OpenCode, Oh My Pi, and Pi.

## Decisions

- Keep the existing explicit scope contract: exactly one of `--project` or `--user` is required.
- Extend existing `install` and `uninstall` commands rather than adding a separate MCP command group.
- The JEV decision engine selected removal of the JEV-owned MCP registration during uninstall (`0.96` probability, `0.92` confidence).
- The JEV decision engine selected a portable package console launcher (`1.00` probability, `1.00` confidence) rather than a source-checkout or absolute-environment launcher.
- Add a `jev-mcp` console script targeting `jev_mcp.server:main`. Registrations invoke it through `uvx --from git+https://github.com/EdwardHong0627/jev-poc.git jev-mcp`.
- Never store `JEV_API_TOKEN` or `JEV_ENDPOINT` in a harness configuration file. The server uses its inherited host environment and the existing JEV configuration precedence.

## Harness configuration registry

The installer owns a server named `jev` in each native configuration file.

| Harness | Project configuration | User configuration | Server shape |
| --- | --- | --- | --- |
| Claude Code | `<project>/.mcp.json` | `<home>/.claude.json` | `mcpServers.jev` with `type: "stdio"`, `command`, and `args` |
| OpenCode | `<project>/opencode.json` | `<home>/.config/opencode/opencode.json` | `mcp.servers.jev` with `type: "local"` and a command array |
| Oh My Pi | `<project>/.omp/mcp.json` | `<home>/.omp/agent/mcp.json` | `mcpServers.jev` with `type: "stdio"`, `command`, and `args` |
| Pi | `<project>/.pi/mcp.json` | `<home>/.pi/agent/mcp.json` | `mcpServers.jev` with `transport: "stdio"`, `command`, `args`, and `lifecycle: "lazy"` |

Pi requires its separately installed `pi-mcp-extension`. The JEV installer writes the supported configuration but does not install unrelated third-party packages.

## Ownership and safety

- Registration is idempotent when the existing `jev` entry is structurally equal to the canonical JEV entry for that harness.
- A different existing `jev` entry is foreign. Normal install reports a conflict and does not modify it. `--force` explicitly replaces it.
- Uninstall removes a `jev` entry only when it structurally matches the canonical registration. A foreign or altered entry is left intact and reported.
- Config mutation reads the complete JSON object, updates only the owning server key, and writes the complete object back. All unrelated keys and server entries are preserved.
- Invalid, non-object, or symlinked configuration files are rejected before either skill or MCP mutation. The implementation performs all preflight checks before writes.
- Uninstall leaves an otherwise empty configuration file in place; configuration-file lifecycle is not owned by JEV.

## Command behavior

`jev install <harness> --project <path>` or `--user <path>`:

1. Validate the selected harness and scope.
2. Preflight the skill target and native MCP configuration target.
3. Write or retain the packaged skill using the existing idempotency and `--force` rules.
4. Add or retain the canonical `jev` MCP server entry.
5. Report both managed destinations.

`jev uninstall <harness> --project <path>` or `--user <path>`:

1. Validate the selected harness and scope.
2. Remove the packaged skill according to existing narrow removal rules.
3. Remove only an exact canonical JEV MCP entry.
4. Preserve every other configuration key, server entry, and file.
5. Report both managed destinations and any retained foreign registration.

## Verification

Tests exercise every harness and both scopes: new-file creation, merge with unrelated configuration, idempotency, foreign-entry refusal, forced replacement, narrow uninstall, malformed config refusal, and the `jev-mcp` package script. A focused CLI smoke test installs a representative harness into a temporary project and validates the resulting native configuration.
