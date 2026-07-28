# to-markdown 服务架构

## 背景

`to-markdown` 的目标是把文件、PDF、图片转换成 Markdown。服务化目标是把 MarkItDown 与 oMLX 的转换链路封装成稳定的 HTTP API：

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
  -> api.dependencies 通过 Depends 获取共享 ConvertService
  -> uploads.temp_uploads 保存为临时文件
  -> convert.service 编排转换
  -> integrations.markitdown 调用 MarkItDown
  -> integrations.omlx 作为 MarkItDown 的 llm_client
  -> convert.ocr_markdown_cleaner 清理 OCR 协议噪声
  -> api.models.convert.ConvertResponse 返回 Markdown
```

接口在 HTTP 语义上是同步的：一次请求等待一次转换完成。`ConvertService.convert(...)` 是同步函数，但路由通过 `run_in_threadpool()` 执行，因此不会直接阻塞 FastAPI 主事件循环。内部核心入口不依赖 FastAPI request，未来仍可被异步任务 worker 复用。

`ConvertService` 在 FastAPI 应用启动时创建一次，并在应用关闭时释放 oMLX/OpenAI SDK 的 HTTP 资源。路由通过 `Depends(get_convert_service)` 获取该实例，而不是自行创建或直接装配服务。每次转换只创建请求级的 OCR 调用状态，避免并发请求共享 warning。

### `POST /convert/object`

请求体为单个 MinIO 原始对象 Key：

```json
{"originalObjectKey":"bid-records/8/batches/550e8400-e29b-41d4-a716-446655440000/original/a.pdf"}
```

服务通过应用生命周期内复用的 MinIO 读取器读取一个
`bid-records/{bidRecordId}/batches/{uploadBatchId}/original/a.pdf` 对象，下载到 `TEMP_DIR` 下的临时文件，再复用
`ConvertService.convert()` 调用 MarkItDown，转换完成后删除临时文件，并立即写入
`bid-records/{bidRecordId}/batches/{uploadBatchId}/converted/a.md`。MinIO 以对象前缀表示目录，首次上传时无需额外创建目录。
Java 负责批次循环、文件状态和批次状态，Python 只处理当前对象。响应仅返回原对象 Key、转换
对象 Key 和 warning，不返回全部 Markdown 内容。

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
- `MINIO_ENDPOINT`：MinIO 服务地址，默认 `http://10.0.0.100:9000`。
- `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY`：MinIO 访问凭据。
- `MINIO_BUCKET`：资信文件 Bucket，默认 `credential-files`。

批次转换需要在当前虚拟环境安装 MinIO Python SDK：

```bash
.venv/bin/python -m pip install minio
```

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
- 原始文件上传和业务文件元数据管理（由 Java 负责）。
- 业务批次/文件状态维护（由 Java 负责）。
- 文本 LLM 二次重写。
- 页面端 UI。

当前 `/convert/object` 已通过 `integrations/minio.py` 从共享 MinIO 读取一个
`original` 对象，并将转换后的 Markdown 写入同批次的 `converted` 前缀。Python
不维护业务数据库，也不负责批次循环；Java 负责逐文件调用、状态更新和后续汇总。

这些能力后续都可以在当前分层上扩展，不需要改写 MarkItDown/oMLX 的核心适配逻辑。

独立的模型退化排错材料位于
[`experiments/omlx_ocr_degeneration/`](../../experiments/omlx_ocr_degeneration/)，不属于正式服务运行时路径。
