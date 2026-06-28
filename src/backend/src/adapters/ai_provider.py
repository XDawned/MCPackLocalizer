"""
AI Provider Adapter

Provides a unified interface for multiple AI/LLM providers used for
Minecraft modpack translation. Supports OpenAI, Anthropic, DeepSeek,
Qwen (Alibaba), Zhipu, and Ollama.

Also provides:
- Base URL normalization
- Model list fetching (via /models endpoint for OpenAI-compatible providers)
- API connectivity / authentication testing
"""

import asyncio
import json
import logging
import os
import time
from typing import Optional, List
from urllib.parse import urlparse, urlunparse

import httpx

try:
    from ..config import settings
except ImportError:
    from src.config import settings  # type: ignore

logger = logging.getLogger(__name__)

PROVIDER_CONFIGS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "ollama": "http://localhost:11434/v1",
}

DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o",
    "anthropic": "claude-3-5-sonnet-20241022",
    "deepseek": "deepseek-chat",
    "qwen": "qwen-plus",
    "zhipu": "glm-4",
    "ollama": "llama3",
}

# Providers that use OpenAI-compatible /models endpoint
OPENAI_COMPATIBLE_PROVIDERS = {"openai", "deepseek", "qwen", "zhipu", "ollama"}


def normalize_api_base(url: Optional[str], provider_type: Optional[str] = None) -> Optional[str]:
    """
    Normalize an API base URL.

    - Strip trailing slashes
    - Ensure scheme is present (default https)
    - Remove common redundant path segments
    - Return default for provider_type if url is empty

    Args:
        url: The raw API base URL.
        provider_type: Provider type key for fallback defaults.

    Returns:
        Normalized URL string, or None if no URL and no default.
    """
    if not url or not url.strip():
        if provider_type and provider_type in PROVIDER_CONFIGS:
            return PROVIDER_CONFIGS[provider_type]
        return None

    url = url.strip().rstrip("/")

    # Ensure scheme
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # Parse and reconstruct to normalize
    parsed = urlparse(url)
    # Remove common redundant path segments like /v1/v1
    path = parsed.path
    while "/v1/v1" in path:
        path = path.replace("/v1/v1", "/v1")

    normalized = urlunparse((
        parsed.scheme,
        parsed.netloc,
        path,
        parsed.params,
        parsed.query,
        "",  # strip fragment
    ))

    return normalized


class AIProvider:
    """Unified AI provider client for translation tasks."""

    def __init__(
        self,
        provider_type: str,
        api_key: str,
        api_base: str | None = None,
        model: str = "gpt-4o",
    ):
        self.provider_type = provider_type
        self.api_key = api_key
        self.api_base = normalize_api_base(api_base, provider_type) or PROVIDER_CONFIGS.get(provider_type, "")
        self.model = model

    async def translate(self, messages: list[dict], **kwargs) -> dict:
        """
        Send translation request to the AI provider.

        Includes automatic retry with exponential backoff for transient errors
        (timeouts, 429 rate-limits, and 5xx server errors).

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            **kwargs: Additional parameters passed to the API request body.

        Returns:
            dict with keys: text, tokens_used, model, (error on failure)
        """
        max_retries = kwargs.pop("max_retries", None) or settings.AI_MAX_RETRIES
        retry_delay = kwargs.pop("retry_delay", None) or settings.AI_RETRY_DELAY

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                if self.provider_type == "anthropic":
                    return await self._translate_anthropic(messages, **kwargs)
                else:
                    return await self._translate_openai_compatible(messages, **kwargs)
            except httpx.TimeoutException:
                last_error = "Request timed out"
                if attempt < max_retries:
                    wait = retry_delay * (2 ** attempt)
                    logger.warning(
                        "[%s] Request timed out (attempt %d/%d), retrying in %.1fs...",
                        self.provider_type, attempt + 1, max_retries + 1, wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "[%s] Request timed out after %d attempts",
                        self.provider_type, max_retries + 1,
                    )
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                # Retry on 429 (rate limit) and 5xx (server error)
                if status_code in (429, *range(500, 600)) and attempt < max_retries:
                    wait = retry_delay * (2 ** attempt)
                    logger.warning(
                        "[%s] HTTP %d (attempt %d/%d), retrying in %.1fs...",
                        self.provider_type, status_code, attempt + 1, max_retries + 1, wait,
                    )
                    await asyncio.sleep(wait)
                    last_error = f"HTTP {status_code}: {e.response.text[:200]}"
                else:
                    logger.error(
                        "[%s] HTTP error: %s - %s",
                        self.provider_type,
                        status_code,
                        e.response.text[:500],
                    )
                    return {
                        "text": "",
                        "tokens_used": 0,
                        "error": f"HTTP {status_code}: {e.response.text[:200]}",
                    }
            except Exception as e:
                logger.exception("[%s] Unexpected error: %s", self.provider_type, e)
                return {"text": "", "tokens_used": 0, "error": str(e)}

        return {"text": "", "tokens_used": 0, "error": last_error or "Request timed out"}

    async def _translate_openai_compatible(
        self, messages: list[dict], **kwargs
    ) -> dict:
        """Handle OpenAI-compatible APIs (openai, deepseek, qwen, ollama, zhipu)."""
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.3),
            "max_tokens": kwargs.get("max_tokens", 384000),
        }
        payload.update(
            {k: v for k, v in kwargs.items() if k not in ("temperature", "max_tokens")}
        )

        async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]
        content = choice["message"]["content"]
        usage = data.get("usage", {})
        tokens_used = usage.get("total_tokens", 0)
        model_used = data.get("model", self.model)

        logger.info(
            "[%s] Translation completed: tokens=%d, model=%s",
            self.provider_type,
            tokens_used,
            model_used,
        )

        return {
            "text": content,
            "tokens_used": tokens_used,
            "model": model_used,
        }

    async def _translate_anthropic(self, messages: list[dict], **kwargs) -> dict:
        """Handle Anthropic Messages API."""
        url = f"{self.api_base}/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": kwargs.get("anthropic_version", "2023-06-01"),
            "Content-Type": "application/json",
        }

        system_content = None
        api_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            else:
                api_messages.append(msg)

        payload = {
            "model": self.model,
            "max_tokens": kwargs.get("max_tokens", 65535),
            "messages": api_messages,
            "temperature": kwargs.get("temperature", 0.3),
        }
        if system_content:
            payload["system"] = system_content

        processed = {"temperature", "max_tokens", "anthropic_version"}
        payload.update({k: v for k, v in kwargs.items() if k not in processed})

        async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        content_blocks = data.get("content", [])
        text = ""
        for block in content_blocks:
            if block.get("type") == "text":
                text += block.get("text", "")

        usage = data.get("usage", {})
        tokens_used = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        model_used = data.get("model", self.model)

        logger.info(
            "[%s] Translation completed: tokens=%d, model=%s",
            self.provider_type,
            tokens_used,
            model_used,
        )

        return {
            "text": text,
            "tokens_used": tokens_used,
            "model": model_used,
        }

    async def translate_batch(
        self,
        messages_list: list[list[dict]],
        concurrency: int = 3,
    ) -> list[dict]:
        """
        Batch translate multiple message lists with concurrency control.

        Args:
            messages_list: List of message list batches to translate.
            concurrency: Maximum concurrent requests.

        Returns:
            List of result dicts in the same order as input.
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def _bounded_translate(messages: list[dict]) -> dict:
            async with semaphore:
                return await self.translate(messages)

        tasks = [_bounded_translate(msgs) for msgs in messages_list]
        results = await asyncio.gather(*tasks)
        return list(results)

    # ------------------------------------------------------------------ #
    #  Model listing & API testing
    # ------------------------------------------------------------------ #

    async def fetch_models(self) -> List[dict]:
        """
        Fetch available models from the provider.

        For OpenAI-compatible providers, calls GET /models.
        For Anthropic, calls GET /models.
        For Ollama, calls GET /tags (Ollama-specific).

        Returns:
            List of dicts with keys: id, name (optional), owned_by (optional).

        Raises:
            httpx.HTTPStatusError: On HTTP errors.
            httpx.TimeoutException: On timeout.
            ValueError: On unexpected response format.
        """
        if self.provider_type == "anthropic":
            return await self._fetch_models_anthropic()
        elif self.provider_type == "ollama":
            return await self._fetch_models_ollama()
        else:
            return await self._fetch_models_openai_compatible()

    async def _fetch_models_openai_compatible(self) -> List[dict]:
        """Fetch models from OpenAI-compatible /models endpoint."""
        url = f"{self.api_base}/models"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

        models_raw = data.get("data", [])
        if not isinstance(models_raw, list):
            raise ValueError("Unexpected response format: 'data' is not a list")

        result = []
        for m in models_raw:
            model_id = m.get("id", "")
            if model_id:
                result.append({
                    "id": model_id,
                    "name": m.get("name") or m.get("id"),
                    "owned_by": m.get("owned_by"),
                })

        # Sort by id for consistent ordering
        result.sort(key=lambda x: x["id"])
        return result

    async def _fetch_models_anthropic(self) -> List[dict]:
        """Fetch models from Anthropic /models endpoint."""
        url = f"{self.api_base}/models"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

        models_raw = data.get("data", [])
        if not isinstance(models_raw, list):
            raise ValueError("Unexpected response format: 'data' is not a list")

        result = []
        for m in models_raw:
            model_id = m.get("id", "")
            if model_id:
                result.append({
                    "id": model_id,
                    "name": m.get("display_name") or m.get("id"),
                    "owned_by": m.get("owned_by", "anthropic"),
                })

        result.sort(key=lambda x: x["id"])
        return result

    async def _fetch_models_ollama(self) -> List[dict]:
        """Fetch models from Ollama /tags endpoint (Ollama-specific)."""
        # Ollama uses a different endpoint: /api/tags
        # But when api_base ends with /v1, we need to adjust
        base = self.api_base
        if base.endswith("/v1"):
            base = base[:-3]

        url = f"{base}/api/tags"
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

        models_raw = data.get("models", [])
        if not isinstance(models_raw, list):
            raise ValueError("Unexpected response format: 'models' is not a list")

        result = []
        for m in models_raw:
            model_id = m.get("name", "")
            if model_id:
                result.append({
                    "id": model_id,
                    "name": model_id,
                    "owned_by": "ollama",
                })

        result.sort(key=lambda x: x["id"])
        return result

    async def test_connection(self, model: Optional[str] = None) -> dict:
        """
        Test API connectivity and authentication.

        Sends a minimal chat completion request to verify the provider
        configuration is working.

        Args:
            model: Model to test with. If None, uses self.model.

        Returns:
            dict with keys:
              - success (bool)
              - message (str): Human-readable result
              - latency_ms (int): Round-trip time in milliseconds
              - model_used (str): The model that was actually used
        """
        test_model = model or self.model
        start = time.monotonic()

        try:
            if self.provider_type == "anthropic":
                result = await self._test_anthropic(test_model)
            else:
                result = await self._test_openai_compatible(test_model)

            elapsed_ms = int((time.monotonic() - start) * 1000)
            result["latency_ms"] = elapsed_ms
            return result

        except httpx.HTTPStatusError as e:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            status = e.response.status_code
            if status == 401:
                msg = "认证失败：API密钥无效或已过期"
            elif status == 403:
                msg = "访问被拒绝：权限不足"
            elif status == 404:
                msg = f"模型不存在或端点不可用 (HTTP 404)"
            elif status == 429:
                msg = "请求频率超限，请稍后重试"
            elif status >= 500:
                msg = f"服务端错误 (HTTP {status})"
            else:
                msg = f"请求失败 (HTTP {status})"
            return {
                "success": False,
                "message": msg,
                "latency_ms": elapsed_ms,
                "model_used": test_model,
            }
        except httpx.TimeoutException:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return {
                "success": False,
                "message": "连接超时，请检查网络或API地址是否正确",
                "latency_ms": elapsed_ms,
                "model_used": test_model,
            }
        except httpx.ConnectError:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return {
                "success": False,
                "message": "无法连接到API服务，请检查API地址是否正确",
                "latency_ms": elapsed_ms,
                "model_used": test_model,
            }
        except Exception as e:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.exception("[%s] Test connection unexpected error", self.provider_type)
            return {
                "success": False,
                "message": f"测试失败：{str(e)[:200]}",
                "latency_ms": elapsed_ms,
                "model_used": test_model,
            }

    async def _test_openai_compatible(self, model: str) -> dict:
        """Test OpenAI-compatible provider by sending a minimal completion request."""
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 5,
            "temperature": 0,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        model_used = data.get("model", model)
        return {
            "success": True,
            "message": "连接测试成功",
            "model_used": model_used,
        }

    async def _test_anthropic(self, model: str) -> dict:
        """Test Anthropic provider by sending a minimal messages request."""
        url = f"{self.api_base}/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": 5,
            "messages": [{"role": "user", "content": "Hi"}],
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        model_used = data.get("model", model)
        return {
            "success": True,
            "message": "连接测试成功",
            "model_used": model_used,
        }


def get_ai_provider(
    provider_id_or_type: str,
    db_session=None,
) -> AIProvider:
    """
    Factory function to get a configured AIProvider instance.

    If db_session is provided, queries the ai_providers table by ID.
    Otherwise, falls back to environment variables and defaults.

    Args:
        provider_id_or_type: Provider ID (int string when db_session given)
                             or provider type string.
        db_session: SQLAlchemy database session (optional).

    Returns:
        Configured AIProvider instance.
    """
    if db_session is not None:
        try:
            from ..models.settings import AIProvider as AIProviderModel
        except ImportError:
            from src.models.settings import AIProvider as AIProviderModel  # type: ignore

        provider_id = int(provider_id_or_type)
        db_provider = (
            db_session.query(AIProviderModel)
            .filter(
                AIProviderModel.id == provider_id,
                AIProviderModel.is_enabled == True,
            )
            .first()
        )

        if db_provider:
            provider_type = db_provider.provider_type
            api_key = db_provider.api_key_encrypted or ""
            api_base = db_provider.api_base or None
            model = db_provider.default_model or DEFAULT_MODELS.get(
                provider_type, "gpt-4o"
            )
            return AIProvider(
                provider_type=provider_type,
                api_key=api_key,
                api_base=api_base,
                model=model,
            )

        logger.warning(
            "AI provider id=%d not found in database, falling back to defaults",
            provider_id,
        )

    provider_type = provider_id_or_type
    env_key_map = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "qwen": "QWEN_API_KEY",
        "zhipu": "ZHIPU_API_KEY",
        "ollama": "OLLAMA_API_KEY",
    }
    env_key = env_key_map.get(provider_type, f"{provider_type.upper()}_API_KEY")
    api_key = os.getenv(env_key, "")
    model = os.getenv(
        f"{provider_type.upper()}_MODEL",
        DEFAULT_MODELS.get(provider_type, "gpt-4o"),
    )

    return AIProvider(
        provider_type=provider_type,
        api_key=api_key,
        api_base=None,
        model=model,
    )


def build_translation_messages(
    source_texts: list[dict],
    glossary_terms: list[dict] | None = None,
    custom_prompt: str | None = None,
) -> list[dict]:
    """
    Build compact messages for AI translation with a Minecraft-focused prompt.

    Args:
        source_texts: List of dicts with 'key' and 'original' (English) text.
        glossary_terms: Optional list of dicts with 'source' and 'target' terms.
        custom_prompt: Optional user-supplied prompt appended after the default
            system prompt. When non-empty, it is appended as an additional
            requirement section while preserving the default prompt and output
            format constraint intact.

    Returns:
        List of message dicts ready for AIProvider.translate().
    """
    glossary_section = ""
    if glossary_terms:
        terms_lines = []
        for term in glossary_terms:
            src = term.get("source", term.get("term", ""))
            tgt = term.get("target", term.get("translation", ""))
            if src and tgt:
                terms_lines.append(f"- {src} => {tgt}")
        if terms_lines:
            glossary_section = "Glossary (use exact translations):\n" + "\n".join(
                terms_lines
            )

    compact_source_texts: dict[str, str] = {}
    for item in source_texts:
        key = str(item.get("key", "")).strip()
        if key != "":
            compact_source_texts[key] = str(item.get("original", ""))

    prompt_sections = [
        "You are an expert Minecraft mod EN->zh-CN translator.",
        "Rules:\n"
        "1. Follow Minecraft community conventions.\n"
        "2. Preserve placeholders/codes exactly: %s, %d, {0}, §, color codes, escapes.\n"
        "3. Keep technical abbreviations like RF when appropriate.\n"
        "4. Translate only text values; never add, remove, or rename keys.\n"
        "5. Return JSON only, without markdown or explanations.\n"
        '6. Output format: {"translations":{"<key>":"<translated_text>"}}\n'
        "7. Every input key must appear exactly once; do not repeat source text.",
    ]
    if glossary_section:
        prompt_sections.append(glossary_section)
    if custom_prompt and custom_prompt.strip():
        prompt_sections.append(f"User requirements:\n{custom_prompt.strip()}")

    system_prompt = "\n\n".join(prompt_sections)
    texts_json = json.dumps(compact_source_texts, ensure_ascii=False, separators=(",", ":"))
    user_prompt = (
        "Translate this JSON object. Keys are lookup IDs and must stay unchanged; "
        "values are the source texts.\n"
        f"{texts_json}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def estimate_cost(model: str, tokens_used: int) -> float:
    """
    Estimate translation cost in RMB based on model and token usage.

    Uses average rates (blended input/output) per 1K tokens.

    Args:
        model: Model identifier string.
        tokens_used: Total tokens consumed.

    Returns:
        Estimated cost in RMB.
    """
    pricing: dict[str, tuple[float, float]] = {
        "deepseek-v4-pro": (3.0, 6.0),
        "deepseek-v4-flash": (1.0, 2.0),
    }

    input_price, output_price = (0.0, 0.0)
    for key, prices in pricing.items():
        if key in model.lower():
            input_price, output_price = prices
            break

    input_tokens = int(tokens_used * 0.7)
    output_tokens = tokens_used - input_tokens

    cost = (input_tokens / 1000000) * input_price + (output_tokens / 1000000) * output_price
    return round(cost, 6)
