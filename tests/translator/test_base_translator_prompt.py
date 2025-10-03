from __future__ import annotations

from dataclasses import dataclass

from pdf2zh_next.translator.base_translator import BaseTranslator


@dataclass
class _DummyTranslationSettings:
    lang_in: str = "en"
    lang_out: str = "zh"
    ignore_cache: bool = False
    custom_prompt: str | None = None


@dataclass
class _DummySettings:
    translation: _DummyTranslationSettings


class _DummyRateLimiter:
    def wait(self, _params):  # noqa: D401 - simple stub
        return None


class _DummyTranslator(BaseTranslator):
    name = "dummy"

    def do_translate(self, text, rate_limit_params: dict | None = None):  # pragma: no cover - not used
        return text


def _make_translator(custom_prompt: str | None = None) -> _DummyTranslator:
    settings = _DummySettings(
        translation=_DummyTranslationSettings(custom_prompt=custom_prompt)
    )
    return _DummyTranslator(settings=settings, rate_limiter=_DummyRateLimiter())


def test_prompt_without_custom_prompt():
    translator = _make_translator()

    prompt_messages = translator.prompt("hello")

    assert len(prompt_messages) == 1
    content = prompt_messages[0]["content"]
    assert (
        "You are a professional translation engine specialized in technical"
        in content
    )
    assert "regulatory documents for en → zh" in content
    assert "Additional instructions" not in content
    assert content.rstrip().endswith("hello")


def test_prompt_with_custom_prompt():
    translator = _make_translator("Please preserve formatting.")

    content = translator.prompt("world")[0]["content"]

    assert "Additional instructions" in content
    assert "Please preserve formatting." in content
    assert content.rstrip().endswith("world")


def test_prompt_with_template_expansion():
    translator = _make_translator(
        "Prefer ${lang_out} terminology and keep original snippet: ${text}"
    )

    content = translator.prompt("sample")[0]["content"]

    assert "Prefer zh terminology" in content
    assert "keep original snippet: sample" in content
