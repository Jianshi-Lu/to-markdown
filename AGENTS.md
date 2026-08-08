# to-markdown Agent 项目背景

> 本文件记录当前仓库源码已经实现的稳定事实、调用边界和不可破坏的约束。
> 若本文与源码不一致，以源码为准。

## 1. 项目目标与边界

`to-markdown` 是一个独立的多格式文件转 Markdown HTTP 服务。它只接受调用方
上传的单个文件流，完成格式识别、内容提取、必要的图片 OCR 和 Markdown 清理，
然后把单个 Markdown 文件直接返回调用方。

当前服务负责：

- 通过 MarkItDown 识别并转换 PDF、Office、图片、HTML、压缩包等测试覆盖的文件类型；
- 始终启用 MarkItDown 内置转换器，保留表格、列表、标题等官方结构化能力；
- 嵌入位图按需调用本地 unlimited-ocr（复用 markitdown-ocr 的 LLMVisionOCRService，
  但不注册其插件，避免插件替换内置转换器）；
- 通过 `POST /convert` 接收 multipart 文件并返回 `text/markdown`；
- 暴露进程健康检查和 oMLX TCP 可达性检查。

当前明确不负责：

- 从 MinIO、业务文件系统、URL 或数据库读取原文件；
- 保存原文件或转换后的 Markdown；
- 生成 `original/`、`converted/`、`bidRecordId`、`batchId` 等业务路径；
- MinIO bucket、object key、覆盖策略、幂等和存储凭据；
- Java 平台的文件、批次、投标记录和数据库状态；
- 批量编排、任务队列、重试恢复、风险分析、RAG 或知识库管理。

正式依赖方向是：

```text
调用方读取文件
  -> multipart POST /convert
  -> to-markdown 转换
  -> text/markdown 响应
  -> 调用方保存 Markdown 并更新业务状态
```

## 2. 技术栈与运行入口

| 技术 | 当前用途 |
| --- | --- |
| Python | 服务实现语言；本地项目使用 Python 3.13 虚拟环境 |
| FastAPI | HTTP 路由、multipart 上传和异常处理 |
| Uvicorn | ASGI 服务运行器 |
| MarkItDown | 文件类型识别和 Markdown 转换；只启用内置转换器 |
| markitdown-ocr | 仅复用其 LLMVisionOCRService，不注册插件 |
| OpenAI Python SDK + httpx | 以 OpenAI-compatible client 方式调用本地 oMLX |
| oMLX | 独立 OCR/VLM 模型服务 |
| unittest / pytest | 自动化测试 |

正式运行时不依赖 MinIO SDK，也没有对象存储、数据库或本地结果持久化模块。
仓库当前没有提交 `pyproject.toml`、`requirements.txt` 或正式依赖锁定文件。

启动服务：

```bash
.venv/bin/python run_server.py
```

开发热重载：

```bash
.venv/bin/python run_server.py --reload
```

默认地址为 `http://127.0.0.1:8081`，可通过 `SERVER_HOST`、`SERVER_PORT`、
`SERVER_LOG_LEVEL` 覆盖。

## 3. 目录与职责

```text
main.py                         # FastAPI app、lifespan、AppError HTTP 出口
run_server.py                   # Uvicorn 启动参数
api/
  convert.py                    # POST /convert：multipart -> text/markdown
  health.py                     # GET /health、GET /health/omlx
  dependencies.py               # 从 app.state 提供共享 ConvertService
  models/health.py              # 健康检查响应模型
convert/
  service.py                    # 文件流转换主编排
  types.py                      # SourceFile、ConvertResult
integrations/
  markitdown.py                 # MarkItDown 文件流适配
  embedded_image_ocr.py         # 嵌入位图按需 OCR（PDF/Office）
  omlx.py                       # oMLX/OpenAI-compatible OCR 适配
core/
  config.py                     # 进程级 Settings
  errors.py                     # AppError 及具体异常
  logging.py                    # 日志入口
archive/
  integrations/minio.py        # 历史 MinIO 适配，不进入正式运行链路
tests/                          # 自动化、HTTP 脚本、Postman 和测试输入
experiments/                    # 与正式运行时隔离的模型实验
docs/                           # 架构和代码参考
```

依赖方向：

```text
api -> convert / dependencies / core
convert -> integrations / core / internal types
integrations -> 第三方 SDK / core.errors
main -> api / convert / core
archive -/-> 正式运行模块
```

`main.py`、`api/`、`convert/` 和正式 `integrations/` 不得导入 `archive`。

## 4. HTTP 接口契约

### 4.1 健康检查

| 方法 | 路径 | 行为 |
| --- | --- | --- |
| `GET` | `/health` | 证明 FastAPI 进程存活，返回 `{"status":"ok"}` |
| `GET` | `/health/omlx` | 对 `OMLX_BASE_URL` 做 TCP 检查；失败返回 HTTP 503 |

`/health/omlx` 不验证 API Key、模型加载状态或真实推理质量。

### 4.2 `POST /convert`

请求使用 `multipart/form-data`，唯一必填字段为 `file`：

```bash
curl -X POST http://127.0.0.1:8081/convert \
  -F "file=@./contract.pdf" \
  --output contract.md
```

成功响应：

```http
HTTP/1.1 200 OK
Content-Type: text/markdown; charset=utf-8
Content-Disposition: attachment; filename="converted.md"; filename*=UTF-8''contract.md

# 转换后的 Markdown
```

响应体不是 JSON，不包含 object key、存储路径、业务状态或 Markdown 外层字段。
文件名和 MIME type 只作为 MarkItDown 格式识别提示与响应下载名使用。

### 4.3 已移除接口

`POST /convert/object` 已从正式服务移除。服务不接受 `originalObjectKey`，不读取
MinIO，也不写入 `convertedObjectKey`。

## 5. 转换调用链

```text
POST /convert
  -> api.convert.convert_file
  -> 校验 UploadFile.size 和清理客户端路径信息
  -> run_in_threadpool(ConvertService.convert)
  -> PDF：pypdfium2 拆单页 -> 每页 MarkItDown 内置转换
        -> 页面含嵌入位图时 EmbeddedImageOcr 调用 unlimited-ocr
  -> DOCX/PPTX/XLSX：MarkItDown 内置转换
        -> ZIP 内 media 位图按需 OCR 并追加结果
  -> 其它格式：MarkItDown 内置转换（图片文件走官方 ImageConverter）
  -> ConvertResult
  -> Response(text/markdown)
```

FastAPI 路由异步接收请求，同步转换在线程池执行。服务代码不创建业务文件或
转换结果文件；`UploadFile.file` 是 multipart 请求生命周期内的流，Starlette
可能按自身实现对大文件进行临时缓冲，但该缓冲不构成业务存储契约。

`ConvertService`、MarkItDown 适配器和 oMLX client 在应用启动时创建一次并复用，
应用关闭时调用 `close()`。

## 6. 转换与 OCR 规则

### 6.1 MarkItDown

`integrations/markitdown.py` 创建 `MarkItDown(enable_plugins=False, ...)`，
不启用 markitdown-ocr 插件。原因：插件以 -1.0 优先级整体替换内置
PDF/DOCX/PPTX/XLSX 转换器，导致 MarkItDown 自身的表格等结构能力被屏蔽。
适配器根据上传文件名和 MIME type 构造 `StreamInfo`，直接调用
`convert_stream()`。转换异常统一包装为 `ConversionError`。

PDF 先扫描是否含嵌入位图：无位图时整篇单遍调用内置 PdfConverter（无分页标记，
省去逐页拆解开销）；含位图时用 pypdfium2 拆成单页后逐页调用内置转换器，输出带
`## Page N` 分页标记，让 OCR 结果稳定归属页面。

### 6.3 嵌入位图按需 OCR

`integrations/embedded_image_ocr.py` 复用 markitdown-ocr 的
`LLMVisionOCRService`，配置为本地 unlimited-ocr（`OMLX_MODEL`）。只有检测到
嵌入位图才发起请求：

- PDF：pdfplumber 检测每页 `page.images`，渲染裁剪区域后 OCR，结果以
  `*[Image OCR] ... [End OCR]*` 插回对应页面；
- DOCX：按 `document.xml` 中图片出现顺序与 Markdown 图片标签配对，OCR 结果
  紧跟对应 `![](...)` 标签插入；
- HTML：提取 data URI 图片，OCR 结果紧跟对应图片标签插入；
- EPUB：按 content.opf manifest 顺序提取图片，OCR 结果回填到相对路径标签；
- ZIP：提取包内位图，OCR 结果回填到嵌套 HTML 等 Markdown 图片标签；
- XLSX：解包 ZIP 中 `xl/media/` 下的位图，OCR 结果追加到 Markdown 末尾；
- PPTX：由 MarkItDown 内置 PptxConverter 在配置 `llm_client` 时用
  `llm_caption` 内联描述，不重复 OCR；
- 远程 URL 图片（http/https）不发起 OCR，避免服务对外部站点产生依赖；
- 纯文本/无位图文档：零 OCR 调用。

### 6.2 oMLX

- `httpx.Client(trust_env=False)` 和 OpenAI client 在应用级复用；
- `max_retries=0`，没有 SDK 自动重试；
- 每次转换通过 `ContextVar` 建立独立 `OmlxOcrCallState`；
- 默认注入 `max_tokens`、`temperature`、`repetition_penalty`；
- 文档解析继续使用 `OMLX_OCR_MAX_TOKENS`，含视觉输入的请求单独使用
  `OMLX_IMAGE_OCR_MAX_TOKENS`（默认 768），避免复杂图片触发超长退化生成；
- 对 byte-level tokenizer 文本做解码；
- 丢弃连续重复字符的退化输出并记录 warning；
- `finish_reason == "length"` 时保留文本并记录 warning。

## 7. 配置与敏感信息

`core/config.py` 在模块导入时构造冻结的 `SETTINGS`：

| 环境变量 | 用途 |
| --- | --- |
| `OMLX_BASE_URL` | oMLX OpenAI-compatible 地址 |
| `OMLX_API_KEY` | oMLX 请求凭据或本地占位 token |
| `OMLX_MODEL` | OCR 模型名 |
| `OMLX_OCR_MAX_TOKENS` | OCR 输出上限 |
| `OMLX_IMAGE_OCR_MAX_TOKENS` | 含图片输入的 OCR/视觉描述输出上限，默认 768 |
| `OMLX_OCR_TEMPERATURE` | OCR 采样温度 |
| `OMLX_OCR_REPETITION_PENALTY` | OCR 重复惩罚 |
| `ON_DEMAND_OCR_ENABLED` | 是否启用嵌入位图按需 OCR（默认 1） |
| `MAX_UPLOAD_MB` | multipart 文件大小上限 |
| `SERVER_HOST` / `SERVER_PORT` / `SERVER_LOG_LEVEL` | Uvicorn 配置 |

正式配置中不存在 `MINIO_*` 或 `TEMP_DIR`。不要把真实凭据写入文档、源码、
测试输出或提交记录。

## 8. 异常边界

| 异常 | HTTP | 触发范围 |
| --- | ---: | --- |
| `UploadTooLargeError` | 413 | multipart 文件超过 `MAX_UPLOAD_MB` |
| `ConversionError` | 422 | MarkItDown 转换失败 |
| `OmlxUnavailableError` | 503 | oMLX 健康检查或连接失败 |

`main.py` 将 `AppError` 转换为：

```json
{"error":"conversion_failed","message":"..."}
```

失败响应可以是 JSON；成功响应始终是 Markdown 文件。客户端响应不得泄露
traceback、凭据或内部网络认证信息。

## 9. 测试与验证

```bash
.venv/bin/python -m pytest -q
```

当前测试覆盖：

- `tests/test_convert_api.py`：multipart 输入、Markdown 文件响应、路径清理和旧端点移除；
- `tests/test_markitdown_stream.py`：文件流与 `StreamInfo` 传递；
- `tests/test_omlx.py`：请求参数、解码、退化输出和并发状态；
- `tests/convert.py`、`tests/convert_all.py`：真实 HTTP 服务联调。

Postman 集合只调用 multipart `/convert`，不要求 MinIO。

## 10. 当前限制

- 请求同步等待转换完成；
- `MAX_UPLOAD_MB` 在 multipart 解析完成后根据 `UploadFile.size` 校验，不是网关级限流；
- oMLX 健康检查只有 TCP 级别；
- 非致命 OCR warning 保留在内部 `ConvertResult`，成功的文件响应不携带 warning envelope；
- 无文字矢量图形（流程图/图标）没有可 OCR 文本，unlimited-ocr 也无法给出语义描述；
- OCR 文本质量取决于 unlimited-ocr 模型本身，服务只保证按需触发和结果回插；
- 没有正式依赖锁定、容器编排、认证、限流和生产指标；
- `archive/` 和 `experiments/` 不属于正式运行时。

## 11. 修改时必须保持的约束

1. 正式转换接口只接收调用方提供的文件内容，不接受 object key 或业务路径。
2. 正式服务不得读取或写入 MinIO、业务文件系统、数据库或远程存储。
3. 成功响应是单个 `text/markdown` 文件，不恢复 JSON Markdown envelope。
4. 文件名只能用于格式提示和下载名，必须去掉调用方路径信息。
5. 共享 oMLX/OpenAI client 可以复用，请求级 warning 状态必须隔离。
6. OCR 只处理嵌入位图，不注册替换内置转换器的插件；无位图文档不得发起 OCR。
7. 修改接口、配置、转换规则或生命周期时，同步更新 README、docs、测试和 Postman。
