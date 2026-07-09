# to-markdown 服务架构

## 背景

`to-markdown` 的目标是把文件、PDF、图片转换成 Markdown。第一版服务化目标不是做完整文档美化，而是把已经在 demo 中跑通的链路变成稳定的 HTTP API：

```text
文件 / PDF / 图片
  -> FastAPI 上传接口
  -> MarkItDown 文件类型路由和基础内容提取
  -> oMLX VLM 补充图片 OCR
  -> 输出 Markdown
```

文本 LLM 二次整理暂不实现，只保留接口位置。这样可以先验证 Web 服务、文件上传、MarkItDown、oMLX OCR 这条主链路。

## 技术选型

- FastAPI：Web API 框架，负责路由、表单上传、响应模型和异常处理。
- Uvicorn：ASGI 运行器，用于启动 FastAPI 服务。
- MarkItDown：文件识别、路由和基础 Markdown 转换。
- oMLX：独立模型服务，负责加载和管理 OCR/VLM 模型权重。
- OpenAI Python SDK：只作为 OpenAI-compatible HTTP client 使用，请求实际发往本地 oMLX，不发往 OpenAI 云端。

选择 FastAPI 的原因是它足够轻，适合当前“单接口文件转换服务”的需求；不像 Django 那样包含数据库、后台管理、ORM 等当前不需要的能力。

## 请求生命周期

```text
POST /v1/convert
  -> api.routes.convert 接收 UploadFile 和表单参数
  -> storage.temp_files 保存为临时文件
  -> services.conversion_service 编排转换
  -> adapters.markitdown_adapter 调用 MarkItDown
  -> adapters.omlx_client 作为 MarkItDown 的 llm_client
  -> services.markdown_normalizer 第一版跳过
  -> api.schemas.ConvertResponse 返回 Markdown
```

第一版接口是同步阻塞的：一次请求等待一次转换完成。内部核心入口是 `ConversionService.convert(...)`，不依赖 FastAPI request，因此未来可以被异步任务 worker 复用。

## API

### `GET /health`

检查 Web 服务是否存活。

### `GET /v1/health/omlx`

检查 oMLX 的 TCP endpoint 是否可连。它只验证 host:port，不代表模型推理一定成功。

### `POST /v1/convert`

请求格式：`multipart/form-data`

字段：

- `file`：上传文件，必填。
- `enable_ocr`：是否允许图片 OCR，默认 `true`。
- `normalize_markdown`：是否启用文本 LLM 二次整理，第一版保留参数但不真正整理。

响应字段：

- `markdown`：转换后的 Markdown。
- `source_filename`：原始文件名。
- `content_type`：上传文件 Content-Type。
- `used_ocr`：是否按文件类型推断会使用 OCR。
- `normalized`：第一版固定为 `false`。
- `warnings`：非致命提示。

## 配置项

配置通过环境变量读取：

- `OMLX_BASE_URL`：默认 `http://127.0.0.1:8000/v1`。
- `OMLX_API_KEY`：默认 `20020228`，作为本地 oMLX 占位 token。
- `OMLX_MODEL`：默认 `unlimited-ocr-mxfp8-mlx`。
- `TEMP_DIR`：临时文件根目录，默认系统临时目录。
- `MAX_UPLOAD_MB`：上传文件大小限制，默认 `100`。

## 错误处理

服务内部异常统一继承 `AppError`，由 FastAPI exception handler 转成 JSON：

- `ConversionError`：MarkItDown 转换失败。
- `OmlxUnavailableError`：oMLX 不可连或 chat completions 请求失败。
- `UploadTooLargeError`：上传文件超过限制。

第一版不暴露完整 Python traceback 给客户端，避免排错信息噪音太大。

## 第一版边界

第一版不做：

- 数据库。
- Redis / Celery / 任务队列。
- 用户系统。
- 文件长期存储。
- 文本 LLM 二次整理。
- 页面端 UI。

这些能力后续都可以在当前分层上扩展，不需要改写 MarkItDown/oMLX 的核心适配逻辑。

