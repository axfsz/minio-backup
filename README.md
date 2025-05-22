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
| LOCAL_RESTORE_DIR    | 本地恢复目录                   | ./restored_data           |
| DOWNLOAD_PREFIX      | 下载前缀                       | auto/                     |
| MINIO_SECURE         | 是否使用 HTTPS（true/false）    | false                     |
| MAX_RETRIES          | 上传/下载失败最大重试次数       | 3                         |
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
export LOCAL_RESTORE_DIR=./restored_data
export DOWNLOAD_PREFIX=auto/
```
3. 执行备份脚本：
```bash
python backup/upload_backup_to_minio.py --backup-dir /your/data/dir
```
4. 执行恢复脚本：
```bash
python backup/restore_from_minio.py --restore-dir /your/restore/dir --download-prefix auto/
```

## 数据恢复流程说明

### 恢复脚本用途
`backup/restore_from_minio.py` 用于从 MinIO 对象存储恢复指定前缀下的所有文件到本地指定目录，适用于数据灾备、归档恢复等场景。

### 主要参数与环境变量
- `MINIO_ENDPOINT`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY`、`BUCKET_NAME`：同备份脚本，指定 MinIO 连接信息。
- `LOCAL_RESTORE_DIR`：本地恢复目录，默认为 `./restored_data`，可通过环境变量或 `--restore-dir` 参数指定。
- `DOWNLOAD_PREFIX`：下载前缀，默认为 `auto/`，可通过环境变量或 `--download-prefix` 参数指定。
- `MINIO_SECURE`、`MAX_RETRIES`、`RETRY_DELAY`：同备份脚本，控制连接安全性与重试机制。

### 典型用法示例
- 通过环境变量恢复：
```bash
export LOCAL_RESTORE_DIR=/restore/target
export DOWNLOAD_PREFIX=auto/
python backup/restore_from_minio.py
```
- 通过命令行参数恢复（优先于环境变量）：
```bash
python backup/restore_from_minio.py --restore-dir /restore/target --download-prefix auto/
```

### 日志与错误处理
- 所有操作均有详细日志输出，包含恢复进度、成功/失败文件数、耗时等。
- 支持断点重试，下载失败会自动重试，达到最大重试次数后记录为失败。
- 恢复过程中如遇配置错误、连接异常、存储桶不存在等问题会有明确日志提示。

### 常见问题与注意事项
- **端口说明**：MinIO API 端口通常为 9000，若配置为 9090 会自动切换为 9000。
- **恢复目录**：如目标目录不存在会自动创建，需确保有写入权限。
- **前缀匹配**：仅恢复指定 `DOWNLOAD_PREFIX` 下的对象，注意与备份前缀保持一致。
- **大文件恢复**：支持大文件断点续传，网络异常时自动重试。
- **安全连接**：如需使用 HTTPS，设置 `MINIO_SECURE=true` 并确保 MinIO 端点支持 HTTPS。
- **日志查看**：建议关注日志输出，及时发现并处理恢复失败的文件。

---

## 备份与恢复流程对比

| 流程 | 入口脚本 | 主要环境变量 | 主要参数 | 典型命令 |
|------|----------|--------------|----------|----------|
| 备份 | upload_backup_to_minio.py | LOCAL_BACKUP_DIR, UPLOAD_PREFIX | --backup-dir | python backup/upload_backup_to_minio.py --backup-dir /your/data/dir |
| 恢复 | restore_from_minio.py | LOCAL_RESTORE_DIR, DOWNLOAD_PREFIX | --restore-dir, --download-prefix | python backup/restore_from_minio.py --restore-dir /restore/target --download-prefix auto/ |