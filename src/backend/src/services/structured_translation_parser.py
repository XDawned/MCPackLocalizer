"""
结构化翻译结果解析器

使用 LangChain 的 PydanticOutputParser 与自定义容错逻辑，
对大模型翻译批次输出进行严格约束、规范化与修复提示构建。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

_INVALID_UNICODE_ESCAPE_RE = re.compile(r"\\u(?![0-9a-fA-F]{4})")
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
_KEY_VALUE_LINE_RE = re.compile(
    r"^\s*[-*]?\s*[\"']?(?P<key>[^\"'=:]+?)[\"']?\s*(?::|=)\s*(?P<value>.+?)\s*,?\s*$"
)


class StructuredTranslationItem(BaseModel):
    """单条结构化翻译结果。"""

    key: str = Field(..., description="输入条目的稳定 key")
    translated: str = Field(
        ...,
        validation_alias=AliasChoices(
            "translated",
            "translation",
            "translated_text",
            "text",
            "value",
            "target",
        ),
        description="译文",
    )

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("key 不能为空")
        return normalized

    @field_validator("translated")
    @classmethod
    def normalize_translated(cls, value: str) -> str:
        if value is None:
            raise ValueError("translated 不能为空")
        return str(value)


class StructuredTranslationBatchPayload(BaseModel):
    """单个翻译批次的结构化结果。"""

    translations: list[StructuredTranslationItem] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_payload(cls, data: Any) -> Any:
        if data is None:
            return {"translations": []}

        if isinstance(data, list):
            return {"translations": data}

        if not isinstance(data, dict):
            return data

        if isinstance(data.get("translations"), dict):
            return {
                "translations": [
                    {"key": key, "translated": value}
                    for key, value in data["translations"].items()
                ]
            }

        if isinstance(data.get("translations"), list):
            return {"translations": data["translations"]}

        for alias in ("items", "results", "entries", "data"):
            alias_value = data.get(alias)
            if isinstance(alias_value, list):
                return {"translations": alias_value}
            if isinstance(alias_value, dict):
                return {
                    "translations": [
                        {"key": key, "translated": value}
                        for key, value in alias_value.items()
                    ]
                }

        metadata_keys = {
            "message",
            "messages",
            "note",
            "notes",
            "reason",
            "reasons",
            "explanation",
            "comment",
            "comments",
        }
        if data and not set(data.keys()) & metadata_keys:
            if all(isinstance(value, str) for value in data.values()):
                return {
                    "translations": [
                        {"key": key, "translated": value}
                        for key, value in data.items()
                    ]
                }

        return data


@dataclass(slots=True)
class ParsedTranslationBatch:
    """解析后的批次结果。"""

    translations_by_key: dict[str, str]
    missing_keys: list[str]
    unexpected_keys: list[str]
    duplicate_keys: list[str]
    candidate_text: str
    raw_text: str


class StructuredTranslationParseError(ValueError):
    """结构化解析失败异常，保留部分可恢复上下文。"""

    def __init__(
        self,
        message: str,
        raw_text: str,
        *,
        partial_translations: dict[str, str] | None = None,
        missing_keys: Sequence[str] | None = None,
        unexpected_keys: Sequence[str] | None = None,
        duplicate_keys: Sequence[str] | None = None,
        candidate_text: str | None = None,
    ):
        super().__init__(message)
        self.raw_text = raw_text
        self.partial_translations = dict(partial_translations or {})
        self.missing_keys = list(missing_keys or [])
        self.unexpected_keys = list(unexpected_keys or [])
        self.duplicate_keys = list(duplicate_keys or [])
        self.candidate_text = candidate_text or ""

    @property
    def raw_preview(self) -> str:
        return _truncate_text(self.raw_text, 1200)


class StructuredTranslationParser:
    """基于 LangChain + Pydantic 的健壮翻译结果解析器。"""

    def __init__(self, expected_keys: Sequence[str]):
        self.expected_keys = [str(key).strip() for key in expected_keys if str(key).strip()]
        self.expected_key_set = set(self.expected_keys)
        self._parser = PydanticOutputParser(pydantic_object=StructuredTranslationBatchPayload)

    def get_format_instructions(self) -> str:
        return self._parser.get_format_instructions()

    def get_structured_output_chain(self, llm: BaseChatModel):
        try:
            return llm.with_structured_output(StructuredTranslationBatchPayload, include_raw=True)
        except TypeError:
            return llm.with_structured_output(StructuredTranslationBatchPayload)

    def parse_payload(
        self,
        payload: StructuredTranslationBatchPayload | dict[str, Any] | list[Any],
        *,
        raw_text: str = "",
        candidate_text: str | None = None,
    ) -> ParsedTranslationBatch:
        normalized_payload = (
            payload
            if isinstance(payload, StructuredTranslationBatchPayload)
            else StructuredTranslationBatchPayload.model_validate(payload)
        )
        candidate = candidate_text if candidate_text is not None else _serialize_candidate_payload(normalized_payload)
        return self._normalize_payload(normalized_payload, raw_text or candidate, candidate)

    def parse(self, raw_text: str) -> ParsedTranslationBatch:
        cleaned = _strip_code_fence(raw_text or "").strip()
        if not cleaned:
            raise StructuredTranslationParseError("AI 返回空响应", raw_text)

        last_error: Exception | None = None
        best_partial_result: ParsedTranslationBatch | None = None
        for candidate in self._build_candidates(cleaned):
            payload: StructuredTranslationBatchPayload | None = None

            try:
                payload = self._parser.parse(candidate)
            except Exception as exc:
                last_error = exc
                try:
                    payload = StructuredTranslationBatchPayload.model_validate(json.loads(candidate))
                except Exception as fallback_exc:
                    last_error = fallback_exc
                    continue

            try:
                parsed_result = self._normalize_payload(payload, raw_text, candidate)
            except StructuredTranslationParseError as exc:
                last_error = exc
                continue

            if not parsed_result.missing_keys:
                return parsed_result
            if best_partial_result is None or len(parsed_result.translations_by_key) > len(best_partial_result.translations_by_key):
                best_partial_result = parsed_result

        kv_payload = self._extract_key_value_payload(cleaned)
        if kv_payload is not None:
            try:
                kv_result = self._normalize_payload(kv_payload, raw_text, cleaned)
                if not kv_result.missing_keys:
                    return kv_result
                if best_partial_result is None or len(kv_result.translations_by_key) > len(best_partial_result.translations_by_key):
                    best_partial_result = kv_result
            except StructuredTranslationParseError as exc:
                last_error = exc

        if best_partial_result is not None:
            return best_partial_result

        if _looks_like_truncated_json(cleaned):
            raise StructuredTranslationParseError(
                "模型输出疑似为半截 JSON，未形成完整结构",
                raw_text,
                candidate_text=cleaned,
            )

        error_message = str(last_error)[:500] if last_error else "未知解析错误"
        raise StructuredTranslationParseError(
            f"无法将模型输出解析为合法结构化结果：{error_message}",
            raw_text,
            candidate_text=cleaned,
        )

    def build_repair_messages(
        self,
        source_texts: Sequence[dict[str, Any]],
        invalid_output: str,
        error_message: str,
        *,
        custom_prompt: str | None = None,
    ) -> list[dict[str, str]]:
        source_map = {
            str(item.get("key", "")).strip(): str(item.get("original", ""))
            for item in source_texts
            if str(item.get("key", "")).strip()
        }

        prompt_sections = [
            "You repair malformed Minecraft EN->zh-CN translation outputs.",
            "Return JSON only. Do not add markdown fences, explanations, prefixes, or suffixes.",
            "You must keep every input key exactly once and preserve placeholders/codes unchanged.",
            self.get_format_instructions(),
        ]
        if custom_prompt and custom_prompt.strip():
            prompt_sections.append(f"User requirements:\n{custom_prompt.strip()}")

        system_prompt = "\n\n".join(prompt_sections)
        user_prompt = (
            "The previous translation output is invalid and must be repaired.\n"
            f"Validation error: {_truncate_text(error_message, 500)}\n\n"
            f"Source texts JSON:\n{json.dumps(source_map, ensure_ascii=False, separators=(",", ":"))}\n\n"
            f"Previous invalid output:\n{_truncate_text(invalid_output, 6000)}\n\n"
            "Return the full corrected result for all keys."
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _normalize_payload(
        self,
        payload: StructuredTranslationBatchPayload,
        raw_text: str,
        candidate_text: str,
    ) -> ParsedTranslationBatch:
        translations_by_key: dict[str, str] = {}
        duplicate_keys: list[str] = []

        for entry in payload.translations:
            key = str(entry.key).strip()
            translated = str(entry.translated)
            if key in translations_by_key:
                duplicate_keys.append(key)
            if translated == "":
                continue
            translations_by_key[key] = translated

        filtered_translations = {
            key: translations_by_key[key]
            for key in self.expected_keys
            if key in translations_by_key
        }
        unexpected_keys = [
            key for key in translations_by_key.keys()
            if key not in self.expected_key_set
        ]
        missing_keys = [
            key for key in self.expected_keys
            if key not in filtered_translations
        ]

        if not filtered_translations:
            raise StructuredTranslationParseError(
                "结构化结果中未找到任何预期的翻译条目",
                raw_text,
                partial_translations={},
                missing_keys=missing_keys,
                unexpected_keys=unexpected_keys,
                duplicate_keys=duplicate_keys,
                candidate_text=candidate_text,
            )

        return ParsedTranslationBatch(
            translations_by_key=filtered_translations,
            missing_keys=missing_keys,
            unexpected_keys=unexpected_keys,
            duplicate_keys=duplicate_keys,
            candidate_text=candidate_text,
            raw_text=raw_text,
        )

    def _build_candidates(self, cleaned_text: str) -> list[str]:
        candidates: list[str] = []

        def add_candidate(value: str | None):
            if not value:
                return
            candidate = value.strip()
            if not candidate:
                return
            if candidate not in candidates:
                candidates.append(candidate)

        add_candidate(cleaned_text)

        for fragment in _extract_json_fragments(cleaned_text):
            add_candidate(fragment)

        for opener, closer in (("{", "}"), ("[", "]")):
            start = cleaned_text.find(opener)
            end = cleaned_text.rfind(closer)
            if start != -1 and end != -1 and end > start:
                add_candidate(cleaned_text[start:end + 1])

        for candidate in list(candidates):
            for repaired in _repair_json_candidates(candidate):
                add_candidate(repaired)

        return candidates

    def _extract_key_value_payload(self, text: str) -> StructuredTranslationBatchPayload | None:
        translations: list[dict[str, str]] = []

        for line in text.splitlines():
            parsed_entry = _parse_key_value_line(line)
            if not parsed_entry:
                continue
            key, translated = parsed_entry
            if key not in self.expected_key_set:
                continue
            translations.append({"key": key, "translated": translated})

        if not translations:
            return None

        return StructuredTranslationBatchPayload.model_validate({"translations": translations})


def _strip_code_fence(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_json_fragments(text: str) -> list[str]:
    fragments: list[str] = []
    start_index: int | None = None
    stack: list[str] = []
    in_string = False
    escaped = False

    pairs = {"{": "}", "[": "]"}
    closers = set(pairs.values())

    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if start_index is None:
            if char in pairs:
                start_index = index
                stack.append(pairs[char])
            continue

        if char in pairs:
            stack.append(pairs[char])
            continue

        if char in closers:
            if not stack or char != stack[-1]:
                start_index = None
                stack.clear()
                continue
            stack.pop()
            if not stack and start_index is not None:
                fragments.append(text[start_index:index + 1])
                start_index = None

    return fragments


def _repair_json_candidates(text: str) -> list[str]:
    repaired_candidates: list[str] = []

    def add_candidate(value: str | None):
        if not value:
            return
        candidate = value.strip()
        if not candidate:
            return
        if candidate not in repaired_candidates:
            repaired_candidates.append(candidate)

    stripped = text.strip()
    add_candidate(_escape_invalid_unicode_sequences(stripped))
    add_candidate(_remove_trailing_commas(stripped))
    add_candidate(_close_truncated_json(stripped))
    add_candidate(_sanitize_json_candidate(stripped))
    add_candidate(_remove_trailing_commas(_close_truncated_json(stripped)))
    add_candidate(_close_truncated_json(_remove_trailing_commas(stripped)))
    add_candidate(_close_truncated_json(_escape_invalid_unicode_sequences(stripped)))
    add_candidate(_sanitize_json_candidate(_remove_trailing_commas(stripped)))

    return repaired_candidates


def _sanitize_json_candidate(text: str) -> str:
    candidate = _escape_invalid_unicode_sequences(text or "")
    candidate = _close_truncated_json(candidate)
    candidate = _remove_trailing_commas(candidate)
    return candidate.strip()


def _escape_invalid_unicode_sequences(text: str) -> str:
    value = str(text or "")
    if "\\u" not in value:
        return value

    repaired: list[str] = []
    index = 0
    while index < len(value):
        if value[index] == "\\" and index + 1 < len(value) and value[index + 1] == "u":
            hex_part = value[index + 2:index + 6]
            if len(hex_part) == 4 and all(char in "0123456789abcdefABCDEF" for char in hex_part):
                repaired.append(value[index:index + 6])
                index += 6
                continue
            repaired.append("\\\\u")
            index += 2
            continue

        repaired.append(value[index])
        index += 1

    return "".join(repaired)


def _remove_trailing_commas(text: str) -> str:
    return _TRAILING_COMMA_RE.sub(r"\1", text or "")


def _close_truncated_json(text: str) -> str:
    value = str(text or "")
    if not value:
        return value

    stack: list[str] = []
    in_string = False
    escaped = False
    pairs = {"{": "}", "[": "]"}

    for char in value:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char in pairs:
            stack.append(pairs[char])
        elif char in pairs.values() and stack and char == stack[-1]:
            stack.pop()

    suffix = ""
    if escaped:
        suffix += "\\"
    if in_string:
        suffix += '"'
    if stack:
        suffix += "".join(reversed(stack))
    return value + suffix


def _parse_key_value_line(line: str) -> tuple[str, str] | None:
    stripped = str(line or "").strip()
    if not stripped or stripped in {"{", "}", "[", "]"}:
        return None

    match = _KEY_VALUE_LINE_RE.match(stripped)
    if not match:
        return None

    key = str(match.group("key") or "").strip()
    if not key:
        return None

    value = _normalize_scalar_value(match.group("value") or "")
    return key, value


def _normalize_scalar_value(value: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return ""

    if len(candidate) >= 2 and candidate[0] == candidate[-1] and candidate[0] in {"\"", "'"}:
        quote = candidate[0]
        if quote == '"':
            try:
                repaired = _escape_invalid_unicode_sequences(candidate)
                return str(json.loads(repaired))
            except Exception:
                return candidate[1:-1]
        return (
            candidate[1:-1]
            .replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace("\\r", "\r")
            .replace("\\'", "'")
            .replace('\\"', '"')
        )

    if candidate.lower() in {"null", "none"}:
        return ""

    return candidate


def _looks_like_truncated_json(text: str) -> bool:
    stack: list[str] = []
    in_string = False
    escaped = False
    pairs = {"{": "}", "[": "]"}

    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char in pairs:
            stack.append(pairs[char])
        elif char in pairs.values():
            if stack and char == stack[-1]:
                stack.pop()

    return bool(stack or in_string or _INVALID_UNICODE_ESCAPE_RE.search(text or ""))


def _serialize_candidate_payload(payload: StructuredTranslationBatchPayload | BaseModel | dict[str, Any] | list[Any]) -> str:
    if isinstance(payload, BaseModel):
        return json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)
    return json.dumps(payload, ensure_ascii=False)


def _truncate_text(text: str, limit: int) -> str:
    value = str(text or "")
    if len(value) <= limit:
        return value
    return value[:limit] + "...(truncated)"
