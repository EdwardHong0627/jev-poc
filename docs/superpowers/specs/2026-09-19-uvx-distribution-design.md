# uvx Distribution Design

## Goal

Let users run the existing `jev` console command through `uvx` without requiring a PyPI release.

## Decision

Document direct installation from the canonical GitHub repository:

```sh
uvx --from git+https://github.com/EdwardHong0627/jev-poc.git jev
```

JEV selected repository distribution over PyPI distribution (0.75 probability) because the package is not currently published on PyPI and a canonical GitHub remote is available.

## Scope

- Preserve the existing `[project.scripts]` entry point, `jev = "jev_bot.cli:app"`.
- Add a README installation section before the CLI usage documentation.
- Show a short `uvx` invocation and explain that `uvx` creates an isolated environment.

## Non-goals

- Publishing `jev-poc` to PyPI.
- Changing package name, version, dependencies, or CLI behavior.
- Adding an installer wrapper or a second command.

## Verification

Use uv to install and execute `jev --help` directly from the GitHub source in an isolated cache directory. This proves that `uvx` resolves the repository, builds the package, and exposes its declared console script.
