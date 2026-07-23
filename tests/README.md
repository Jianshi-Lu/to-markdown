# 文件转换测试

`test_files/input/` 用于集中保存测试输入。测试脚本通过 HTTP 调用项目的
`/convert` 接口；运行前先启动服务：

```bash
.venv/bin/python run_server.py --reload
```

项目服务默认地址为 `http://127.0.0.1:8081`。如果使用其他地址，运行测试脚本前设置 `TO_MARKDOWN_BASE_URL`。

服务固定启用 MarkItDown plugin；只有文件包含可 OCR 图片时才会访问 oMLX。

## 批量转换

批量脚本会递归转换 `test_files/input/` 内的所有测试文件（忽略隐藏文件），并在
每次执行前完全清空 `test_files/output/`：

```bash
.venv/bin/python tests/convert_all.py
```

它按文件顺序串行请求接口。每个输出保留输入的相对目录，并追加
`_converted.md`；例如 `input/contracts/a.pdf` 对应
`output/contracts/a_converted.md`。任意文件失败时，脚本会立即退出，已完成的结果
会保留在输出目录中。

## 单文件转换

```bash
.venv/bin/python tests/convert.py tests/test_files/input/test_pdf.pdf
```

默认输出为 `tests/test_files/output/converted/test_pdf_converted.md`。

第二个参数可以指定输出目录：

```bash
.venv/bin/python tests/convert.py /path/to/input.docx /path/to/output/
```

也可以指定 Markdown 文件名。脚本会在扩展名前自动追加 `_converted`：

```bash
.venv/bin/python tests/convert.py /path/to/input.docx /path/to/result.md
```

实际输出为 `/path/to/result_converted.md`。

服务会固定清理 OCR 协议标记，无需额外传入开关。

## Postman 批次联调

可导入 [`postman/to-markdown-batch.postman_collection.json`](postman/to-markdown-batch.postman_collection.json)，
将集合变量 `uploadBatchId` 改为 MinIO 中实际存在的批次 UUID，然后调用批次转换接口。
详细前置条件见 [`postman/README.md`](postman/README.md)。
