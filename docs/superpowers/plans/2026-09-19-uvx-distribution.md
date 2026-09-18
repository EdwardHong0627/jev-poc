# uvx Distribution Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users run the `jev` CLI through `uvx` directly from the canonical GitHub repository.

**Architecture:** Retain the existing setuptools console-script declaration, `jev = "jev_bot.cli:app"`, which is sufficient for `uvx` to expose the CLI after building from GitHub. Add one concise README installation section that shows the canonical direct-source command; no runtime or packaging behavior changes are needed.

**Tech Stack:** Python 3.12+, setuptools, uv/uvx, Markdown.

---

## Chunk 1: Installation documentation

### Task 1: Document direct `uvx` execution

**Files:**
- Modify: `README.md:14` (insert before `## Console CLI`)
- Verify: direct `uvx` execution with an isolated cache directory

- [ ] **Step 1: Confirm the package console script remains available**

Read `pyproject.toml` and confirm the existing declaration remains exactly:

```toml
[project.scripts]
jev = "jev_bot.cli:app"
```

No metadata change is required. Do not change the package name, version, dependencies, or entry point.

- [ ] **Step 2: Add the `uvx` installation section**

Insert this README section immediately before `## Console CLI`:

```markdown
## Install with uvx

Run the CLI directly from GitHub without cloning the repository or creating a
local environment:

```sh
uvx --from git+https://github.com/EdwardHong0627/jev-poc.git jev --help
```

`uvx` installs the package in an isolated environment and exposes its `jev`
console command for the invocation.
```

- [ ] **Step 3: Run the direct-source smoke test**

Run:

```sh
UV_CACHE_DIR=$(mktemp -d) uvx --from git+https://github.com/EdwardHong0627/jev-poc.git jev --help
```

Expected: exit status 0 and Typer’s `jev` help, including the `install`, `uninstall`, and `config` commands. The temporary cache prevents a local source checkout or existing uv cache from satisfying the command.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/superpowers/plans/2026-09-19-uvx-distribution.md
git commit -m "docs: add uvx installation command"
```
