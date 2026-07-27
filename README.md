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

## `POST /convert/object`

Java 负责批次循环和数据库状态更新；Python 每次只接收一个 MinIO `original` object key，
读取单个对象、转换 Markdown，并写入对应的 `converted` object key：

```bash
curl -X POST http://127.0.0.1:8081/convert/object \
  -H 'Content-Type: application/json' \
  -d '{"originalObjectKey":"bid-records/8/batches/550e8400-e29b-41d4-a716-446655440000/original/a.pdf"}'
```

输入对象：

```text
bid-records/<bidRecordId>/batches/<uploadBatchId>/original/a.pdf
```

输出对象：

```text
bid-records/<bidRecordId>/batches/<uploadBatchId>/converted/a.md
```

`converted` 前缀不存在时，首次上传 Markdown 对象会自动形成。Python 不读取批次列表，也不
访问业务数据库；批次循环、单文件状态和批次状态由 Java 负责。

成功响应示例：

```json
{
  "originalObjectKey": ".../original/a.pdf",
  "originalFilename": "a.pdf",
  "convertedObjectKey": ".../converted/a.md",
  "status": "COMPLETED",
  "warnings": []
}
```
