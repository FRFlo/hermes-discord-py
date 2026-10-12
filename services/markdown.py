"""Markdown-aware Discord message splitting."""

from __future__ import annotations

import re
from bisect import bisect_right

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode


_MARKERS = ("```", "***", "___", "||", "**", "__", "~~", "`", "*", "_")
_LINK_RE = re.compile(r"\[[^\]\n]*\]\([^)\n]*\)")
_PARSER = MarkdownIt("commonmark")


def _syntax_states(text: str) -> tuple[list[tuple[str, ...]], list[bool]]:
    """Track Discord inline formatting ancestors and safe split positions."""
    states: list[tuple[str, ...]] = [()] * (len(text) + 1)
    safe: list[bool] = [True] * (len(text) + 1)
    active: list[str] = []
    protected = [False] * (len(text) + 1)
    for match in _LINK_RE.finditer(text):
        for offset in range(match.start(), match.end() + 1):
            protected[offset] = True

    def mark_position(offset: int) -> None:
        states[offset] = tuple(active)
        safe[offset] = not any(marker in {"```", "`"} for marker in active) and not protected[offset]

    index = 0
    while index < len(text):
        mark_position(index)
        if text[index] == "\\":
            mark_position(min(index + 1, len(text)))
            index += 2
            continue
        marker = next((item for item in _MARKERS if text.startswith(item, index)), None)
        in_fenced_code = "```" in active
        in_inline_code = "`" in active
        if marker and ((in_fenced_code and marker == "```") or
                       (in_inline_code and marker == "`") or
                       (not active)):
            if marker in active:
                active.remove(marker)
            else:
                active.append(marker)
            for offset in range(index + 1, min(index + len(marker), len(text))):
                safe[offset] = False
            mark_position(min(index + len(marker), len(text)))
            index += len(marker)
            continue
        if marker and not in_fenced_code and not in_inline_code:
            if marker in {"_", "__", "___"}:
                before = text[index - 1] if index else " "
                after = text[index + len(marker)] if index + len(marker) < len(text) else " "
                if before.isalnum() and after.isalnum():
                    index += len(marker)
                    continue
            if marker in active:
                active.remove(marker)
            else:
                active.append(marker)
            for offset in range(index + 1, min(index + len(marker), len(text))):
                safe[offset] = False
            mark_position(min(index + len(marker), len(text)))
            index += len(marker)
            continue
        mark_position(index + 1)
        index += 1
    mark_position(len(text))
    return states, safe


def _markdown_tree_boundaries(text: str) -> list[int]:
    """Return source offsets at the ends of Markdown AST nodes.

    markdown-it-py supplies a real block AST. Its source maps let us favor
    boundaries between paragraphs, lists, quotes, and code blocks instead of
    cutting those structures at arbitrary whitespace.
    """
    line_end_offsets = [match.end() for match in re.finditer("\n", text)]
    line_end_offsets.append(len(text))
    tree = SyntaxTreeNode(_PARSER.parse(text))
    boundaries: set[int] = set()

    def visit(node: SyntaxTreeNode) -> None:
        source_map = node.map if node.type != "root" else None
        if source_map:
            line_end = min(source_map[1], len(line_end_offsets))
            if line_end:
                offset = line_end_offsets[line_end - 1]
                if 0 < offset < len(text):
                    boundaries.add(offset)
        for child in node.children:
            visit(child)

    visit(tree)
    return sorted(boundaries)


def split_discord_markdown(text: str, *, limit: int = 2000) -> list[str]:
    """Split at Markdown AST boundaries when possible, restoring inline styles.

    Block-level cuts are selected from markdown-it's parsed syntax tree. Oversized
    individual blocks are split at safe inline boundaries, with open Discord
    formatting closed and reopened around each chunk.
    """
    if not text:
        return []
    if limit < 16:
        raise ValueError("Discord message limit is too small for Markdown continuation")

    states, safe = _syntax_states(text)
    tree_boundaries = _markdown_tree_boundaries(text)
    chunks: list[str] = []
    start = 0
    carry: tuple[str, ...] = ()
    while start < len(text):
        prefix = "".join(carry)
        best = min(len(text), start + limit - len(prefix))
        if best < len(text):
            fallback = None
            while best > start:
                ending = states[best]
                suffix = "".join(reversed(ending))
                if len(prefix) + best - start + len(suffix) <= limit and safe[best]:
                    break
                if fallback is None and len(prefix) + best - start + len(suffix) <= limit:
                    fallback = best
                best -= 1
            if best == start:
                best = fallback if fallback is not None else min(len(text), start + limit - len(prefix))
            else:
                lower_bound = max(start + 1, best - 240)
                ast_candidates = [
                    point for point in tree_boundaries
                    if lower_bound <= point <= best and safe[point]
                    and len(prefix) + point - start + len("".join(reversed(states[point]))) <= limit
                ]
                if ast_candidates:
                    best = ast_candidates[-1]
                else:
                    preferred = [
                        pos for pos in range(best, start, -1)
                        if safe[pos] and text[pos - 1].isspace()
                    ]
                    if preferred:
                        candidate = preferred[0]
                        suffix = "".join(reversed(states[candidate]))
                        if len(prefix) + candidate - start + len(suffix) <= limit:
                            best = candidate
        ending = states[best]
        suffix = "".join(reversed(ending))
        chunks.append(prefix + text[start:best] + suffix)
        carry = ending
        start = best
    return chunks
