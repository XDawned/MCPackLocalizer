# [Module: translation.api] [Status: 已完成] [Brief: 多协议 API 翻译、响应提取与有限重试]
from __future__ import annotations

import json
import math
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import uuid4

import httpx

from ... import __version__
from .glossary import Glossary
from .local import (
    DEFAULT_GLOSSARY,
    PROTECTED,
    ModelConfig,
    preservation_rules,
    protect_braces,
    render_prompt,
    render_system_prompt,
    restore_braces,
    validate,
)
from .locales import language_name, validate_pair
from .response import extract_translation, output_instruction, strip_thinking
from .rules import NoTranslate

PROTOCOLS = ("openai", "anthropic", "gemini")


def endpoint(base_url, protocol, model=""):
    parts = urlsplit(base_url.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc or parts.username or parts.password:
        raise ValueError("接口地址必须是有效的 http(s) URL，且不能包含用户名或密码")
    if parts.query or parts.fragment:
        raise ValueError("接口地址不能包含查询参数或片段；API Key 请填入密钥栏")
    path = parts.path.rstrip("/")
    if protocol == "openai":
        if not path.endswith("/chat/completions"):
            path = (path or "/v1") + "/chat/completions"
    elif protocol == "anthropic":
        if not path.endswith("/messages"):
            path = (path or "/v1") + "/messages"
    elif protocol == "gemini":
        if "/models/" in path:
            path = path.split("/models/", 1)[0]
        path = (path or "/v1beta") + "/models/" + quote(model.removeprefix("models/"), safe="") + ":generateContent"
    else:
        raise ValueError("未知接口协议")
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def extra_parameters(text):
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ValueError("扩展请求参数必须是 JSON 对象") from exc
    if not isinstance(data, dict):
        raise ValueError("扩展请求参数必须是 JSON 对象")  # noqa: TRY004 -- configuration errors share a UI path
    reserved = {"model", "messages", "system", "contents", "systemInstruction", "stream", "n",
                "max_tokens", "max_completion_tokens", "temperature", "generationConfig", "api_key", "key",
                "system_instruction", "generation_config", "candidateCount"}
    if reserved.intersection(data):
        raise ValueError("扩展参数不能覆盖模型、提示词、流式开关、输出上限、温度或密钥")
    return data


@dataclass
class ApiProfile:
    id: str = ""
    name: str = "新接口"
    protocol: str = "openai"
    base_url: str = "http://127.0.0.1:1234/v1"
    model: str = ""
    api_key: str = field(default="", repr=False)
    key_env: str = ""
    prompt_mode: str = "custom"
    temperature: float = 0.3
    send_temperature: bool = True
    token_parameter: str = "max_tokens"
    extra_body: str = "{}"
    group: str = "auto"
    context_size: int = 8192
    max_tokens: int = 2048
    term_tokens: int = 1024
    timeout: int = 300
    concurrency: int = 3
    retries: int = 2
    request_interval: float = 1.0

    def validate(self, *, require_model=True):
        for name in ("id", "name", "protocol", "base_url", "model", "api_key", "key_env", "prompt_mode",
                     "token_parameter", "extra_body", "group"):
            if not isinstance(getattr(self, name), str):
                raise ValueError(f"接口 {name} 必须是文本")  # noqa: TRY004 -- configuration errors share a UI path
        if not self.id or not self.name.strip():
            raise ValueError("接口标识和名称不能为空")
        if self.protocol not in PROTOCOLS or self.prompt_mode not in {"custom", "hy_mt"}:
            raise ValueError("请选择有效的接口协议和提示词模式")
        if self.group not in {"auto", "local", "online", "custom"}:
            raise ValueError("请选择有效的接口分组")
        if self.protocol != "openai" and self.prompt_mode == "hy_mt":
            raise ValueError("HY-MT-2 的 API 模式使用 OpenAI 兼容协议")
        if require_model and not self.model.strip():
            raise ValueError("请填写 API 模型名称")
        if self.key_env and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.key_env):
            raise ValueError("密钥环境变量名称无效")
        if type(self.send_temperature) is not bool:
            raise ValueError("温度开关必须是布尔值")
        if type(self.temperature) not in (int, float) or not math.isfinite(self.temperature) or not 0 <= self.temperature <= 2:
            raise ValueError("API 温度必须在 0 至 2 之间")
        if self.protocol == "anthropic" and self.send_temperature and self.temperature > 1:
            raise ValueError("Anthropic 温度不能超过 1")
        if self.token_parameter not in {"max_tokens", "max_completion_tokens"}:
            raise ValueError("输出 token 参数无效")
        for name, minimum, maximum in (
            ("context_size", 256, 131072), ("max_tokens", 1, 32768), ("term_tokens", 0, 32768),
            ("timeout", 1, 86400), ("concurrency", 1, 32), ("retries", 0, 10),
        ):
            if type(getattr(self, name)) is not int or not minimum <= getattr(self, name) <= maximum:
                raise ValueError(f"接口 {name} 必须在 {minimum} 至 {maximum} 之间")
        if self.max_tokens >= self.context_size:
            raise ValueError("接口输出 token 上限必须小于上下文长度")
        if (type(self.request_interval) not in (int, float) or not math.isfinite(self.request_interval)
                or not 0 <= self.request_interval <= 60):
            raise ValueError("接口请求间隔必须在 0 至 60 秒之间")
        endpoint(self.base_url, self.protocol, self.model)
        extra_parameters(self.extra_body)

    def resolved_key(self):
        if self.key_env:
            key = os.getenv(self.key_env, "")
            if not key:
                raise ValueError(f"密钥环境变量 {self.key_env} 未设置")
            return key
        return self.api_key.strip()


def validate_api_config(config):
    validate_pair(config.source_locale, config.target_locale)
    if config.api_prompt_mode == "hy_mt" and config.target_locale != "zh_cn":
        raise ValueError("HY-MT-2 固定模板输出中文；其它译文语言请选择 MC 提示词模式")
    ApiProfile(id=config.api_profile_id or "api", protocol=config.api_protocol, base_url=config.api_base_url,
               model=config.api_model, key_env=config.api_key_env, prompt_mode=config.api_prompt_mode,
               temperature=config.api_temperature, send_temperature=config.api_send_temperature,
               token_parameter=config.api_token_parameter, extra_body=config.api_extra_body).validate()


class ApiClient:
    def __init__(self, config: ModelConfig, credentials=None, timeout=300):
        validate_api_config(config)
        self.config = config
        self.key = (credentials or {}).get(config.api_profile_id, "")
        if config.api_key_env:
            self.key = os.getenv(config.api_key_env, "")
            if not self.key:
                raise ValueError(f"密钥环境变量 {config.api_key_env} 未设置")
        self.timeout = timeout
        self.url = endpoint(config.api_base_url, config.api_protocol, config.api_model)
        self.session_id = uuid4().hex
        self.lock = threading.Lock()
        self.next_request = 0.0
        self.usage = {"requests": 0, "input_tokens": 0, "output_tokens": 0}
        self.info = {"backend": "api", "protocol": config.api_protocol, "model": config.api_model,
                     "profile_id": config.api_profile_id}
        self.no_translate = NoTranslate(config.non_translate)
        preset = config.glossary
        if (preset and Path(preset).resolve() == DEFAULT_GLOSSARY.resolve()
                and not (config.source_locale.startswith("en_") and config.target_locale == "zh_cn")):
            preset = None
        self.glossary = Glossary(Path(preset) if preset else None,
                                 Path(config.overrides) if config.overrides else None, inline=config.glossary_inline)

    def __enter__(self):
        # Build before fan-out; httpx.Client can be shared by request threads.
        if self.config.glossary or self.config.overrides or self.config.glossary_inline != "{}":
            self.glossary.find("")
        self.client = httpx.Client(timeout=self.timeout, follow_redirects=False)
        return self

    def __exit__(self, *args):
        self.client.close()

    def usage_snapshot(self):
        with self.lock:
            return self.usage.copy()

    def _payload(self, user, system):
        cfg = self.config
        headers = {"Content-Type": "application/json", "User-Agent": f"MCPackLocalizer/{__version__} (localization tool)"}
        if urlsplit(self.url).hostname == "opencode.ai":
            headers["x-opencode-session"] = self.session_id
        if cfg.api_protocol == "openai":
            if self.key:
                headers["Authorization"] = "Bearer " + self.key
            messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
            body = {"model": cfg.api_model, "messages": messages, cfg.api_token_parameter: cfg.max_tokens, "stream": False}
            if cfg.api_send_temperature:
                body["temperature"] = cfg.api_temperature
        elif cfg.api_protocol == "anthropic":
            if self.key:
                headers["x-api-key"] = self.key
            headers["anthropic-version"] = "2023-06-01"
            body = {"model": cfg.api_model, "messages": [{"role": "user", "content": user}], "max_tokens": cfg.max_tokens}
            if system:
                body["system"] = system
            if cfg.api_send_temperature:
                body["temperature"] = cfg.api_temperature
        else:
            if self.key:
                headers["x-goog-api-key"] = self.key
            generation = {"maxOutputTokens": cfg.max_tokens}
            if cfg.api_send_temperature:
                generation["temperature"] = cfg.api_temperature
            body = {"contents": [{"role": "user", "parts": [{"text": user}]}], "generationConfig": generation}
            if system:
                body["systemInstruction"] = {"parts": [{"text": system}]}
        extras = extra_parameters(cfg.api_extra_body)
        if cfg.api_protocol == "gemini":
            # Gemini's generation options live inside generationConfig.
            for key in ("topP", "topK", "thinkingConfig", "stopSequences"):
                if key in extras:
                    body["generationConfig"][key] = extras.pop(key)
        body.update(extras)
        return headers, body

    def _request(self, user, system):
        headers, body = self._payload(user, system)
        for attempt in range(self.config.retries + 1):
            with self.lock:
                delay = max(0, self.next_request - time.monotonic())
                self.next_request = time.monotonic() + delay + self.config.request_interval
            if delay:
                time.sleep(delay)
            with self.lock:
                self.usage["requests"] += 1
            try:
                response = self.client.post(self.url, headers=headers, json=body)
            except httpx.TransportError:
                if attempt >= self.config.retries:
                    raise RuntimeError("API 连接失败或超时，请检查地址、网络和超时设置") from None
                time.sleep(min(2 ** attempt, 30))
                continue
            if response.status_code in {408, 429, 500, 502, 503, 504, 529} and attempt < self.config.retries:
                retry_after = response.headers.get("Retry-After", "")
                delay = min(float(retry_after), 30) if retry_after.isdigit() else min(2 ** attempt, 30)
                time.sleep(delay)
                continue
            if not response.is_success:
                # Do not echo provider response bodies/URLs: they may contain credentials.
                hint = {401: "密钥无效", 403: "无访问权限", 404: "地址或模型不存在", 429: "请求限流",
                        400: "请求参数不兼容，可关闭温度或调整扩展参数"}.get(response.status_code, "接口请求失败")
                raise RuntimeError(f"API HTTP {response.status_code}：{hint}")
            try:
                payload = response.json()
                return self._parse(payload)
            except (KeyError, IndexError, TypeError, AttributeError, ValueError):
                raise ValueError("API 返回了无效、空、被拦截或截断的译文；请检查输出上限和模型") from None
        raise RuntimeError("API 请求失败")

    def _parse(self, data):
        protocol = self.config.api_protocol
        # Providers bill responses even when truncation/format checks reject them.
        usage = data.get("usageMetadata" if protocol == "gemini" else "usage") or {}
        inputs = usage.get("promptTokenCount" if protocol == "gemini" else "input_tokens" if protocol == "anthropic" else "prompt_tokens", 0)
        outputs = usage.get("candidatesTokenCount" if protocol == "gemini" else "output_tokens" if protocol == "anthropic" else "completion_tokens", 0)
        thought_tokens = usage.get("thoughtsTokenCount", 0) if protocol == "gemini" else 0
        with self.lock:
            self.usage["input_tokens"] += inputs if type(inputs) is int and inputs > 0 else 0
            self.usage["output_tokens"] += outputs if type(outputs) is int and outputs > 0 else 0
            self.usage["output_tokens"] += thought_tokens if type(thought_tokens) is int and thought_tokens > 0 else 0
        if protocol == "openai":
            choice = data["choices"][0]
            if choice.get("finish_reason") in {"length", "content_filter", "tool_calls", "function_call"}:
                raise ValueError("模型响应不完整")
            content = choice["message"]["content"]
            text = content if isinstance(content, str) else "".join(p["text"] for p in content if p.get("type") == "text")
        elif protocol == "anthropic":
            if data.get("stop_reason") != "end_turn":
                raise ValueError("模型响应不完整")
            text = "".join(p["text"] for p in data["content"] if p.get("type") == "text")
        else:
            choice = data["candidates"][0]
            if choice.get("finishReason") != "STOP":
                raise ValueError("模型响应不完整")
            text = "".join(p.get("text", "") for p in choice["content"]["parts"] if not p.get("thought"))
        return strip_thinking(text)

    def translate(self, source, context=""):
        body, kept = self.no_translate.mask(source)
        visible = PROTECTED.sub(" ", body)
        if not (re.search(r"[A-Za-z]", visible) if self.config.source_locale.startswith("en_") else any(c.isalpha() for c in visible)):
            return source
        terms, budget = [], 0
        matches = self.glossary.find(visible) if self.config.term_tokens else []
        for term in matches:
            # A conservative UTF-8 byte estimate avoids adding a tokenizer dependency.
            size = len(f"{term[0]} = {term[1]}\n".encode())
            if budget + size <= self.config.term_tokens:
                terms.append(term)
                budget += size
        last_error = None
        for attempt in range(2):
            masked, mapping = protect_braces(body) if attempt else (body, {})
            cfg = self.config
            template = "" if cfg.api_prompt_mode == "hy_mt" else cfg.system_prompt
            # Templates can place reference data in the system message; otherwise retain user-message injection.
            user_terms = () if "{glossary}" in template else terms
            user_context = "" if "{context}" in template else context
            if cfg.api_prompt_mode == "hy_mt":
                user = render_prompt(masked, user_terms, user_context, markers=list(mapping))
            else:
                source_label = language_name(cfg.source_locale, english=True) + f" ({cfg.source_locale})"
                target_label = language_name(cfg.target_locale, english=True) + f" ({cfg.target_locale})"
                reference = "参考术语：\n" + "\n".join(f"{key} 翻译成 {value}" for key, value in user_terms) + "\n\n" if user_terms else ""
                background = f"【背景信息】\n{user_context}\n\n" if user_context else ""
                rules = preservation_rules(masked, list(mapping)) if mapping else ""
                user = (reference + background + rules + output_instruction(masked)
                        + f"将以下 {source_label} 文本翻译为 {target_label}：\n\n" + masked)
                if attempt:
                    user = "上次响应未通过译文边界或保留符校验，请返回一个完整译文结果。\n" + user
            system = render_system_prompt(template, cfg.source_locale, cfg.target_locale, terms, context)
            if len((user + system).encode()) + self.config.max_tokens > self.config.context_size:
                raise ValueError("原文和提示词超过上下文预算，请提高上下文长度；不会截断原文")
            raw = self._request(user, system)
            try:
                raw = extract_translation(raw, masked)
                relaxed = bool(attempt and self.config.allow_missing_placeholders)
                translated = restore_braces(raw, mapping, relaxed) if attempt else raw.strip()
                validate(body, translated, relaxed)
                translated = self.no_translate.restore(translated, kept)
                self.no_translate.validate(source, translated)
                return translated
            except ValueError as exc:
                last_error = exc
        raise last_error
