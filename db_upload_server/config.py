from pathlib import Path

# 기본 경로 설정
SCRIPT_DIR = Path(__file__).parent.resolve()
BASE_DIR = (SCRIPT_DIR / "../server/recordings").resolve()

# 상태별 폴더 경로
PROCESSING_DIR = BASE_DIR / "processing"
COMPLETED_DIR = BASE_DIR / "completed"
FAILED_DIR = BASE_DIR / "failed"

# AWS S3 설정
S3_BUCKET_NAME = "nev-video-bucket"

# 외부 서버 설정
STATUS_SERVER_URL = "http://status-server.com/metadata"

# 워커 설정
SCAN_INTERVAL_SECONDS = 10