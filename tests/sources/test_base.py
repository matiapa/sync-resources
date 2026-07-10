from sources.base import RenderedNote


def test_rendered_note_defaults_tokens_to_zero():
    note = RenderedNote(text="hola")
    assert note.text == "hola"
    assert note.tokens == 0


def test_rendered_note_is_frozen():
    note = RenderedNote(text="x", tokens=5)
    try:
        note.text = "y"
    except Exception as exc:
        assert "frozen" in type(exc).__name__.lower() or "cannot assign" in str(exc).lower()
    else:
        raise AssertionError("RenderedNote debería ser inmutable")
