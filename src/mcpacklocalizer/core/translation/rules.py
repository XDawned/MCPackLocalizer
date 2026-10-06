"""Literal, case-sensitive no-translate terms with ASCII word boundaries."""
from __future__ import annotations

import hashlib
import re
from collections import Counter


class NoTranslate:
    def __init__(self, text=""):
        terms = sorted({line.strip() for line in text.splitlines() if line.strip()}, key=lambda s: (-len(s), s))
        self.pattern = re.compile("|".join(
            (r"(?<![A-Za-z0-9_])" if term[0].isascii() and term[0].isalnum() else "")
            + re.escape(term)
            + (r"(?![A-Za-z0-9_])" if term[-1].isascii() and term[-1].isalnum() else "")
            for term in terms)) if terms else None

    def mask(self, source):
        from .local import PROTECTED
        if not self.pattern:
            return source, {}
        reserved = [(m.start(), m.end()) for m in PROTECTED.finditer(source)]
        mapping = {}
        prefix = "MCPL_KEEP_" + hashlib.sha256(source.encode()).hexdigest()[:8] + "_"
        while prefix in source:
            prefix += "X"

        def replace(match):
            if any(match.start() < end and start < match.end() for start, end in reserved):
                return match.group()
            marker = "{{" + prefix + str(len(mapping)) + "}}"
            mapping[marker] = match.group()
            return marker

        return self.pattern.sub(replace, source), mapping

    @staticmethod
    def restore(text, mapping):
        if any(text.count(marker) != 1 for marker in mapping):
            raise ValueError("禁翻词条占位符丢失或重复")
        # A single substitution prevents a restored literal from becoming a marker.
        return re.sub("|".join(map(re.escape, mapping)), lambda m: mapping[m.group()], text) if mapping else text

    def validate(self, source, translation):
        if self.pattern and Counter(self.pattern.findall(source)) != Counter(self.pattern.findall(translation)):
            raise ValueError("译文修改了禁翻词条")
