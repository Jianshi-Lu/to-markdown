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

上传一个文件并直接返回对应的 Markdown 文件。文件格式由 MarkItDown 识别；
服务端固定启用 plugin，图片内容由 plugin 按需进行 OCR。

请求使用 `multipart/form-data`，必填字段只有 `file`。

```bash
curl -X POST http://127.0.0.1:8081/convert \
  -F "file=@./samples/contract.pdf"
```

成功响应不是 JSON，而是单个 Markdown 文件：

```http
HTTP/1.1 200 OK
Content-Type: text/markdown; charset=utf-8
Content-Disposition: attachment; filename="converted.md"; filename*=UTF-8''contract.md

# 转换后的 Markdown
```

服务不接收 MinIO object key，不读取或写入对象存储，也不生成 `original/`、
`converted/`、`batchId` 等业务路径。调用方负责取得原文件、调用本接口、保存
返回的 Markdown 文件并维护业务状态。
