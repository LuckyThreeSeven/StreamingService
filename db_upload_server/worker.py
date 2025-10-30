import time
import shutil
import logging
import boto3
import requests
import config
from moviepy.editor import VideoFileClip
from pathlib import Path
from botocore.exceptions import ClientError
from datetime import datetime, timedelta

from prometheus_client import start_http_server, Counter, Histogram, Gauge
import os

# --- 로깅 설정 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


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


# 측정할 메트릭 정의 (전역 변수)
DEFAULT_LATENCY_BUCKETS = [0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10, 15, 30]
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
DEFAULT_MOVE_BUCKETS = [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
move_buckets = get_buckets_from_env("MOVE_BUCKETS", DEFAULT_MOVE_BUCKETS)
FILE_MOVE_DURATION_SECONDS = Histogram(
    'video_file_move_duration_seconds',
    '/processing 폴더로 파일을 이동(move)하는 데 소요된 시간',
    buckets=move_buckets
)

start_http_server(8000)

class VideoProcessor:
    """영상 파일 하나를 처리하는 모든 단계를 책임지는 클래스"""

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.original_filename = filepath.name
        self.video_info = {}
        self.parsed_data = {}

    def run(self, start_timestamp: float):
        """처리 파이프라인 전체를 실행합니다."""
        logging.info(f"'{self.original_filename}' 처리 시작.")
        try:
            # 1. 정보 파싱 및 새로운 파일명 생성
            self._parse_info()
            self._generate_new_names()
            logging.info(f"파싱된 정보: {self.video_info}")

            # 2. S3 업로드
            s3_url = self._upload_to_s3()
            if s3_url is None:
                raise Exception("S3 업로드에 실패했습니다.")
            self.video_info["s3_url"] = s3_url
            logging.info(f"'{self.original_filename}' 정보: {self.video_info}")

            # 3. 상태 서버로 정보 전송
            if not self._send_info_to_server():
                raise Exception("상태 서버로 정보 전송에 실패했습니다.")

            # --- Prometheus: 성공 시 메트릭 기록 ---
            # DB 전송 성공 직후, 지연 시간과 처리량을 기록합니다.
            end_timestamp = time.time()
            latency = end_timestamp - start_timestamp
            LATENCY_HISTOGRAM.observe(latency)
            THROUGHPUT_COUNTER.labels(status='success').inc()

            # 4. 성공 시 파일 이동
            self._move_to(config.COMPLETED_DIR)
            logging.info(f"'{self.original_filename}' 작업 완료.")

        except Exception as e:
            logging.error(f"'{self.original_filename}' 처리 중 에러 발생: {e}")

            # --- Prometheus: 실패 시 메트릭 기록 ---
            THROUGHPUT_COUNTER.labels(status='failed').inc()

            self._move_to(config.FAILED_DIR)

    def _parse_info(self):
        """경로와 파일로부터 메타데이터를 파싱하여 self.parsed_data에 저장합니다."""
        parts = self.filepath.parts
        base_index = parts.index(config.PROCESSING_DIR.name)

        created_at_utc = datetime.strptime(self.filepath.stem, "%Y%m%d-%H%M%S")

        stream_started_at_str = parts[base_index + 2]
        if stream_started_at_str == "offline":
            stream_started_at_utc = datetime(1970, 1, 1, 0, 0, 0)
        else:
            stream_started_at_utc = datetime.strptime(stream_started_at_str, "%Y%m%d-%H%M%S")
        stream_started_at_kst = self._change_utc_to_kst(stream_started_at_utc)

        with VideoFileClip(str(self.filepath)) as clip:
            duration = clip.duration

        # 파싱된 중간 결과물을 self.parsed_data에 저장
        self.parsed_data = {
            "blackbox_uuid": parts[base_index + 1],
            "stream_started_at_kst": stream_started_at_kst,
            "created_at_kst": self._change_utc_to_kst(created_at_utc),
            "file_type": self.filepath.suffix[1:],
            "file_size": self.filepath.stat().st_size,
            "duration": duration,
        }

    def _generate_new_names(self):
        """파싱된 데이터를 바탕으로 새 이름과 S3 키를 생성하고 최종 video_info를 완성합니다."""
        # _parse_info에서 저장한 중간 결과물을 사용
        created_at_kst = self.parsed_data["created_at_kst"]
        blackbox_uuid = self.parsed_data["blackbox_uuid"]
        file_type = self.parsed_data["file_type"]
        stream_started_at_kst = self.parsed_data["stream_started_at_kst"]

        # KST 기준으로 새로운 파일명과 S3 키 생성
        new_filename_kst = created_at_kst.strftime("%Y%m%d-%H%M%S") + f".{file_type}"
        new_s3_key = f"{blackbox_uuid}/{new_filename_kst}"

        # 최종 video_info 딕셔너리 완성
        self.video_info = {
            "blackbox_uuid": blackbox_uuid,
            "stream_started_at": stream_started_at_kst if isinstance(stream_started_at_kst,
                                                                     str) else stream_started_at_kst.isoformat(),
            "created_at": created_at_kst.isoformat(),
            "file_size": self.parsed_data["file_size"],
            "duration": self.parsed_data["duration"],
            "object_key": new_s3_key,
            "file_type": file_type,
        }

    def _change_utc_to_kst(self, utc_time) -> datetime:
        kst_timezone_delta = timedelta(hours=9)
        kst_time = utc_time + kst_timezone_delta
        return kst_time

    def _upload_to_s3(self) -> str | None:
        s3_key = self.video_info.get("object_key")
        if not s3_key: return None

        s3_client = boto3.client('s3')
        try:
            s3_client.upload_file(str(self.filepath), config.S3_BUCKET_NAME, s3_key)
            region = s3_client.meta.region_name
            s3_url = f"https://{config.S3_BUCKET_NAME}.s3.{region}.amazonaws.com/{s3_key}"
            logging.info(f"S3 업로드 성공. URL: {s3_url}")
            return s3_url
        except ClientError as e:
            logging.error(f"S3 업로드 실패: {e}")
            return None

    def _send_info_to_server(self) -> bool:
        try:
            response = requests.post(config.STATUS_SERVER_URL, json=self.video_info, timeout=10)
            response.raise_for_status()
            logging.info(f"상태 서버로 정보 전송 성공: {self.video_info.get('object_key')}")
            return True
        except requests.exceptions.RequestException as e:
            logging.error(f"상태 서버로 정보 전송 실패: {self.video_info.get('object_key')}, 에러: {e}")
            return False

    def _move_to(self, destination_dir: Path):
        try:
            s3_key = self.video_info.get("object_key")
            if not s3_key:
                s3_key = self.original_filename

            destination_path = destination_dir / s3_key
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(self.filepath, destination_path)
            logging.info(f"'{self.original_filename}'을 '{destination_path}' 경로로 이동.")
        except Exception as e:
            logging.error(f"'{self.original_filename}' 파일 이동 실패: {e}")


class FileScanner:
    """처리할 새로운 영상 파일을 찾아내는 클래스"""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.ignore_dirs = {config.PROCESSING_DIR, config.COMPLETED_DIR, config.FAILED_DIR}

    def find_new_videos(self) -> list[Path]:
        """새로운 비디오 파일 목록을 찾아 반환합니다."""
        all_videos = self.base_dir.glob('**/*.mp4')
        new_videos = []
        for video_path in all_videos:
            # 부모 폴더 중 무시할 폴더가 하나라도 포함되어 있는지 확인
            if not any(ignore_dir in video_path.parents for ignore_dir in self.ignore_dirs):
                new_videos.append(video_path)
        return new_videos


def main_loop():
    """메인 루프: 스캐너와 프로세서를 사용하여 전체 작업을 조율한다."""
    logging.info(f"워커 시작. '{config.BASE_DIR}' 폴더를 스캔합니다...")

    scanner = FileScanner(config.BASE_DIR)

    # --- Prometheus: EFS 스캔 시간 측정 ---
    scan_start_time = time.time()

    try:
        found_videos = scanner.find_new_videos()
    finally:
        scan_end_time = time.time()
        EFS_SCAN_DURATION.set(scan_end_time - scan_start_time)
    # ---

    for source_path in found_videos:
        try:

            # --- Prometheus: 지연 시간 측정을 위해 원본 mtime 확보 ---
            # (파일을 이동하기 전에 mtime을 가져와야 합니다)
            start_timestamp = os.path.getmtime(source_path)
            # ---

            relative_path = source_path.relative_to(config.BASE_DIR)

            if len(relative_path.parts) < 2:
                logging.warning(f"예상과 다른 경로 구조의 파일은 건너뜁니다: {source_path}")
                continue

            processing_path = config.PROCESSING_DIR / relative_path
            processing_path.parent.mkdir(parents=True, exist_ok=True)

            shutil.move(source_path, processing_path)
            move_end_time = time.time()
            move_duration = move_end_time - start_timestamp

            FILE_MOVE_DURATION_SECONDS.observe(move_duration)

            logging.info(f"'{source_path.name}' 파일을 processing 폴더로 이동.")

            # VideoProcessor 객체를 생성하고 실행 (파일 경로만 전달)
            processor = VideoProcessor(processing_path)
            # processor.run()
            # --- Prometheus: mtime을 인자로 전달 ---
            processor.run(start_timestamp=start_timestamp)

        except FileNotFoundError:
            continue
        except Exception as e:
            logging.error(f"'{source_path.name}' 파일을 처리하는 중 에러 발생: {e}")


if __name__ == "__main__":
    while True:
        main_loop()
        time.sleep(config.SCAN_INTERVAL_SECONDS)
