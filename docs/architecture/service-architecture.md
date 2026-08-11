# to-markdown 服务架构

## 背景

`to-markdown` 的目标是把文件、PDF、图片转换成 Markdown。服务化目标是把 MarkItDown 与 oMLX 的转换链路封装成稳定的 HTTP API：

```text
文件 / PDF / 图片
  -> FastAPI 上传接口
  -> MarkItDown 内置转换器（表格、列表等结构保留）
  -> 嵌入位图按需调用 oMLX unlimited-ocr
  -> 输出 Markdown
```

服务不注册 markitdown-ocr 插件：插件会整体替换内置转换器，导致表格提取被
屏蔽。OCR 只作用于检测到的嵌入位图，无位图文档零模型调用。

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
  -> convert.service 直接接收请求级文件流
  -> convert.service 按后缀编排
     PDF：无位图整篇单遍转换；含位图时 pypdfium2 拆单页内置转换
     -> 含嵌入位图时 integrations.embedded_image_ocr 调用 unlimited-ocr
     DOCX/XLSX：内置转换 -> media 位图按需 OCR；PPTX 由内置转换器在配置 LLM client 时描述图片
     -> integrations.omlx 作为 OCR 的 OpenAI-compatible client
  -> Response 返回单个 text/markdown 文件
```

接口在 HTTP 语义上是同步的：一次请求等待一次转换完成。`ConvertService.convert(...)` 是同步函数，但路由通过 `run_in_threadpool()` 执行，因此不会直接阻塞 FastAPI 主事件循环。内部核心入口不依赖 FastAPI request，未来仍可被异步任务 worker 复用。

`ConvertService` 在 FastAPI 应用启动时创建一次，并在应用关闭时释放 oMLX/OpenAI SDK 的 HTTP 资源。路由通过 `Depends(get_convert_service)` 获取该实例，而不是自行创建或直接装配服务。每次转换只创建请求级的 OCR 调用状态，避免并发请求共享 warning。

服务不提供 `/convert/object`。MinIO、文件系统或其他存储中的原文件由调用方
读取；调用方通过 multipart 上传文件，并负责持久化返回的 Markdown。Python
不知道 `bidRecordId`、`batchId`、object key、`original/` 或 `converted/`。

## API

### `GET /health`

检查 Web 服务是否存活。

### `GET /health/omlx`

检查 oMLX 的 TCP endpoint 是否可连。它只验证 host:port，不代表模型推理一定成功。

### `POST /convert`

请求格式：`multipart/form-data`

字段：

- `file`：上传文件，必填。
服务端只启用 MarkItDown 内置转换器；无嵌入位图 PDF 整篇输出，含位图或无法解析时才带 `## Page N` 分页。嵌入位图
按需调用本地 unlimited-ocr，文件中没有嵌入位图时不会访问 oMLX。

成功响应：

- HTTP 状态为 `200`。
- `Content-Type` 为 `text/markdown; charset=utf-8`。
- `Content-Disposition` 提供由原文件名生成的 `.md` 下载名。
- 响应体就是 Markdown 内容，不再使用 JSON 包装。

## 配置项

配置通过环境变量读取：

- `OMLX_BASE_URL`：默认 `http://127.0.0.1:8000/v1`。
- `OMLX_API_KEY`：默认 `20020228`，作为本地 oMLX 占位 token。
- `OMLX_MODEL`：默认 `unlimited-ocr-mxfp8-mlx`。
- OCR 文档解析提示词固定为 `document parsing.`，直接写入 `Settings`，不从环境变量覆盖。
- `OMLX_OCR_MAX_TOKENS`：OCR 最大输出 token，默认 `16384`。
- `OMLX_IMAGE_OCR_MAX_TOKENS`：含图片输入的 OCR/视觉描述最大输出 token，默认 `768`；
  与文档解析输出上限分离，避免图片识别异常时长时间生成。
- `OMLX_OCR_TEMPERATURE`：OCR 采样温度，默认 `0`。
- `OMLX_OCR_REPETITION_PENALTY`：OCR 重复惩罚，默认 `1.1`。
- `MAX_UPLOAD_MB`：上传文件大小限制，默认 `100`。
- `ON_DEMAND_OCR_ENABLED`：嵌入位图按需 OCR 开关，默认 `1`。
- 嵌入位图 OCR 提示词同样固定为 `document parsing.`，直接写入 `Settings`。

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
- 原始文件读取、Markdown 保存和存储路径生成。
- 业务批次/文件状态维护（由 Java 负责）。
- 文本 LLM 二次重写。
- 页面端 UI。

历史 MinIO 适配器保存在 `archive/integrations/minio.py`，不属于正式服务依赖。
若调用方使用 MinIO，应在调用方完成下载和返回 Markdown 的上传。

独立的模型退化排错材料位于
[`experiments/omlx_ocr_degeneration/`](../../experiments/omlx_ocr_degeneration/)，不属于正式服务运行时路径。
