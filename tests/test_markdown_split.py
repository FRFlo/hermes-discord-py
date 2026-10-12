from services.markdown import _markdown_tree_boundaries, split_discord_markdown


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


def test_split_preserves_all_source_characters_including_newlines():
    text = "Header\n\n- first\n- second\n"
    assert "".join(split_discord_markdown(text, limit=18)) == text


def test_split_has_no_application_level_message_count_ceiling():
    text = "0123456789 " * 100
    chunks = split_discord_markdown(text, limit=20)

    assert len(chunks) > 8
    assert "".join(chunks) == text


def test_markdown_ast_provides_block_boundaries():
    text = "first paragraph\n\nsecond paragraph\n\n- item one\n- item two\n"

    assert _markdown_tree_boundaries(text) == [16, 34, 46]


def test_split_prefers_markdown_ast_block_boundary():
    text = "short paragraph\n\n" + ("long " * 20)
    chunks = split_discord_markdown(text, limit=30)

    assert chunks[0] == "short paragraph\n"
    assert len(chunks) > 1
