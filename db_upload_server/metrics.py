import os
import logging
from prometheus_client import start_http_server, Counter, Histogram, Gauge

# --- 버킷 로드 헬퍼 ---
def get_buckets_from_env(env_var_name: str, default_buckets: list[float]) -> list[float]:
    buckets_str = os.getenv(env_var_name)
    if not buckets_str:
        logging.info(f"'{env_var_name}' 환경 변수가 설정되지 않았습니다. 기본 버킷을 사용합니다.")
        return default_buckets

    try:
        buckets = [float(b.strip()) for b in buckets_str.split(',') if b.strip()]
        if not buckets:
            raise ValueError("버킷 리스트가 비어있습니다.")

        logging.info(f"'{env_var_name}' 환경 변수에서 커스텀 버킷을 로드했습니다: {buckets}")
        return buckets
    except Exception as e:
        logging.warning(
            f"'{env_var_name}' 환경 변수 파싱 실패 (값: \"{buckets_str}\"). "
            f"에러: {e}. 기본 버킷을 사용합니다."
        )
        return default_buckets

# --- 메트릭 정의 ---
DEFAULT_LATENCY_BUCKETS = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1, 1.05, 1.1, 1.15, 1.2, 1.25, 1.3,
                           1.35, 1.4, 1.45, 1.5, 1.55, 1.6, 1.65, 1.7, 1.75, 1.8, 1.85, 1.9, 1.95, 2, 2.1, 2.2, 2.3,
                           2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 3, 4, 5]
latency_buckets = get_buckets_from_env("LATENCY_BUCKETS", DEFAULT_LATENCY_BUCKETS)

# 1. 엔드투엔드 처리 지연 시간 (Histogram)
LATENCY_HISTOGRAM = Histogram(
    'e2e_latency_seconds',
    '파일 생성(mtime)부터 DB POST 성공까지의 종단 간(E2E) 지연 시간',
    buckets=latency_buckets
)

# 2. 처리량 (Counter)
THROUGHPUT_COUNTER = Counter(
    'video_processed_total',
    '처리된 총 비디오 세그먼트 수',
    ['status']  # 'success' 또는 'failed' 라벨
)

# 3. EFS 스캔 자체에 걸린 시간 (Gauge)
EFS_SCAN_DURATION = Gauge(
    'video_file_scan_duration_seconds',
    'EFS /recordings 스캔 작업에 소요된 순수 시간'
)

# 4. /processing 폴더로의 파일 이동 시간 (Histogram)
DEFAULT_MOVE_BUCKETS = [0.01, 0.02, 0.03, 0.04, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1, 1.5, 2, 3, 4, 5]
move_buckets = get_buckets_from_env("MOVE_BUCKETS", DEFAULT_MOVE_BUCKETS)

FILE_MOVE_DURATION_SECONDS = Histogram(
    'video_file_move_duration_seconds',
    '/processing 폴더로 파일을 이동(move)하는 데 소요된 시간',
    buckets=move_buckets
)

def start_metrics_server():
    """프로메테우스 HTTP 서버 시작"""
    start_http_server(8000)
    logging.info("프로메테우스 서버가 8000번 포트에서 시작되었습니다.")