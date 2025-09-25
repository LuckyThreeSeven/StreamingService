# config.py
import os
from dotenv import load_dotenv

# .env 파일에서 환경 변수를 로드
load_dotenv()

CLIENT_UUID = os.getenv("CLIENT_UUID", "DEFAULT_UUID")

# --- 서버 및 클라이언트 기본 설정 ---
MEDIAMTX_SERVER_URL = os.getenv("MEDIAMTX_SERVER_URL", "127.0.0.1:8890")
MEDIAMTX_SERVER_CHECK_URL = os.getenv("MEDIAMTX_SERVER_CHECK_URL", "127.0.0.1:9997")

# --- 오프라인 녹화 설정 ---
OFFLINE_REC_DURATION = int(os.getenv("OFFLINE_REC_DURATION", 30))

# --- 동적으로 경로 및 URL 생성 ---
# 로컬 녹화 파일 저장 경로
LOCAL_REC_PATH = f'./{CLIENT_UUID}'

# 오프라인 영상 업로드 서버 URL
OFFLINE_UPLOAD_SERVER_BASE_URL = os.getenv("OFFLINE_UPLOAD_SERVER_BASE_URL","http://127.0.0.1:8001/upload/video/")