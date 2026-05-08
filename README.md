# Manual Translation Tool

本地网页工具，用来把英文水泵说明书 PDF 转成可校对的越南语 PDF。

## 当前第一版能力

- 上传 PDF，生成每页预览图。
- 尝试读取 PDF 里的英文文字和坐标。
- 通过阿里百炼 API 把英文翻译成越南语。
- 如果没有设置 API Key，会保留英文并标记为需要人工翻译/校对。
- 可以在网页里逐块修改译文、勾选校对完成。
- 导出越南语 PDF：保留原页面背景，在原文字区域覆盖白底并写入越南语。
- 导出时会尽量继承原文字号、标题加粗、章节标题和警告文字样式。

## 启动

```powershell
.\start.ps1
```

然后打开：

```text
http://127.0.0.1:8000
```

## 阿里百炼 API 设置

百炼支持 OpenAI 兼容接口，本项目使用 Python `openai` SDK 调用百炼。

在启动前先设置 API Key：

```powershell
$env:DASHSCOPE_API_KEY="你的阿里百炼 API Key"
```

默认配置：

```powershell
$env:DASHSCOPE_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
$env:DASHSCOPE_MODEL="qwen-plus"
```

如果你使用新加坡或美国地域，可以改 `DASHSCOPE_BASE_URL`：

```powershell
# 新加坡
$env:DASHSCOPE_BASE_URL="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

# 美国弗吉尼亚
$env:DASHSCOPE_BASE_URL="https://dashscope-us.aliyuncs.com/compatible-mode/v1"
```

不设置 API Key 也可以使用工具，只是译文会先显示英文，需要人工填写越南语。
