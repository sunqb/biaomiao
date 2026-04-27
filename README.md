# biaomiao

白描 OCR Web API 封装。

## 安装

```bash
pip install -r requirements.txt
```

## 配置

本地直接运行时使用 `config.ini`：

复制示例配置并填写账号信息：

```bash
cp config.example.ini config.ini
```

配置项：

```ini
[default]
username = your_account
password = your_password
uuid =
login_token =
request_timeout = 15
ocr_timeout = 60
poll_interval = 0.2
```

## 鉴权

所有 OCR 接口（`/ocr`、`/ocr/detail`、`/ocr/latex`、`/ocr/table`）支持 Bearer Token 鉴权。  
`/health` 接口不需要鉴权。

**配置方式**：在 `.env` 或环境变量中设置 `API_KEY`：

```ini
API_KEY=your-secret-token
```

未设置 `API_KEY` 时，所有请求均放行，便于本地开发调试。

## 启动 API

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Docker Compose 部署

Docker Compose 部署只需要 `.env`，不需要再配置 `config.ini`：

```bash
cp .env.example .env
# 编辑 .env 填入 BAIMIAO_USERNAME 和 BAIMIAO_PASSWORD
docker compose up -d --build
```

`.env` 配置项：

```ini
BAIMIAO_USERNAME=your_account
BAIMIAO_PASSWORD=your_password
# API token 鉴权，留空则不启用鉴权
API_KEY=your-secret-token
BAIMIAO_REQUEST_TIMEOUT=15
BAIMIAO_OCR_TIMEOUT=60
BAIMIAO_POLL_INTERVAL=0.2
```

说明：`config.ini` 仅用于本地 `python main.py` 或 `uvicorn main:app` 运行；Docker Compose 使用 `.env` 注入环境变量，避免两套配置重复维护。

常用命令：

```bash
docker compose ps
docker compose logs -f baimiao-ocr
docker compose down
```

接口：

所有 OCR 接口需要在 Header 中携带 Bearer Token（配置了 `API_KEY` 时生效）：

```
Authorization: Bearer your-secret-token
```

未配置 `API_KEY` 时自动跳过鉴权，便于本地开发。无 token 或 token 错误返回 `401`。

- `GET /health`：健康检查（无需鉴权）
- `POST /ocr`：文字识别，返回纯文本
- `POST /ocr/detail`：文字识别，返回带坐标的词块列表
- `POST /ocr/latex`：数学公式识别，返回 LaTeX 字符串
- `POST /ocr/table`：表格识别，返回 xlsx 下载链接

所有识别接口请求体格式相同：

| 字段 | 类型 | 说明 |
|------|------|------|
| `url` | string | 图片 HTTP/HTTPS 地址（与 `image` 二选一） |
| `image` | string | Base64 字符串或 data URL（与 `url` 二选一） |
| `filename` | string | 文件名，默认 `image.png` |
| `mime_type` | string | MIME 类型，默认 `image/png` |

请求示例：

**1. 文字识别 `/ocr`（纯文本）：**

```bash
curl -X POST http://127.0.0.1:8000/ocr \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/image.png","mime_type":"image/png"}'
```

响应：
```json
{"text": "识别出的文字内容"}
```

**2. 文字识别 `/ocr/detail`（带坐标）：**

```bash
curl -X POST http://127.0.0.1:8000/ocr/detail \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/image.png","mime_type":"image/png"}'
```

响应：
```json
{
  "blocks": [
    {
      "words": "识别出的文字",
      "location": {"left": 44, "top": 25, "width": 391, "height": 34},
      "vertexes_location": [{"x":44,"y":25},{"x":435,"y":25},{"x":435,"y":59},{"x":44,"y":59}],
      "score": 0.99
    }
  ]
}
```

**3. 公式识别 `/ocr/latex`：**

```bash
curl -X POST http://127.0.0.1:8000/ocr/latex \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/formula.png","mime_type":"image/png"}'
```

响应：
```json
{"latex": "\\beta_{0}n+\\beta_{1}\\sum_{i=1}^{n}x_{i}+\\cdots"}
```

**4. 表格识别 `/ocr/table`：**

```bash
curl -X POST http://127.0.0.1:8000/ocr/table \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/table.png","mime_type":"image/png"}'
```

响应：
```json
{
  "xlsx_url": "https://baimiaopdf.oss-cn-hangzhou.aliyuncs.com/result/xxx.xlsx?...",
  "file_name": "xxx"
}
```

**5. Base64 / Data URL 方式（所有接口通用）：**

```bash
curl -X POST http://127.0.0.1:8000/ocr \
  -H 'Content-Type: application/json' \
  -d '{"image":"data:image/png;base64,BASE64_IMAGE"}'
```

## 命令行识别

```bash
python main.py ./image.png
```
