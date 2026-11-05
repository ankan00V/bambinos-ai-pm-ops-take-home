import json
import os

from . import config


def is_available():
    return bool(os.environ.get("OPENAI_API_KEY"))


def polish(prompt_file, payload, fallback):
    if not is_available():
        return fallback, False
    try:
        from openai import OpenAI
    except ImportError:
        return fallback, False
    try:
        prompt_path = config.PROMPT_DIR / prompt_file
        if not prompt_path.exists():
            return fallback, False
        client = OpenAI()
        response = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            temperature=0.2,
            messages=[
                {"role": "system", "content": prompt_path.read_text(encoding="utf-8")},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            return fallback, False
        return content, True
    except Exception:
        return fallback, False
