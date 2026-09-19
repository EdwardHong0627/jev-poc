# Test Report

## Command

```sh
uv run python -m pytest -v
```

## Result

- Exit status: `0`
- Passed: `342`
- Failed: `0`
- Duration: `2.73s`

## Coverage exercised

- OpenRouter Decisions client: typed response parsing, retries, error redaction, metadata.
- Typed choice, score, and noul request/response models.
- MCP `jev_decide` tool input validation, lifecycle, and confidence output.
- Conversational CLI and Typer installer/config CLI.
- Skill installer safety, package-resource loading, target mappings, and uninstall behavior.
- User configuration persistence, permissions, precedence, and validation.

## Environment note

`uv` emitted an existing virtual-environment selection warning because `VIRTUAL_ENV=/Users/huaichehong/base` differs from the project `.venv`. It did not affect execution: pytest completed successfully with exit status `0`.
