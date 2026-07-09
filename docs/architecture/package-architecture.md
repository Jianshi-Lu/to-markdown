# to-markdown 分包架构

## 总体原则

项目采用“入口薄、业务集中、外部依赖隔离”的分包方式：

- HTTP 层只处理请求和响应。
- 业务编排集中在 service 层。
- MarkItDown、oMLX、OpenAI SDK 这类外部依赖放在 adapter 层。
- 内部模型不绑定 FastAPI，方便未来复用到异步任务或命令行工具。

## 目录结构

```text
main.py
api/
  routes/
    convert.py
    health.py
  schemas.py
core/
  config.py
  errors.py
  logging.py
domain/
  models.py
services/
  conversion_service.py
  markdown_normalizer.py
adapters/
  markitdown_adapter.py
  omlx_client.py
storage/
  temp_files.py
```

根目录就是服务代码根，不再额外套一层 `to_markdown/` 包。`main.py` 是唯一服务入口，直接创建 FastAPI app。

启动方式：

```bash
uvicorn main:app --reload
```

## 包职责

### `main.py`

创建 FastAPI app，注册 router 和统一异常处理。这里不写具体转换逻辑。

### `api`

HTTP API 层。

- `routes/convert.py`：实现 `POST /v1/convert`。
- `routes/health.py`：实现健康检查。
- `schemas.py`：定义对外响应模型。

这一层不直接 import `MarkItDown`、`OpenAI` 或 `httpx`。

### `core`

项目基础设施。

- `config.py`：读取环境变量，生成 `Settings`。
- `errors.py`：定义统一业务异常。
- `logging.py`：保留统一日志入口。

### `domain`

内部业务模型。

- `UploadedFileInfo`：上传文件元信息。
- `ConversionOptions`：转换选项。
- `ConversionResult`：转换结果。

这些对象不依赖 FastAPI，未来同步接口、异步 worker、命令行工具都可以共用。

### `services`

业务编排层。

- `ConversionService`：负责完整转换流程。
- `MarkdownNormalizer`：文本 LLM 二次整理占位实现。

`ConversionService.convert(...)` 是未来同步和异步共用的核心入口。

### `adapters`

外部依赖适配层。

- `markitdown_adapter.py`：
  - 初始化 MarkItDown。
  - 调用 `convert(...)`。
  - 把异常转换成项目自己的 `ConversionError`。

- `omlx_client.py`：
  - 用 OpenAI SDK 请求本地 oMLX。
  - 提供 MarkItDown 需要的 `client.chat.completions.create(...)` 形状。
  - 修复部分 OCR 模型返回的 byte-level tokenizer 乱码。
  - 提供 oMLX 可达性检查。

项目其他层不直接依赖 OpenAI SDK 和 MarkItDown 细节。

### `storage`

临时文件存储层。

- `temp_files.py`：
  - 保存 FastAPI 上传文件。
  - 控制临时目录和大小限制。
  - 转换结束后清理临时文件。

后续如果要把文件放到对象存储，只需要替换这一层。

## 同步与异步扩展

第一版是同步阻塞接口，但分层刻意避免把业务逻辑写死在 FastAPI route 中。

当前同步路径：

```text
FastAPI route -> ConversionService.convert(...) -> ConvertResponse
```

未来异步路径可以变成：

```text
FastAPI route -> 创建 task_id -> worker 调用 ConversionService.convert(...) -> 存储结果
```

这样异步化时主要增加任务状态和结果存储，不需要重写转换核心。

## Demo 的定位

`demo/` 保留为排错和学习材料。正式服务代码不依赖 demo 文件。

如果后续 oMLX、MarkItDown 或 OCR 输出出现问题，可以先用 demo 单独复现，再把确认过的修复迁移到 adapter 层。
