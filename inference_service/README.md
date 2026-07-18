# MCPackLocalizer 离线推理服务

独立的本地 MarianMT 翻译后端，通过 HTTP 与主程序解耦，使用独立的 `uv` 环境，避免
`transformers` / `torch` / `tokenizers` 等大体积依赖被打入主程序包。

## 目录结构

```
inference_service/
├── pyproject.toml      # 独立依赖：transformers + torch + fastapi + uvicorn
├── server.py           # FastAPI 推理服务
├── models/
│   └── minecraft-en-zh/  # MarianMT 模型权重（自行放置）
└── README.md
```

## 安装与启动

```powershell
cd inference_service
uv sync                                          # 首次：自动创建 .venv 并安装依赖
uv run python server.py                          # 启动服务，默认监听 127.0.0.1:8765
```

启动后服务监听 `http://127.0.0.1:8765`，主程序（机翻 API 选择「离线翻译」时）会
自动调用该服务。

## 接口

### `GET /health`
健康检查，返回 `{"status": "ok", "model_loaded": true}`。

### `POST /translate`
请求体：
```json
{ "text": "Hello world" }
```
响应：
```json
{ "translation": "你好世界" }
```

## 模型放置

将 HuggingFace 格式的 `Helsinki-NLP/opus-mt-en-zh`（或同源的 `minecraft-en-zh`）
模型文件放入 `inference_service/models/minecraft-en-zh/`，确保目录内至少包含：
```
config.json
generation_config.json
model.safetensors  # 或 pytorch_model.bin
source.spm
target.spm
tokenizer_config.json
vocab.json
```
