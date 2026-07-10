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


def test_summarize_calls_client_and_parses():
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        content = json.dumps({"summary": "resumen", "description": "frase"})
        message = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    s = summarize("a/b", "texto", model="gpt-5.5", client=client)
    assert s.summary == "resumen"
    assert s.description == "frase"
    assert captured["model"] == "gpt-5.5"
    assert captured["response_format"] == {"type": "json_object"}
