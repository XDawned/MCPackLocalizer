"""MCPackLocalizer 离线推理服务

独立的 MarianMT 翻译后端，通过 HTTP 与主程序解耦。
"""
from __future__ import annotations

import os
import re
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

MAGIC_WORD = r"{xdawned}"
DEFAULT_MODEL_DIR = str(Path(__file__).parent / "models" / "minecraft-en-zh")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


class _ModelHolder:
    """线程安全、延迟加载的模型容器。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokenizer = None
        self._model = None
        self._load_error: Optional[str] = None

    @property
    def loaded(self) -> bool:
        return self._model is not None and self._tokenizer is not None

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    def load(self, model_dir: str) -> None:
        if self.loaded:
            return
        with self._lock:
            if self.loaded:
                return
            if not Path(model_dir).exists():
                self._load_error = f"模型目录不存在: {model_dir}"
                return
            from transformers import MarianMTModel, MarianTokenizer  # noqa: WPS433

            self._tokenizer = MarianTokenizer.from_pretrained(model_dir)
            self._model = MarianMTModel.from_pretrained(model_dir)
            self._load_error = None

    def translate(self, text: str) -> str:
        if not self.loaded:
            raise RuntimeError(self._load_error or "模型未加载")
        input_ids = self._tokenizer.encode(text, return_tensors="pt")
        translated = self._model.generate(input_ids, max_length=128)
        return self._tokenizer.decode(translated[0], skip_special_tokens=True)


HOLDER = _ModelHolder()


def _bracket(m: re.Match) -> str:
    return "[&" + m.group(0) + "]"


def _debracket(m: re.Match) -> str:
    return m.group(0)[2:-1]


def pre_process(text: str) -> tuple[Optional[str], str]:
    """与主程序 Translator.pre_process 行为一致。返回 (processed, original)。"""
    if text.find(".jpg") + text.find(".png") != -2:
        return None, text
    if text.find(r'{\"') != -1:
        return None, text
    processed = text.replace("\\\\&", "PPP")
    pattern = re.compile(r"&([a-z,0-9]|#[0-9,A-F]{6})")
    processed = pattern.sub(_bracket, processed)
    processed = re.sub(r'#\w+:\w+\b', MAGIC_WORD, re.sub(r'\\"', '\"', processed))
    pattern = re.compile(r'(http|https)://(?:[-\w.]|(?:%[\da-fA-F]{2}))+')
    if re.search(pattern, processed):
        return None, text
    return processed, text


def post_process(text: str, translate: str, keep_original: bool) -> str:
    """与主程序 Translator.post_process 行为一致。"""
    pattern = re.compile(r"\[&&([a-z,0-9]|#[0-9,A-F]{6})]")
    translate = pattern.sub(_debracket, translate)
    text = pattern.sub(_debracket, text)
    text = re.sub(r'(["\'])', r'\\\g<1>', text)
    quotes = re.findall(r'#\w+:\w+\b', text)
    if len(quotes) > 0:
        count = 0
        index = translate.find(MAGIC_WORD)
        while index != -1:
            translate = re.sub(MAGIC_WORD, quotes[count], translate, 1)
            count += 1
            index = translate.find(MAGIC_WORD)
    return translate + "[--" + text + "--]" if keep_original else translate


class TranslateRequest(BaseModel):
    text: str = Field(..., description="待翻译的英文原文")
    keep_original: bool = Field(False, description="是否在译文后保留原文")


class TranslateResponse(BaseModel):
    translation: str
    skipped: bool = False
    reason: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    load_error: Optional[str] = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    model_dir = os.environ.get("MCPACK_MODEL_DIR", DEFAULT_MODEL_DIR)
    try:
        HOLDER.load(model_dir)
    except Exception as exc:  # noqa: BLE001
        HOLDER._load_error = f"{type(exc).__name__}: {exc}"  # noqa: SLF001
    yield


app = FastAPI(title="MCPackLocalizer Inference", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        model_loaded=HOLDER.loaded,
        load_error=HOLDER.load_error,
    )


@app.post("/translate", response_model=TranslateResponse)
def translate(req: TranslateRequest) -> TranslateResponse:
    if not HOLDER.loaded:
        raise HTTPException(status_code=503, detail=f"模型未就绪: {HOLDER.load_error}")
    processed, original = pre_process(req.text)
    if processed is None:
        return TranslateResponse(translation=req.text, skipped=True, reason="pre_process_skipped")
    try:
        output = HOLDER.translate(processed)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"推理失败: {exc}") from exc
    return TranslateResponse(translation=post_process(original, output, req.keep_original))


def run() -> None:
    import uvicorn

    host = os.environ.get("MCPACK_HOST", DEFAULT_HOST)
    port = int(os.environ.get("MCPACK_PORT", str(DEFAULT_PORT)))
    uvicorn.run("server:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    run()
