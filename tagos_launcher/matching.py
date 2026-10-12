"""Fuzzy text matching shared by every command.

The query is split into words; every word must match at least one of the
candidate fields. Each word scores higher the "better" its match is:

* the field starts with it                      -> ~100
* it starts a word inside the field             -> ~80
* it appears anywhere in the field              -> ~60
* its letters appear in order (e.g. "vsc" ~ "Visual Studio Code") -> <= 30

The final score is the average over the words, so results can be sorted.
"""

from __future__ import annotations

from typing import Optional


def _token_score(token: str, text: str) -> Optional[float]:
    if text.startswith(token):
        return 100.0 - min(len(text) - len(token), 40) * 0.1
    idx = text.find(token)
    if idx >= 0:
        boundary = not text[idx - 1].isalnum()
        return (80.0 if boundary else 60.0) - min(idx, 40) * 0.25
    if len(token) < 2:
        return None
    # Subsequence match: every letter in order, penalised by the gaps between.
    pos = -1
    gaps = 0
    for ch in token:
        nxt = text.find(ch, pos + 1)
        if nxt < 0:
            return None
        if pos >= 0:
            gaps += nxt - pos - 1
        pos = nxt
    if gaps > len(token) * 4:
        return None
    return max(1.0, 30.0 - gaps)


def score(query: str, *fields: str) -> Optional[float]:
    """Score *query* against *fields*; None when it doesn't match at all.

    An empty query matches everything with a score of 0.
    """
    tokens = query.lower().split()
    if not tokens:
        return 0.0
    haystacks = [f.lower() for f in fields if f]
    total = 0.0
    for token in tokens:
        best: Optional[float] = None
        for hay in haystacks:
            s = _token_score(token, hay)
            if s is not None and (best is None or s > best):
                best = s
        if best is None:
            return None
        total += best
    return total / len(tokens)
