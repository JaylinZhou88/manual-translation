from __future__ import annotations

import os
import re

from dotenv import load_dotenv


load_dotenv()

DEFAULT_BAILIAN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_BAILIAN_MODEL = "qwen-plus"

GLOSSARY = {
    "pump": "máy bơm",
    "booster pump": "máy bơm tăng áp",
    "variable-frequency": "biến tần",
    "permanent-magnet": "nam châm vĩnh cửu",
    "service manual": "sách hướng dẫn sử dụng",
    "warning": "cảnh báo",
    "model": "model",
    "voltage": "điện áp",
    "power": "công suất",
    "flow": "lưu lượng",
    "head": "cột áp",
}

PROTECTED_PATTERN = re.compile(
    r"\b(?:[A-Z]{2,}[A-Z0-9-]*|Z1|SHIMGE|[0-9]+(?:\.[0-9]+)?\s*(?:V|W|kW|Hz|A|m|mm|L/min|bar|MPa))\b"
)


def _protect_tokens(text: str) -> tuple[str, dict[str, str]]:
    replacements: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        key = f"__KEEP_{len(replacements)}__"
        replacements[key] = match.group(0)
        return key

    return PROTECTED_PATTERN.sub(replace, text), replacements


def _restore_tokens(text: str, replacements: dict[str, str]) -> str:
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text


def glossary_hint() -> str:
    return "\n".join(f"- {en}: {vi}" for en, vi in GLOSSARY.items())


def _get_bailian_config() -> tuple[str | None, str, str]:
    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("BAILIAN_API_KEY")
    base_url = os.getenv("DASHSCOPE_BASE_URL") or os.getenv(
        "BAILIAN_BASE_URL", DEFAULT_BAILIAN_BASE_URL
    )
    model = os.getenv("BAILIAN_TRANSLATION_MODEL") or os.getenv(
        "DASHSCOPE_MODEL", DEFAULT_BAILIAN_MODEL
    )
    return api_key, base_url, model


def get_bailian_status() -> dict[str, str | bool | None]:
    api_key, base_url, model = _get_bailian_config()
    return {
        "configured": bool(api_key),
        "base_url": base_url,
        "model": model,
        "key_hint": f"{api_key[:6]}...{api_key[-4:]}" if api_key and len(api_key) >= 12 else None,
    }


def translate_to_vietnamese(text: str) -> tuple[str, str | None]:
    """Return translated text and an optional note.

    If DASHSCOPE_API_KEY is unavailable, keep the source text as a safe placeholder.
    This avoids pretending a machine translation happened.
    """

    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return "", "empty source text"

    protected, replacements = _protect_tokens(clean)
    api_key, base_url, model = _get_bailian_config()
    if not api_key:
        return clean, "DASHSCOPE_API_KEY is not set; please translate/review manually."

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional technical translator. Translate English water "
                        "pump service manual text into Vietnamese. "
                        "Keep placeholders like __KEEP_0__ unchanged. Keep model names, units, "
                        "numbers, company names, and safety warning meaning exact. Use concise, "
                        "manual-style Vietnamese. Return only the Vietnamese translation, no "
                        "explanation. Glossary:\n" + glossary_hint()
                    ),
                },
                {"role": "user", "content": protected},
            ],
            temperature=0.1,
        )
        translated = response.choices[0].message.content or protected
        return _restore_tokens(translated.strip(), replacements), None
    except Exception as exc:  # pragma: no cover - depends on external service
        return clean, f"Alibaba Bailian translation failed: {exc}"
