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
main.py
api/
  convert.py
  health.py
  dependencies.py
  models/
    convert.py
    health.py
core/
  config.py
  errors.py
  logging.py
convert/
  service.py
  types.py
  ocr_markdown_cleaner.py
integrations/
  markitdown.py
  minio.py
  omlx.py
uploads/
  temp_uploads.py
```

根目录就是服务代码根，不再额外套一层 `to_markdown/` 包。`main.py` 是唯一服务入口，直接创建 FastAPI app。

启动方式：

```bash
.venv/bin/python run_server.py --reload
```

## 包职责

### `main.py`

创建 FastAPI app，注册 router、统一异常处理，并在 lifespan 中创建和释放共享的 `ConvertService`。这里不写具体转换逻辑。

### `api`

HTTP API 层。

- `convert.py`：实现 `POST /convert` 和 `POST /convert/batch`。
- `health.py`：实现健康检查。
- `dependencies.py`：通过 FastAPI `Depends` 提供应用级共享服务。
- `models/convert.py`：定义文件转换响应模型。
- `models/health.py`：定义健康检查响应模型。

这一层不直接 import `MarkItDown`、`OpenAI` 或 `httpx`。

### `core`

项目基础设施。

- `config.py`：读取环境变量，生成 `Settings`。
- `errors.py`：定义统一业务异常。
- `logging.py`：保留统一日志入口。

### `convert`

业务编排层。

- `service.py`：`ConvertService`，负责完整转换流程。
- `types.py`：源文件元信息和转换结果数据类型。
- `ocr_markdown_cleaner.py`：清理 OCR 输出的边界标记、检测标签和坐标，不改写普通 Markdown。

`ConvertService.convert(...)` 是未来同步和异步共用的核心入口。

### `integrations`

第三方服务集成层。

- `markitdown.py`：
  - 初始化 MarkItDown。
  - 调用 `convert(...)`。
  - 把异常转换成项目自己的 `ConversionError`。

- `omlx.py`：
  - 用 OpenAI SDK 请求本地 oMLX。
  - 提供 MarkItDown 需要的 `client.chat.completions.create(...)` 形状。
  - 修复部分 OCR 模型返回的 byte-level tokenizer 乱码。
  - 提供 oMLX 可达性检查。

- `minio.py`：
  - 列出指定批次的 `original/` 对象。
  - 下载原文件并上传对应的 `converted/` Markdown 对象。
  - 将 MinIO 对象前缀映射为同批次的输出路径。

项目其他层不直接依赖 OpenAI SDK 和 MarkItDown 细节。

### `uploads`

上传文件的临时处理层。

- `temp_uploads.py`：
  - 保存 FastAPI 上传文件。
  - 控制临时目录和大小限制。
  - 转换结束后清理临时文件。

后续如果要把文件放到对象存储，只需要替换这一层。

## 同步与异步扩展

接口在 HTTP 语义上同步等待结果，但转换函数通过线程池执行；分层刻意避免把业务逻辑写死在 FastAPI route 中。

当前同步路径：

```text
FastAPI route -> Depends(get_convert_service) -> ConvertService.convert(...) -> ConvertResponse
```

未来异步路径可以变成：

```text
FastAPI route -> 创建 task_id -> worker 调用 ConvertService.convert(...) -> 存储结果
```

这样异步化时主要增加任务状态和结果存储，不需要重写转换核心。

## 排错实验的定位

独立的 oMLX OCR 退化实验位于
[`experiments/omlx_ocr_degeneration/`](../../experiments/omlx_ocr_degeneration/)，不进入正式服务运行时路径。
它只用于复现和分析模型输出问题，正式服务代码不依赖实验目录。
