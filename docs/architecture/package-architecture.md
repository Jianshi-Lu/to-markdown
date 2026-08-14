# to-markdown 分包架构

## 总体原则

项目采用“入口薄、业务集中、外部依赖隔离”的分包方式：

- HTTP 层只处理请求和响应。
- 路由依赖通过 FastAPI `Depends` 获取应用级共享对象。
- 业务编排集中在 service 层。
- MarkItDown、oMLX、OpenAI SDK 这类外部依赖放在集成层。
- 内部模型不绑定 FastAPI，方便未来复用到异步任务或命令行工具。

## 目录结构

```text
api/
  server.py
  convert.py
  health.py
  dependencies.py
  models/
    health.py
configuration/
  config.py
core/
  errors.py
  logging.py
convert/
  service.py
  types.py
integrations/
  markitdown.py
  embedded_image_ocr.py
  omlx.py
```

根目录就是服务代码根，不再额外套一层 `to_markdown/` 包。`api/server.py` 是唯一服务入口，直接创建 FastAPI app 并启动 Uvicorn。

启动方式：

```bash
uv run python -m api.server --reload
```

## 包职责

### `api/server.py`

创建 FastAPI app，注册 router、统一异常处理，并在 lifespan 中创建和释放共享的 `ConvertService`。`main()` 解析原有服务参数并启动 Uvicorn；这里不写具体转换逻辑。

### `api`

HTTP API 层。

- `convert.py`：接收 multipart 文件流，调用转换服务并返回 `text/markdown` 文件。
- `health.py`：实现健康检查。
- `dependencies.py`：通过 FastAPI `Depends` 提供应用级共享服务。
- `models/health.py`：定义健康检查响应模型。

这一层不直接 import `MarkItDown`、`OpenAI` 或 `httpx`。

### `configuration`

项目基础设施。

- `config.py`：读取同目录 `.env`（不覆盖已存在的进程变量）；缓存的 `get_conversion_settings()` 和 `get_http_server_settings()` 分别生成转换与 HTTP 监听配置。

### `core`

项目基础设施。

- `errors.py`：定义统一业务异常。
- `logging.py`：保留统一日志入口。

### `convert`

业务编排层。

- `service.py`：`ConvertService`，负责完整转换流程。
- `types.py`：源文件元信息和转换结果数据类型。

`ConvertService.convert(...)` 是未来同步和异步共用的核心入口。

### `integrations`

第三方服务集成层。

- `markitdown.py`：
  - 初始化 MarkItDown（`enable_plugins=False`，只启用内置转换器）。
  - 调用 `convert_stream(...)`，根据上传文件名和 MIME type 提供格式提示。
  - 把异常转换成项目自己的 `ConversionError`。

- `embedded_image_ocr.py`：
  - 复用 markitdown-ocr 的 `LLMVisionOCRService`，OCR 模型为本地 unlimited-ocr。
  - 含嵌入位图的 PDF 才逐页检测并 OCR；DOCX/XLSX 解包 `media/` 位图并 OCR，PPTX 由内置转换器在配置 LLM client 时描述图片。
  - 不注册任何转换器，不阻塞 MarkItDown 内置能力。

- `omlx.py`：
  - 用 OpenAI SDK 请求本地 oMLX。
  - 提供 MarkItDown 需要的 `client.chat.completions.create(...)` 形状。
  - 修复部分 OCR 模型返回的 byte-level tokenizer 乱码。
  - 提供 oMLX 可达性检查。

项目其他层不直接依赖 OpenAI SDK 和 MarkItDown 细节。

正式服务不包含文件存储层。FastAPI 将 multipart 文件暴露为 `UploadFile`，API
把其请求级文件流直接交给 `ConvertService`；调用方负责原文件读取、Markdown
持久化、目标路径、覆盖策略和业务状态。

## 同步与异步扩展

接口在 HTTP 语义上同步等待结果，但转换函数通过线程池执行；分层刻意避免把业务逻辑写死在 FastAPI route 中。

当前同步路径：

```text
FastAPI route -> Depends(get_convert_service) -> ConvertService.convert(stream) -> text/markdown
```

未来异步路径可以变成：

```text
FastAPI route -> 创建 task_id -> worker 调用 ConvertService.convert(stream) -> 返回结果
```

如果未来异步化，任务输入和结果持久化仍应由调用方或上层任务系统负责，不下沉
到这个纯转换服务。

## 排错实验的定位

独立的 oMLX OCR 退化实验位于
[`experiments/omlx_ocr_degeneration/`](../../experiments/omlx_ocr_degeneration/)，不进入正式服务运行时路径。
它只用于复现和分析模型输出问题，正式服务代码不依赖实验目录。
