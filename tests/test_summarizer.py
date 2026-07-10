import json
from types import SimpleNamespace

import pytest

from summarizer import SummaryError, build_messages, parse_response, summarize


def test_build_messages_mentions_repo_and_json():
    msgs = build_messages("pallets/flask", "readme text")
    joined = " ".join(m["content"] for m in msgs)
    assert "pallets/flask" in joined
    assert "JSON" in joined
    assert "readme text" in joined


def test_parse_response_plain_json():
    raw = json.dumps({"summary": "párrafo largo", "description": "una frase"})
    s = parse_response(raw)
    assert s.summary == "párrafo largo"
    assert s.description == "una frase"


def test_parse_response_with_code_fence():
    raw = "```json\n{\"summary\": \"p\", \"description\": \"d\"}\n```"
    s = parse_response(raw)
    assert s.summary == "p"
    assert s.description == "d"


def test_parse_response_missing_key_raises():
    with pytest.raises(SummaryError):
        parse_response('{"summary": "solo esto"}')


def _client_returning(content, usage=None):
    def create(**kwargs):
        create.captured = kwargs
        message = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)

    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    ), create


def test_summarize_calls_client_and_returns_summary_and_tokens():
    content = json.dumps({"summary": "resumen", "description": "frase"})
    client, create = _client_returning(content, usage=SimpleNamespace(total_tokens=123))
    summary, tokens = summarize("a/b", "texto", model="gpt-5.5", client=client)
    assert summary.summary == "resumen"
    assert summary.description == "frase"
    assert tokens == 123
    assert create.captured["model"] == "gpt-5.5"
    assert create.captured["response_format"] == {"type": "json_object"}


def test_summarize_tokens_zero_when_usage_missing():
    content = json.dumps({"summary": "r", "description": "d"})
    client, _ = _client_returning(content, usage=None)
    _, tokens = summarize("a/b", "texto", model="gpt-5.5", client=client)
    assert tokens == 0
