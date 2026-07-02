from backend.utils.text_utils import split_sentences, normalize_text, transcript_snippet


def test_split_sentences_basic():
    result = split_sentences("Hello world. This is a test. Goodbye.")
    assert len(result) == 3
    assert result[0] == "Hello world."
    assert result[1] == "This is a test."
    assert result[2] == "Goodbye."


def test_split_sentences_single():
    result = split_sentences("Just one sentence.")
    assert len(result) == 1
    assert result[0] == "Just one sentence."


def test_split_sentences_with_question():
    result = split_sentences("What if this works? Let's find out.")
    assert len(result) == 2
    assert "?" in result[0]


def test_split_sentences_with_exclamation():
    result = split_sentences("Wow! That is amazing.")
    assert len(result) == 2


def test_split_sentences_empty():
    assert split_sentences("") == []
    assert split_sentences("   ") == []


def test_normalize_text():
    result = normalize_text("  Hello   world  ")
    assert result == "Hello world"


def test_normalize_text_empty():
    assert normalize_text("") == ""


def test_transcript_snippet():
    parts = ["Hello world. This is a test of the snippet function."]
    result = transcript_snippet(parts, limit=5)
    words = result.split()
    assert len(words) <= 5


def test_transcript_snippet_short():
    parts = ["Hello world."]
    result = transcript_snippet(parts, limit=50)
    assert result == "Hello world."


def test_transcript_snippet_empty():
    assert transcript_snippet([]) == ""
