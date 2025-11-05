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
DEFAULT_LATENCY_BUCKETS = [1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 3.0, 3.1, 3.2,
                           3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 4.0, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 5.0,
                           5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 6.0, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8,
                           6.9, 7.0, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 8.0, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6,
                           8.7, 8.8, 8.9, 9.0, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 10.0]
latency_buckets = get_buckets_from_env("LATENCY_BUCKETS", DEFAULT_LATENCY_BUCKETS)

# 엔드투엔드 처리 지연 시간 (Histogram)
LATENCY_HISTOGRAM = Histogram(
    'e2e_latency_seconds',
    '파일 생성(mtime)부터 DB POST 성공까지의 종단 간(E2E) 지연 시간',
    buckets=latency_buckets
)

# 처리량 (Counter)
THROUGHPUT_COUNTER = Counter(
    'video_processed_total',
    '처리된 총 비디오 세그먼트 수',
    ['status']  # 'success' 또는 'failed' 라벨
)

DEFAULT_SCAN_BUCKETS = [0.01, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8,
                        0.85, 0.9, 0.95, 1, 3, 5]
scan_buckets = get_buckets_from_env("SCAN_BUCKETS", DEFAULT_SCAN_BUCKETS)
# EFS/EBS 스캔 자체에 걸린 시간 (Histogram)
FILE_SCAN_DURATION = Histogram(
    'video_file_scan_duration_seconds',  # 메트릭 이름은 그대로 사용 (기술 중립적)
    'Storage /recordings 스캔 작업에 소요된 순수 시간',  # 설명에서 'EFS' 제거
    buckets=scan_buckets
)

# FAILED_DIR에 쌓인 파일 개수 (Gauge)
FAILED_FILES_GAUGE = Gauge(
    'failed_files_in_directory_total',
    '현재 /failed 폴더에 쌓여있는 파일의 총 개수'
)


def start_metrics_server():
    """프로메테우스 HTTP 서버 시작"""
    start_http_server(8000)
    logging.info("프로메테우스 서버가 8000번 포트에서 시작되었습니다.")
    logging.info(f"LATENCY_HISTOGRAM 버킷: {latency_buckets}")
    logging.info(f"FILE_SCAN_DURATION 버킷: {scan_buckets}")
