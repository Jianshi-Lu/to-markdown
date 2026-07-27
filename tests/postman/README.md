# Postman 单文件 MinIO 转换联调

## 前置条件

1. MinIO 中已经存在待转换对象：

   ```text
   bid-records/<bidRecordId>/batches/<uploadBatchId>/original/a.pdf
   ```

2. 已配置 `MINIO_ENDPOINT`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY` 和 `MINIO_BUCKET`。
3. oMLX 服务已启动并可访问。
4. 启动 Python 服务：

   ```bash
   .venv/bin/python run_server.py
   ```

## 使用方式

1. 在 Postman 中导入 `to-markdown-batch.postman_collection.json`。
2. 打开集合变量，将 `originalObjectKey` 改为 MinIO 中实际存在的原始对象 Key。
3. 先执行“健康检查”和“oMLX 连通性检查”。
4. 执行“单文件转换并写回 MinIO”。
5. 在 MinIO 中检查：

   ```text
   bid-records/<bidRecordId>/batches/<uploadBatchId>/converted/a.md
   ```

例如：

```text
original/contract.pdf
converted/contract.md
```

接口不会把全部 Markdown 内容返回给调用方，只返回原对象和 converted 对象的 Key。
