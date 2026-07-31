# Postman 单文件转换联调

## 前置条件

1. oMLX 服务已启动并可访问。
2. 启动 Python 服务：

   ```bash
   .venv/bin/python run_server.py
   ```

## 使用方式

1. 在 Postman 中导入 `to-markdown-batch.postman_collection.json`。
2. 先执行“健康检查”和“oMLX 连通性检查”。
3. 打开“单文件转换”请求，在 `Body -> form-data` 中为 `file` 选择本地文件。
4. 发送请求，确认响应 `Content-Type` 包含 `text/markdown`，响应体为 Markdown。

服务不读取 MinIO，也不保存转换结果。需要持久化时，由调用方将响应体保存为
`.md` 文件或写入自己的对象存储。
