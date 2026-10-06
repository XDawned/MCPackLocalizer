# [Module: mcpacklocalizer.core.translation.glossary] [Status: 开发中] [Brief: 格式码清理去重、可选配置的排除词表、惰性 AC 术语检索与最长优先]
from __future__ import annotations

import json
import re
from pathlib import Path

from ...paths import RESOURCES

COLOR = re.compile(r"[&§]x(?:[&§][0-9a-f]){6}|[&§](?:#[0-9a-f]{6}|[0-9a-fk-orz])", re.IGNORECASE)
# Exact whole-term filtering: never remove these words from a longer name.
# Keep material/block names (e.g. Iron, Water) even if common in ordinary English.
# The list is read from the editable config on every process start.
DEFAULT_COMMON_WORDS = RESOURCES / "glossary/common_words_en.txt"
if not DEFAULT_COMMON_WORDS.is_file():
    DEFAULT_COMMON_WORDS = Path(__file__).with_name("data") / "common_words_en.txt"


def load_common_words(path: Path | None = None) -> frozenset[str]:
    """Read the exclusion list; one term per line, lines starting with # are ignored."""
    path = DEFAULT_COMMON_WORDS if path is None else path
    if not path.is_file():
        raise FileNotFoundError(f"未找到常用词配置：{path}")
    lines = (line.strip().casefold() for line in path.read_text(encoding="utf-8-sig").splitlines())
    return frozenset(line for line in lines if line and not line.startswith("#"))


COMMON_WORDS = load_common_words()
NUMERIC_TERM = re.compile(r"[\d\s.,%+\-−–—×x/:]+", re.IGNORECASE)
# Only for exclusion lookup, not for modifying valid names or translations.
EDGE_PUNCTUATION = " \t\r\n.,!?;:'\"()[]{}…。，！？；：‘’“”«»"


def clean_term(text: str, *, filter_generic: bool = False) -> str:
    """Clean display formatting; optionally reject a glossary source term."""
    cleaned = COLOR.sub("", text).strip()
    if filter_generic and is_generic_term(cleaned.casefold()):
        return ""
    return cleaned


def normalize(text: str) -> str:
    return clean_term(text).casefold()


def is_generic_term(key: str) -> bool:
    """Exclude standalone common words and numeric expressions, not MC names."""
    bare = key.strip(EDGE_PUNCTUATION)
    return (key in COMMON_WORDS or bare in COMMON_WORDS
            or (bool(NUMERIC_TERM.fullmatch(bare)) and any(c.isdigit() for c in bare)))


class Glossary:
    def __init__(self, path: Path | None = None, overrides: Path | None = None, *, inline="{}"):
        self.path, self.overrides, self._automaton = path, overrides, None
        self.inline = inline
        self.stats = {"terms": 0, "ambiguous": 0}

    def _build(self):
        import ahocorasick
        automaton = ahocorasick.Automaton()
        terms = {}
        sources = [json.loads(path.read_text(encoding="utf-8-sig")) for path in (self.path, self.overrides) if path]
        sources.append(json.loads(self.inline))
        for data in sources:
            if not isinstance(data, dict):
                raise TypeError("术语表必须是术语到译文的 JSON 对象")
            file_terms = {}
            for term, values in data.items():
                if isinstance(values, str):
                    values = [values]
                if not isinstance(values, list):
                    continue
                term = clean_term(term, filter_generic=True)
                if not any(character.isalnum() for character in term):
                    continue
                key = normalize(term)
                if values == [] or values == [""]:
                    terms.pop(key, None)
                    file_terms.pop(key, None)
                    continue
                translations = list(dict.fromkeys(cleaned for value in values if isinstance(value, str)
                                                  and (cleaned := clean_term(value))))
                if key and translations:
                    previous = file_terms.get(key)
                    if previous:
                        translations = list(dict.fromkeys(previous[1] + translations))
                    file_terms[key] = (previous[0] if previous else term, translations)
            # Clean/deduplicate within each file first. Explicit overrides still
            # replace built-in entries, including formerly ambiguous variants.
            terms.update(file_terms)
        for key, (term, translations) in terms.items():
            if len(translations) != 1:
                self.stats["ambiguous"] += 1
                continue
            automaton.add_word(key, (key, term, translations[0]))
        if len(automaton):
            automaton.make_automaton()
        self.stats["terms"] = len(automaton)
        self._automaton = automaton

    def find(self, text: str, limit: int = 32) -> list[tuple[str, str]]:
        if self._automaton is None:
            self._build()
        if not len(self._automaton):
            return []
        normalized = normalize(text)
        matches = []
        for end, (key, term, translation) in self._automaton.iter(normalized):
            start = end - len(key) + 1
            if key[0].isalnum() and start and (normalized[start - 1].isalnum() or normalized[start - 1] == "_"):
                continue
            if key[-1].isalnum() and end + 1 < len(normalized) and (normalized[end + 1].isalnum() or normalized[end + 1] == "_"):
                continue
            matches.append((start, end + 1, key, term, translation))
        chosen = []
        for match in sorted(matches, key=lambda m: (-(m[1] - m[0]), m[0], m[2])):
            if not any(match[0] < other[1] and other[0] < match[1] for other in chosen):
                chosen.append(match)
        result = {}
        for _, _, key, term, translation in chosen:
            result.setdefault(key, (term, translation))
        return list(result.values())[:limit]
