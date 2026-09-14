"""Discord Markdown-aware message splitting."""

from __future__ import annotations

import re


_MARKERS = ("```", "***", "___", "||", "**", "__", "~~", "`", "*", "_")
_LINK_RE = re.compile(r"\[[^\]\n]*\]\([^)\n]*\)")


def _syntax_states(text: str) -> tuple[list[tuple[str, ...]], list[bool]]:
    """Return active Markdown markers and safe split positions for every offset."""
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


def split_discord_markdown(text: str, *, limit: int = 2000) -> list[str]:
    """Split text without breaking Discord Markdown formatting.

    Open markers are closed at the end of a chunk and reopened at the beginning
    of the next one. Splits prefer whitespace/newlines, while code spans/fences
    and Markdown links are kept intact whenever possible.
    """
    if not text:
        return []
    if limit < 16:
        raise ValueError("Discord message limit is too small for Markdown continuation")

    states, safe = _syntax_states(text)
    chunks: list[str] = []
    start = 0
    carry: tuple[str, ...] = ()
    while start < len(text):
        prefix = "".join(carry)
        best = min(len(text), start + limit - len(prefix))
        if best < len(text):
            # Closing and reopening markers consume space in both messages.
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
                # A marker/link longer than the limit cannot be made valid; make
                # progress rather than looping forever.
                best = fallback if fallback is not None else min(len(text), start + limit - len(prefix))
            else:
                preferred = [pos for pos in range(best, start, -1) if safe[pos] and text[pos - 1].isspace()]
                if preferred:
                    candidate = preferred[0]
                    suffix = "".join(reversed(states[candidate]))
                    if len(prefix) + candidate - start + len(suffix) <= limit:
                        best = candidate
        ending = states[best]
        suffix = "".join(reversed(ending))
        chunks.append(prefix + text[start:best].rstrip("\n") + suffix)
        carry = ending
        start = best
    return chunks
