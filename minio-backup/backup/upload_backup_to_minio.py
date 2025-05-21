import os
import time
import logging
from datetime import datetime
from minio import Minio
from minio.error import S3Error
from urllib3.exceptions import MaxRetryError, ReadTimeoutError
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('minio-backup')

# 从环境变量读取配置
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT")  # 例如 172.16.100.252:9090
ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")   # 访问密钥
SECRET_KEY = os.getenv("MINIO_SECRET_KEY")   # 密钥
BUCKET_NAME = os.getenv("BUCKET_NAME")       # Bucket 名称
LOCAL_DIR = os.getenv("LOCAL_BACKUP_DIR", "/data_to_backup")  # 本地数据目录
UPLOAD_PREFIX = os.getenv("UPLOAD_PREFIX", "auto/")          # 上传路径前缀
# 是否使用安全连接（HTTPS）
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
# 重试次数
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
# 重试间隔（秒）
RETRY_DELAY = int(os.getenv("RETRY_DELAY", "5"))
# 分块上传阈值（字节）- 默认10MB
MULTIPART_THRESHOLD = int(os.getenv("MULTIPART_THRESHOLD", str(10 * 1024 * 1024)))
# 分块大小（字节）- 默认5MB
MULTIPART_CHUNKSIZE = int(os.getenv("MULTIPART_CHUNKSIZE", str(5 * 1024 * 1024)))

# 验证必要的环境变量
def validate_config():
    required_vars = {
        "MINIO_ENDPOINT": MINIO_ENDPOINT,
        "MINIO_ACCESS_KEY": ACCESS_KEY,
        "MINIO_SECRET_KEY": SECRET_KEY,
        "BUCKET_NAME": BUCKET_NAME
    }
    
    missing_vars = [var for var, value in required_vars.items() if not value]
    
    if missing_vars:
        logger.error(f"缺少必要的环境变量: {', '.join(missing_vars)}")
        return False
        
    if not os.path.exists(LOCAL_DIR):
        logger.error(f"本地备份目录不存在: {LOCAL_DIR}")
        return False
        
    return True

def parse_endpoint(endpoint):
    """解析并规范化MinIO端点地址"""
    if not endpoint or not isinstance(endpoint, str):
        logger.error("MinIO端点地址无效")
        return None
        
    # 移除协议前缀（如果存在）
    if endpoint.startswith("http://"):
        endpoint = endpoint[7:]
    elif endpoint.startswith("https://"):
        endpoint = endpoint[8:]
    
    # 移除任何路径组件（如果存在）
    if "/" in endpoint:
        endpoint = endpoint.split("/")[0]
        
    # 确保使用API端口 (通常是9000而不是9090)
    if ":" in endpoint:
        host, port = endpoint.split(":")
        # 如果端口是9090，改为使用API端口9000
        if port == "9090":
            endpoint = f"{host}:9000"
            logger.warning(f"检测到非API端口，已自动切换到API端口: {endpoint}")
    
    return endpoint

def get_minio_client():
    """创建并返回MinIO客户端"""
    endpoint = parse_endpoint(MINIO_ENDPOINT)
    if not endpoint:
        return None
        
    try:
        client = Minio(
            endpoint,
            access_key=ACCESS_KEY,
            secret_key=SECRET_KEY,
            secure=MINIO_SECURE
        )
        return client
    except Exception as e:
        logger.error(f"创建MinIO客户端失败: {e}")
        return None

def ensure_bucket_exists(client):
    """确保存储桶存在，不存在则创建"""
    try:
        if not client.bucket_exists(BUCKET_NAME):
            client.make_bucket(BUCKET_NAME)
            logger.info(f"创建存储桶: {BUCKET_NAME}")
        return True
    except S3Error as err:
        logger.error(f"检查/创建存储桶失败: {err}")
        return False

def upload_file_with_retry(client, local_file, object_name):
    """带重试机制的文件上传"""
    file_size = os.path.getsize(local_file)
    retry_count = 0
    
    while retry_count < MAX_RETRIES:
        try:
            # 大文件使用分块上传
            if file_size > MULTIPART_THRESHOLD:
                logger.info(f"使用分块上传大文件: {local_file} ({file_size/1024/1024:.2f} MB)")
                client.fput_object(
                    bucket_name=BUCKET_NAME,
                    object_name=object_name,
                    file_path=local_file,
                    part_size=MULTIPART_CHUNKSIZE
                )
            else:
                client.fput_object(
                    bucket_name=BUCKET_NAME,
                    object_name=object_name,
                    file_path=local_file
                )
                
            logger.info(f"上传成功: {local_file} → {object_name}")
            return True
            
        except (S3Error, MaxRetryError, ReadTimeoutError) as err:
            retry_count += 1
            if retry_count < MAX_RETRIES:
                wait_time = RETRY_DELAY * retry_count
                logger.warning(f"上传失败: {local_file}, 错误: {err}. 将在{wait_time}秒后重试 ({retry_count}/{MAX_RETRIES})")
                time.sleep(wait_time)
            else:
                logger.error(f"上传失败: {local_file}, 已达到最大重试次数. 错误: {err}")
                return False
        except Exception as e:
            logger.error(f"上传时发生未预期错误: {local_file}, 错误: {e}")
            return False
    
    return False

def upload_directory_to_minio():
    """将本地目录上传到MinIO"""
    # 验证配置
    if not validate_config():
        logger.error("配置验证失败，终止备份")
        return False
    
    # 获取MinIO客户端
    client = get_minio_client()
    if not client:
        logger.error("无法创建MinIO客户端，终止备份")
        return False
    
    # 确保存储桶存在
    if not ensure_bucket_exists(client):
        logger.error("无法确保存储桶存在，终止备份")
        return False
    
    # 统计信息
    total_files = 0
    successful_uploads = 0
    failed_uploads = 0
    start_time = time.time()
    
    logger.info(f"开始备份 {LOCAL_DIR} 到 MinIO 存储桶 {BUCKET_NAME}")
    
    # 遍历本地目录并上传到 MinIO
    for root, _, files in os.walk(LOCAL_DIR):
        for filename in files:
            total_files += 1
            local_file = os.path.join(root, filename)
            relative_path = os.path.relpath(local_file, LOCAL_DIR)
            object_name = os.path.join(UPLOAD_PREFIX, relative_path).replace("\\", "/")
            
            if upload_file_with_retry(client, local_file, object_name):
                successful_uploads += 1
            else:
                failed_uploads += 1
    
    # 备份完成，输出统计信息
    elapsed_time = time.time() - start_time
    logger.info(f"备份完成. 总文件数: {total_files}, 成功: {successful_uploads}, 失败: {failed_uploads}, 耗时: {elapsed_time:.2f}秒")
    
    return failed_uploads == 0

class BackupDirEventHandler(FileSystemEventHandler):
    def __init__(self, backup_func):
        super().__init__()
        self.backup_func = backup_func
        self._last_event_time = 0
        self._debounce_seconds = 3  # 防抖，避免频繁触发

    def on_any_event(self, event):
        now = time.time()
        if now - self._last_event_time > self._debounce_seconds:
            logger.info(f"检测到备份目录变动({event.event_type}: {event.src_path})，自动触发备份...")
            self._last_event_time = now
            self.backup_func()


def start_watch_backup_dir():
    if not validate_config():
        logger.error("配置验证失败，终止目录监听")
        return
    event_handler = BackupDirEventHandler(upload_directory_to_minio)
    observer = Observer()
    observer.schedule(event_handler, LOCAL_DIR, recursive=True)
    observer.start()
    logger.info(f"开始监听目录: {LOCAL_DIR}，检测到变动将自动备份")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logger.info("目录监听已停止")
    observer.join()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="将本地目录备份到MinIO存储桶")
    parser.add_argument('--backup-dir', type=str, default=None, help='本地备份目录，优先于环境变量LOCAL_BACKUP_DIR')
    parser.add_argument('--watch', action='store_true', help='监听目录变动并自动备份')
    args = parser.parse_args()
    if args.backup_dir:
        LOCAL_DIR = args.backup_dir
        logger.info(f"通过命令行参数指定备份目录: {LOCAL_DIR}")
    try:
        if args.watch:
            logger.info("以目录监听模式启动，检测到变动自动备份")
            start_watch_backup_dir()
        else:
            logger.info("开始MinIO备份任务")
            success = upload_directory_to_minio()
            if success:
                logger.info("备份任务成功完成")
                exit(0)
            else:
                logger.error("备份任务完成但存在失败的文件")
                exit(1)
    except KeyboardInterrupt:
        logger.warning("备份任务被用户中断")
        exit(130)
    except Exception as e:
        logger.error(f"备份任务发生未处理的异常: {e}")
        exit(2)

os.environ['TZ'] = 'Asia/Shanghai'
time.tzset()

