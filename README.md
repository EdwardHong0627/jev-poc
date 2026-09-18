# JEV PoC

Conversational CLI over the JEV Decisions API.

## Setup

`JEV_API_TOKEN` is required in the environment. Set it before running; the
program exits with a configuration error when it is missing.

`JEV_ENDPOINT` is optional. When unset, the default endpoint is used. When set,
it must be an HTTPS URL on `openrouter.ai` without userinfo, otherwise startup
fails with a configuration error.

## Run

```sh
uv run python main.py
```

Type a message at the `>` prompt; type `quit` or `exit` to leave. Failures from
the Decisions API are reported as a generic message without credentials or
endpoint details.

## Framework

Every request sends the fixed `framework` question (`type: choice`,
instructions "Which framework should I follow?") with candidate keys:

- `custom`
- `openwebui`
- `chainlit`
- `gradio`
- `streamlit`
- `fastapi_react`

## Output

Each reply prints the selected framework key followed by per-candidate
probabilities sorted highest first:

```text
Selected: <choice>
  <candidate>: <probability>
  ...
```
