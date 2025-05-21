# MinIO 备份工具说明文档

## 项目简介
本项目用于将本地指定目录的数据自动备份到 MinIO 对象存储，支持大文件分块上传、断点重试、灵活配置上传路径等功能，适用于定期数据归档、数据库备份等场景。

## 主要功能
- 支持通过环境变量或命令行参数灵活配置备份目录
- 自动检测并创建 MinIO 存储桶
- 支持大文件分块上传，提升上传效率与稳定性
- 上传失败自动重试，最大重试次数与间隔可配置
- 支持自定义上传前缀，便于归档管理
- 详细日志输出，便于问题排查

## 环境变量说明
| 变量名                | 说明                           | 示例/默认值                |
|----------------------|------------------------------|---------------------------|
| MINIO_ENDPOINT       | MinIO 服务端点（IP:端口）      | 172.16.100.252:9000       |
| MINIO_ACCESS_KEY     | MinIO 访问密钥                 | your-access-key           |
| MINIO_SECRET_KEY     | MinIO 密钥                     | your-secret-key           |
| BUCKET_NAME          | 目标存储桶名称                 | my-backup-bucket          |
| LOCAL_BACKUP_DIR     | 本地待备份目录                 | /data_to_backup           |
| UPLOAD_PREFIX        | 上传到 MinIO 的路径前缀         | auto/                     |
| MINIO_SECURE         | 是否使用 HTTPS（true/false）    | false                     |
| MAX_RETRIES          | 上传失败最大重试次数            | 3                         |
| RETRY_DELAY          | 重试间隔（秒）                  | 5                         |
| MULTIPART_THRESHOLD  | 分块上传阈值（字节）            | 10485760（10MB）          |
| MULTIPART_CHUNKSIZE | 分块大小（字节） | 5242880（5MB） |
| --watch | 是否监听目录变动并自动备份 | 命令行参数，true 时自动备份 |

## 使用方法

### 1. 通过 Docker Compose 部署
1. 修改 `docker-compose.yml`，配置好环境变量和挂载目录：
    - `/data/neo4j:/data:ro`：本地需要备份的数据目录
    - `./backup:/app`：备份脚本目录
2. 启动服务：
```bash
docker-compose up --build -d
```
3. 查看日志：
```bash
docker logs -f minio-backup
```

### 2. 命令行直接运行
1. 安装依赖：
```bash
pip install -r requirements.txt
```
2. 设置环境变量（可选，未设置则使用默认值）：
```bash
export MINIO_ENDPOINT=mino服务器地址:端口 #自定义mino服务地址
export MINIO_ACCESS_KEY=your-access-key
export MINIO_SECRET_KEY=your-secret-key
export BUCKET_NAME=my-backup-bucket
export LOCAL_BACKUP_DIR=/data_to_backup
```
3. 执行备份脚本：
```bash
python backup/upload_backup_to_minio.py --backup-dir /your/data/dir
```

## 常见问题与注意事项
- **端口说明**：MinIO API 端口通常为 9000，若配置为 9090 会自动切换为 9000。
- **目录挂载**：确保本地备份目录已挂载到容器内，且有读取权限。
- **大文件上传**：超过 `MULTIPART_THRESHOLD` 的文件将自动分块上传，分块大小由 `MULTIPART_CHUNKSIZE` 控制。
- **重试机制**：上传失败会自动重试，重试次数和间隔可通过环境变量调整。
- **日志查看**：所有操作均有详细日志输出，便于排查问题。
- **安全连接**：如需使用 HTTPS，设置 `MINIO_SECURE=true` 并确保 MinIO 端点支持 HTTPS。
- **自动目录监听**：通过 `--watch` 参数可自动检测目录变动并实时备份，无需人工干预。