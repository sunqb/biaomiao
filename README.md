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

- `GET /health`：健康检查
- `POST /ocr`：提交 base64 图片、data URL 或图片 URL

请求示例：

**1. Base64 图片：**

```bash
curl -X POST http://127.0.0.1:8000/ocr \
  -H 'Content-Type: application/json' \
  -d '{"image":"BASE64_IMAGE","filename":"image.png","mime_type":"image/png"}'
```

**2. Data URL：**

```bash
curl -X POST http://127.0.0.1:8000/ocr \
  -H 'Content-Type: application/json' \
  -d '{"image":"data:image/png;base64,BASE64_IMAGE","filename":"image.png"}'
```

**3. 图片 URL（推荐）：**

```bash
curl -X POST http://127.0.0.1:8000/ocr \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/image.png","mime_type":"image/png"}'
```

## 命令行识别

```bash
python main.py ./image.png
```
