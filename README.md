# to-markdown API

默认服务地址：`http://127.0.0.1:8081`

完整的自动生成文档：

- Redoc：<http://127.0.0.1:8081/redoc>
- OpenAPI JSON：<http://127.0.0.1:8081/openapi.json>

## `GET /health`

检查 Web 服务是否正在运行。

```bash
curl http://127.0.0.1:8081/health
```

## `GET /health/omlx`

检查配置的 oMLX 服务地址是否可以建立连接。

```bash
curl http://127.0.0.1:8081/health/omlx
```

连接失败时返回 `503`。

## `POST /convert`

上传文件并返回 Markdown。文件格式由 MarkItDown 识别；服务端固定启用 plugin，图片内容由 plugin 按需进行 OCR。

请求使用 `multipart/form-data`，必填字段只有 `file`。

```bash
curl -X POST http://127.0.0.1:8081/convert \
  -F "file=@./samples/contract.pdf"
```

响应中的 `markdown` 字段为转换结果；`warnings` 字段用于返回非致命提示。

## `POST /convert/batch`

调用方只发送批次 UUID，Python 服务自行从 MinIO 读取该批次的 `original` 对象，逐个转换并直接写入同批次的 `converted` 路径：

```bash
curl -X POST http://127.0.0.1:8081/convert/batch \
  -H 'Content-Type: application/json' \
  -d '{"uploadBatchId":"550e8400-e29b-41d4-a716-446655440000"}'
```

输入对象位于：

```text
<uploadBatchId>/original/
```

输出对象位于同批次的：

```text
<uploadBatchId>/converted/
```

例如 `original/a.pdf` 会生成 `converted/a.md`。`converted` 前缀不存在时，首次上传 Markdown
对象会自动形成。响应只返回原对象和转换后对象的 Key，不返回全部 Markdown 内容。
