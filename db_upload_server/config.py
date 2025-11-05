import os
from pathlib import Path

# 기본 경로 설정
BASE_DIR = Path(os.getenv("BASE_DIR", "/recordings"))

# 상태별 폴더 경로
PROCESSING_DIR = BASE_DIR / "processing"
COMPLETED_DIR = BASE_DIR / "completed"
FAILED_DIR = BASE_DIR / "failed"

# 스캔 설정
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "1"))

# AWS S3 설정
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "default-bucket-name")

# 외부 서버 설정
STATUS_SERVER_URL = os.getenv("STATUS_SERVER_URL", "http://status-server.com")

# --- 워커 설정 (int로 변환) ---
NUM_WORKERS = int(os.getenv("NUM_WORKERS", "1"))
NUM_RETRY_WORKER = int(os.getenv("NUM_RETRY_WORKERS", "1"))

# --- 실패 처리 설정 (int로 변환) ---
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY_MINUTES = int(os.getenv("RETRY_DELAY_MINUTES", "10"))
SCHEDULER_INTERVAL_SECONDS = int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "60"))