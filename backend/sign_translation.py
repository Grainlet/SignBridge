from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

import config

_CONTRACTIONS = {
    "i'm": "i am",
    "you're": "you are",
    "we're": "we are",
    "they're": "they are",
    "he's": "he is",
    "she's": "she is",
    "it's": "it is",
    "that's": "that is",
    "what's": "what is",
    "where's": "where is",
    "who's": "who is",
    "how's": "how is",
    "don't": "do not",
    "doesn't": "does not",
    "didn't": "did not",
    "can't": "can not",
    "cannot": "can not",
    "won't": "will not",
    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",
    "i've": "i have",
    "you've": "you have",
    "we've": "we have",
    "i'll": "i will",
    "you'll": "you will",
}

\
PHRASE_RULES: dict[str, list[str]] = {
    "thank you very much": ["thank you", "many"],
    "what is your name": ["your", "name", "what"],
    "how are you": ["how", "you"],
    "i am fine": ["i", "fine"],
    "you are welcome": ["welcome"],
    "nice to meet you": ["nice", "meet", "you"],
    "see you later": ["see", "you", "later"],
    "going to school": ["school", "go"],
    "go to school": ["school", "go"],
    "good morning": ["good", "morning"],
    "good afternoon": ["good", "afternoon"],
    "good evening": ["good", "night"],
    "good night": ["good", "night"],
    "thank you": ["thank you"],
    "excuse me": ["excuse"],
    "i am sorry": ["i", "sorry"],
    "i love you": ["i", "love", "you"],
    "how old are you": ["you", "old", "how"],
    "where are you from": ["you", "from", "where"],
    "what time is it": ["time", "what"],
    "do you understand": ["you", "understand"],
    "i do not understand": ["i", "understand", "not"],
}

\
ASL_OMITTED_WORDS = {
    "a",
    "an",
    "the",
    "is",
    "am",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "do",
    "does",
    "did",
    "to",
    "of",
    "at",
    "on",
    "in",
    "that",
    "it",
}

SYNONYMS: dict[str, str] = {
    "hi": "hello",
    "hey": "hello",
    "greetings": "hello",
    "bye": "goodbye",
    "thanks": "thank you",
    "ok": "fine",
    "okay": "fine",
    "alright": "fine",
    "kid": "child",
    "kids": "children",
    "glad": "happy",
    "begin": "start",
    "speak": "talk",
    "speaking": "talk",
    "talking": "talk",
    "automobile": "car",
    "going": "go",
    "went": "go",
    "goes": "go",
    "seeing": "see",
    "saw": "see",
    "wanted": "want",
    "wants": "want",
    "needed": "need",
    "needs": "need",
    "liked": "like",
    "likes": "like",
    "loved": "love",
    "loves": "love",
    "helped": "help",
    "helping": "help",
    "helps": "help",
    "understood": "understand",
    "understanding": "understand",
    "learned": "learn",
    "learning": "learn",
    "working": "work",
    "worked": "work",
    "walking": "walk",
    "walked": "walk",
    "my": "my",
    "me": "me",
}

TIME_MARKERS = {
    "today",
    "tomorrow",
    "yesterday",
    "now",
    "morning",
    "afternoon",
    "night",
    "later",
    "before",
    "after",
    "always",
    "never",
    "week",
    "month",
    "year",
}

WH_WORDS = {"what", "who", "where", "when", "why", "how", "which"}
NEGATION_WORDS = {"not", "no", "never"}

_VOCAB_CACHE: Optional[set[str]] = None


def load_available_glosses(
    index_path: Optional[Path] = None,
    metadata_path: Optional[Path] = None,
) -> set[str]:
    global _VOCAB_CACHE
    if index_path is None and metadata_path is None and _VOCAB_CACHE is not None:
        return _VOCAB_CACHE

    glosses: set[str] = set()
    idx_file = Path(index_path or config.WLASL_INDEX_PATH)
    meta_file = Path(metadata_path or config.SIGN_METADATA_PATH)

    if idx_file.exists():
        data = json.loads(idx_file.read_text(encoding="utf-8"))
        glosses.update(k.strip().lower() for k in data.keys())

    if meta_file.exists():
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        for item in meta.get("signs", []):
            phrase = str(item.get("english_phrase") or "").strip().lower()
            if phrase:
                glosses.add(phrase)

    if index_path is None and metadata_path is None:
        _VOCAB_CACHE = glosses
    return glosses


def _normalize_text(text: str) -> str:
    lower = (text or "").lower().strip()
    tokens = re.findall(r"[a-z0-9']+", lower)
    expanded: list[str] = []
    for tok in tokens:
        if tok in _CONTRACTIONS:
            expanded.extend(_CONTRACTIONS[tok].split())
        else:
            expanded.append(tok.strip("'"))
    return " ".join(t for t in expanded if t)


def _resolve_word_to_gloss(word: str, vocab: set[str]) -> Optional[str]:
    if word in vocab:
        return word
    if word in SYNONYMS and SYNONYMS[word] in vocab:
        return SYNONYMS[word]

    candidates: list[str] = []
    if len(word) > 4 and word.endswith("ies"):
        candidates.append(word[:-3] + "y")
    if len(word) > 3 and word.endswith("es"):
        candidates.append(word[:-2])
    if len(word) > 3 and word.endswith("s"):
        candidates.append(word[:-1])
    if len(word) > 4 and word.endswith("ed"):
        candidates.extend([word[:-2], word[:-1]])
    if len(word) > 5 and word.endswith("ing"):
        candidates.extend([word[:-3], word[:-3] + "e"])

    for cand in candidates:
        if cand in vocab:
            return cand
        if cand in SYNONYMS and SYNONYMS[cand] in vocab:
            return SYNONYMS[cand]

    return None


def _reorder_asl_grammar(glosses: list[str]) -> list[str]:
    if len(glosses) <= 1:
        return glosses

    time_tokens: list[str] = []
    wh_tokens: list[str] = []
    neg_tokens: list[str] = []
    core_tokens: list[str] = []

    for g in glosses:
        if g in TIME_MARKERS and g not in time_tokens:
            time_tokens.append(g)
        elif g in WH_WORDS:
            wh_tokens.append(g)
        elif g in NEGATION_WORDS:
            neg_tokens.append(g)
        else:
            core_tokens.append(g)

    return time_tokens + core_tokens + neg_tokens + wh_tokens


def translate_sentence(
    sentence: dict[str, Any],
    vocab: Optional[set[str]] = None,
) -> dict[str, Any]:
    available_vocab = vocab if vocab is not None else load_available_glosses()
    raw_text = str(sentence.get("text") or "").strip()
    normalized = _normalize_text(raw_text)
    words = normalized.split() if normalized else []

    sorted_phrases = sorted(PHRASE_RULES.keys(), key=lambda p: len(p.split()), reverse=True)

    matched_words: list[str] = []
    missing_words: list[str] = []
    phrase_hits: list[str] = []

    \
\
    units: list[dict[str, Any]] = []
    i = 0
    while i < len(words):
        phrase_matched = False
        for phrase in sorted_phrases:
            p_words = phrase.split()
            if words[i : i + len(p_words)] == p_words:
                rule_glosses = PHRASE_RULES[phrase]
                valid_rule = [g for g in rule_glosses if g in available_vocab]
                if valid_rule:
                    phrase_hits.append(phrase)
                    units.append({"kind": "phrase", "glosses": valid_rule})
                    matched_words.extend(p_words)
                    i += len(p_words)
                    phrase_matched = True
                    break
        if phrase_matched:
            continue

        word = words[i]
        if word in ASL_OMITTED_WORDS:
            i += 1
            continue

        gloss = _resolve_word_to_gloss(word, available_vocab)
        if gloss:
            units.append({"kind": "word", "gloss": gloss})
            matched_words.append(word)
        else:
            missing_words.append(word)
        i += 1

    time_glosses: list[str] = []
    middle_glosses: list[str] = []
    neg_glosses: list[str] = []
    wh_glosses: list[str] = []

    for unit in units:
        if unit["kind"] == "phrase":
            middle_glosses.extend(unit["glosses"])
        else:
            g = unit["gloss"]
            if g in TIME_MARKERS and g not in time_glosses:
                time_glosses.append(g)
            elif g in WH_WORDS:
                wh_glosses.append(g)
            elif g in NEGATION_WORDS:
                neg_glosses.append(g)
            else:
                middle_glosses.append(g)

    matched_glosses = time_glosses + middle_glosses + neg_glosses + wh_glosses

    \
    deduped_glosses: list[str] = []
    for g in matched_glosses:
        if not deduped_glosses or deduped_glosses[-1] != g:
            deduped_glosses.append(g)

    if not deduped_glosses:
        asl_status = "unavailable"
    elif missing_words:
        asl_status = "partial"
    else:
        asl_status = "matched"

    return {
        "segment_id": sentence.get("id"),
        "source_text": raw_text,
        "start": float(sentence.get("start", 0.0)),
        "end": float(sentence.get("end", 0.0)),
        "asl_available": len(deduped_glosses) > 0,
        "asl_status": asl_status,
        "glosses": deduped_glosses,
        "asl_gloss_text": " · ".join(g.upper() for g in deduped_glosses),
        "phrase_matches": phrase_hits,
        "matched_words": matched_words,
        "missing_words": missing_words,
    }


def translate_sentences(
    sentences: list[dict[str, Any]],
    vocab: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    available_vocab = vocab if vocab is not None else load_available_glosses()
    return [translate_sentence(sentence, vocab=available_vocab) for sentence in sentences]
