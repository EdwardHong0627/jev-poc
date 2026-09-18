"""Static framework package configuration sent verbatim on every request."""

from __future__ import annotations


MODEL_ID = "~typesafe/jev-latest"

FRAMEWORK_TYPE = "choice"

FRAMEWORK_INSTRUCTIONS = "Which framework should I follow?"

FRAMEWORK_CRITERIA: dict[str, str] = {
    "custom": "Custom application from scratch; maximum control, highest engineering cost.",
    "openwebui": "Open WebUI interface; ready-made chat experience, less control over workflow.",
    "chainlit": "Python-native conversational UI; fast to build a purpose-specific bot.",
    "gradio": "Rapid browser chatbot prototype; minimal setup, suitable for demos.",
    "streamlit": "Internal decision-support app with chat and forms; strong for business tools.",
    "fastapi_react": "FastAPI backend with a React frontend; production-oriented and fully customizable.",
}
