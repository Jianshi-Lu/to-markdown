# oMLX OCR 重复生成实验

这个目录用于独立复现 Unlimited-OCR 的重复 token 退化，不会导入或启动项目的
FastAPI、MarkItDown、`ConvertService`、OCR cleaner 和 `integrations`。

实验只保留一条最短链路：

```text
实验图片 → OpenAI-compatible HTTP 请求 → oMLX → 原始模型响应
```

## 复现的问题

对同一张图片使用 `Free OCR.`：

- `repetition_penalty=1.0` 时，模型可能持续生成同一个 byte-level token；原始响应
  表现为重复的 `çŃĨ`，按 tokenizer bytes 恢复后是连续的“筆”。
- 保持 `repetition_penalty=1.0`、把 prompt 改为 `document parsing.` 时不会退化，
  说明问题由图片、prompt 和解码配置共同触发。
- `Free OCR.` 配合 `repetition_penalty=1.1` 时，模型可以离开重复循环，继续输出
  OCR 定位标记和正文。

故障组把 `max_tokens` 限制为 256，只用于证明循环，不再等待原服务默认的 8192
token。对照组上限为 1024。

## 独立运行

先确保 oMLX 已启动并加载 `unlimited-ocr-mxfp8-mlx`。在仓库根目录执行：

```bash
uv sync
uv run python experiments/omlx_ocr_degeneration/prepare_fixture.py
uv run python experiments/omlx_ocr_degeneration/reproduce.py
```

服务地址、API key 和模型名可通过 `OMLX_BASE_URL`、`OMLX_API_KEY`、
`OMLX_MODEL` 覆盖。也可以用 `--input`、`--output`、`--prompt` 等参数。

## 输出

每次执行会先清空本目录的 `output/`，然后生成：

- `baseline_reproduced.raw.txt`：故障组的 oMLX 原始文本。
- `baseline_reproduced.decoded.txt`：byte-level tokenizer 恢复后的文本。
- `baseline_reproduced.summary.json`：结束原因、耗时和最长连续字符统计。
- `prompt_control.*`：只改变 prompt、不改变重复惩罚的控制组。
- `fixed_comparison.*`：修复参数下的同类文件。
- `comparison.json`：两组摘要的集中对照。

这可以证明退化发生在 oMLX 返回 cleaner 之前，而不是 API 返回模型、Markdown
normalizer 或文件写入阶段造成的。

## 如何理解“模型退化”

这里的“退化”不是模型文件损坏，也不是训练能力永久下降，而是一次自回归解码
进入了重复循环。模型每生成一个 token，都会把它作为下一步输入；如果某个异常
token 一直保持最高概率，就会形成正反馈：

```text
异常 token 成为最高概率输出
→ 输出该 token
→ 该 token 进入下一步上下文
→ 同一 token 仍然保持最高概率
→ 重复直到 EOS 或 max_tokens
```

当前实验可以确认的直接诱因是图片、`Free OCR.` 和采样设置的组合。MXFP8 量化、
oMLX 为 `deepseekocr` 自动生成的 `<image>\n` 格式，都可能影响相邻 token 的概率，
但目前没有 A/B 证据证明它们是根因。`repetition_penalty=1.1` 会降低已生成 token
再次被选中的概率，从而让解码继续进入正常 OCR token。
