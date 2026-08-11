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

上传一个文件并直接返回对应的 Markdown 文件。文件格式由 MarkItDown 内置
转换器识别（保留表格、列表等结构）；无嵌入位图的 PDF 整篇单遍转换，只有检测到
嵌入位图（或 PDF 无法解析）时才拆成单页并带有 `## Page N` 分页。嵌入位图按需调用本地 unlimited-ocr，OCR 结果以 `*[Image OCR] ... [End OCR]*`
插回 Markdown。DOCX/HTML/EPUB/ZIP 中的图片同样会被识别并把结果回填到对应
图片标签位置。OCR 模型通过 `OMLX_MODEL` 配置，默认
`unlimited-ocr-mxfp8-mlx`。文档解析和图片 OCR 使用独立输出上限：
`OMLX_OCR_MAX_TOKENS` 默认 `16384`，`OMLX_IMAGE_OCR_MAX_TOKENS` 默认 `768`，
避免复杂图片触发无界生成导致单文件转换长时间等待。

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
