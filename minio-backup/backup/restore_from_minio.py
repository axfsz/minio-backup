import os
import time
import logging
from minio import Minio
from minio.error import S3Error
from urllib3.exceptions import MaxRetryError, ReadTimeoutError

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('minio-restore')

# 从环境变量读取配置
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT")
ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
BUCKET_NAME = os.getenv("BUCKET_NAME")
DOWNLOAD_PREFIX = os.getenv("DOWNLOAD_PREFIX", "auto/")
LOCAL_RESTORE_DIR = os.getenv("LOCAL_RESTORE_DIR", "./restored_data")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", "5"))


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
    if not os.path.exists(LOCAL_RESTORE_DIR):
        try:
            os.makedirs(LOCAL_RESTORE_DIR)
            logger.info(f"创建本地恢复目录: {LOCAL_RESTORE_DIR}")
        except Exception as e:
            logger.error(f"无法创建本地恢复目录: {LOCAL_RESTORE_DIR}, 错误: {e}")
            return False
    return True

def parse_endpoint(endpoint):
    if not endpoint or not isinstance(endpoint, str):
        logger.error("MinIO端点地址无效")
        return None
    if endpoint.startswith("http://"):
        endpoint = endpoint[7:]
    elif endpoint.startswith("https://"):
        endpoint = endpoint[8:]
    if "/" in endpoint:
        endpoint = endpoint.split("/")[0]
    if ":" in endpoint:
        host, port = endpoint.split(":")
        if port == "9090":
            endpoint = f"{host}:9000"
            logger.warning(f"检测到非API端口，已自动切换到API端口: {endpoint}")
    return endpoint

def get_minio_client():
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
    try:
        if not client.bucket_exists(BUCKET_NAME):
            logger.error(f"存储桶不存在: {BUCKET_NAME}")
            return False
        return True
    except S3Error as err:
        logger.error(f"检查存储桶失败: {err}")
        return False

def download_object_with_retry(client, object_name, local_file):
    retry_count = 0
    while retry_count < MAX_RETRIES:
        try:
            local_dir = os.path.dirname(local_file)
            if not os.path.exists(local_dir):
                os.makedirs(local_dir)
            client.fget_object(
                bucket_name=BUCKET_NAME,
                object_name=object_name,
                file_path=local_file
            )
            logger.info(f"下载成功: {object_name} → {local_file}")
            return True
        except (S3Error, MaxRetryError, ReadTimeoutError) as err:
            retry_count += 1
            if retry_count < MAX_RETRIES:
                wait_time = RETRY_DELAY * retry_count
                logger.warning(f"下载失败: {object_name}, 错误: {err}. 将在{wait_time}秒后重试 ({retry_count}/{MAX_RETRIES})")
                time.sleep(wait_time)
            else:
                logger.error(f"下载失败: {object_name}, 已达到最大重试次数. 错误: {err}")
                return False
        except Exception as e:
            logger.error(f"下载时发生未预期错误: {object_name}, 错误: {e}")
            return False
    return False

def restore_from_minio():
    if not validate_config():
        logger.error("配置验证失败，终止恢复")
        return False
    client = get_minio_client()
    if not client:
        logger.error("无法创建MinIO客户端，终止恢复")
        return False
    if not ensure_bucket_exists(client):
        logger.error("无法确保存储桶存在，终止恢复")
        return False
    total_files = 0
    successful_downloads = 0
    failed_downloads = 0
    start_time = time.time()
    logger.info(f"开始从 MinIO 存储桶 {BUCKET_NAME} 恢复 {DOWNLOAD_PREFIX} 到本地 {LOCAL_RESTORE_DIR}")
    objects = client.list_objects(BUCKET_NAME, prefix=DOWNLOAD_PREFIX, recursive=True)
    for obj in objects:
        total_files += 1
        relative_path = os.path.relpath(obj.object_name, DOWNLOAD_PREFIX)
        local_file = os.path.join(LOCAL_RESTORE_DIR, relative_path)
        if download_object_with_retry(client, obj.object_name, local_file):
            successful_downloads += 1
        else:
            failed_downloads += 1
    elapsed_time = time.time() - start_time
    logger.info(f"恢复完成. 总文件数: {total_files}, 成功: {successful_downloads}, 失败: {failed_downloads}, 耗时: {elapsed_time:.2f}秒")
    return failed_downloads == 0

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="从MinIO存储桶恢复数据到本地目录")
    parser.add_argument('--restore-dir', type=str, default=None, help='本地恢复目录，优先于环境变量LOCAL_RESTORE_DIR')
    parser.add_argument('--download-prefix', type=str, default=None, help='下载前缀，优先于环境变量DOWNLOAD_PREFIX')
    args = parser.parse_args()
    if args.restore_dir:
        LOCAL_RESTORE_DIR = args.restore_dir
        logger.info(f"通过命令行参数指定恢复目录: {LOCAL_RESTORE_DIR}")
    if args.download_prefix:
        DOWNLOAD_PREFIX = args.download_prefix
        logger.info(f"通过命令行参数指定下载前缀: {DOWNLOAD_PREFIX}")
    try:
        logger.info("开始MinIO恢复任务")
        success = restore_from_minio()
        if success:
            logger.info("恢复任务成功完成")
            exit(0)
        else:
            logger.error("恢复任务完成但存在失败的文件")
            exit(1)
    except KeyboardInterrupt:
        logger.warning("恢复任务被用户中断")
        exit(130)
    except Exception as e:
        logger.error(f"恢复任务发生未处理的异常: {e}")
        exit(2)