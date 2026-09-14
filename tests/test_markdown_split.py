from services.markdown import split_discord_markdown


def test_split_reopens_bold_and_italic_formatting():
    chunks = split_discord_markdown("**" + ("word " * 20) + "**", limit=40)

    assert len(chunks) > 1
    assert all(len(chunk) <= 40 for chunk in chunks)
    assert chunks[0].startswith("**") and chunks[0].endswith("**")
    assert chunks[1].startswith("**")
    assert chunks[-1].endswith("**")


def test_split_preserves_fenced_code_blocks():
    chunks = split_discord_markdown("```python\n" + ("print('ok')\n" * 10) + "```", limit=45)

    assert len(chunks) > 1
    assert all(len(chunk) <= 45 for chunk in chunks)
    assert all(chunk.count("```") == 2 for chunk in chunks)
    assert chunks[0].startswith("```python")
    assert all(chunk.startswith("```") for chunk in chunks[1:])


def test_split_keeps_discord_spoiler_and_strikethrough_valid():
    chunks = split_discord_markdown("||" + ("secret " * 15) + "|| ~~done~~", limit=35)

    assert len(chunks) > 1
    assert all(len(chunk) <= 35 for chunk in chunks)
    assert all(chunk.count("||") in {0, 2} for chunk in chunks)
    assert all(chunk.count("~~") in {0, 2} for chunk in chunks)
