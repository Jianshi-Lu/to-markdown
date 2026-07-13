# to-markdown 服务架构

## 背景

`to-markdown` 的目标是把文件、PDF、图片转换成 Markdown。第一版服务化目标不是做完整文档美化，而是把已经在 demo 中跑通的链路变成稳定的 HTTP API：

```text
文件 / PDF / 图片
  -> FastAPI 上传接口
  -> MarkItDown 文件类型路由和基础内容提取
  -> oMLX VLM 补充图片 OCR
  -> 清理 OCR 协议标记
  -> 输出 Markdown
```

Normalizer 只删除 OCR 模型输出中的协议标记和坐标，保留识别文字与普通 Markdown，不调用文本 LLM 重写内容。

## 技术选型

- FastAPI：Web API 框架，负责路由、表单上传、响应模型和异常处理。
- Uvicorn：ASGI 运行器，用于启动 FastAPI 服务。
- MarkItDown：文件识别、路由和基础 Markdown 转换。
- oMLX：独立模型服务，负责加载和管理 OCR/VLM 模型权重。
- OpenAI Python SDK：只作为 OpenAI-compatible HTTP client 使用，请求实际发往本地 oMLX，不发往 OpenAI 云端。

选择 FastAPI 的原因是它足够轻，适合当前“单接口文件转换服务”的需求；不像 Django 那样包含数据库、后台管理、ORM 等当前不需要的能力。

## 请求生命周期

```text
POST /convert
  -> api.convert 接收 UploadFile
  -> uploads.temp_uploads 保存为临时文件
  -> convert.service 编排转换
  -> integrations.markitdown 调用 MarkItDown
  -> integrations.omlx 作为 MarkItDown 的 llm_client
  -> convert.ocr_markdown_cleaner 清理 OCR 协议噪声
  -> api.models.convert.ConvertResponse 返回 Markdown
```

第一版接口是同步阻塞的：一次请求等待一次转换完成。内部核心入口是 `ConvertService.convert(...)`，不依赖 FastAPI request，因此未来可以被异步任务 worker 复用。

## API

### `GET /health`

检查 Web 服务是否存活。

### `GET /health/omlx`

检查 oMLX 的 TCP endpoint 是否可连。它只验证 host:port，不代表模型推理一定成功。

### `POST /convert`

请求格式：`multipart/form-data`

字段：

- `file`：上传文件，必填。
MarkItDown plugin 在服务端固定启用；文件中没有可 OCR 图片时不会访问 oMLX。

响应字段：

- `markdown`：转换后的 Markdown。
- `source_filename`：原始文件名。
- `content_type`：上传文件 Content-Type。
- `normalized`：本次输出是否清理了 OCR 协议标记。
- `warnings`：非致命提示。

## 配置项

配置通过环境变量读取：

- `OMLX_BASE_URL`：默认 `http://127.0.0.1:8000/v1`。
- `OMLX_API_KEY`：默认 `20020228`，作为本地 oMLX 占位 token。
- `OMLX_MODEL`：默认 `unlimited-ocr-mxfp8-mlx`。
- `OMLX_OCR_PROMPT`：默认 `Free OCR.`。
- `OMLX_OCR_MAX_TOKENS`：OCR 最大输出 token，默认 `4096`。
- `OMLX_OCR_TEMPERATURE`：OCR 采样温度，默认 `0`。
- `OMLX_OCR_REPETITION_PENALTY`：OCR 重复惩罚，默认 `1.1`。
- `TEMP_DIR`：临时文件目录，默认项目根目录下的 `.runtime/uploads/`。
- `MAX_UPLOAD_MB`：上传文件大小限制，默认 `100`。

## 错误处理

服务内部异常统一继承 `AppError`，由 FastAPI exception handler 转成 JSON：

- `ConversionError`：MarkItDown 转换失败。
- `OmlxUnavailableError`：oMLX 健康检查失败；转换期间的 OCR 调用失败会作为 warning 返回。
- `UploadTooLargeError`：上传文件超过限制。

第一版不暴露完整 Python traceback 给客户端，避免排错信息噪音太大。

## 第一版边界

第一版不做：

- 数据库。
- Redis / Celery / 任务队列。
- 用户系统。
- 文件长期存储。
- 文本 LLM 二次重写。
- 页面端 UI。

这些能力后续都可以在当前分层上扩展，不需要改写 MarkItDown/oMLX 的核心适配逻辑。
