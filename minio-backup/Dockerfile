FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# 确保 watchdog 依赖已包含在 requirements.txt 中，无需单独安装
COPY backup/upload_backup_to_minio.py /app/

