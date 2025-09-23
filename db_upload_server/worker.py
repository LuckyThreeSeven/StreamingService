import time
import shutil
import logging
from moviepy.editor import VideoFileClip
from pathlib import Path
import boto3
from botocore.exceptions import ClientError
import requests
from datetime import datetime
import config

# --- 로깅 설정 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class VideoProcessor:
    """영상 파일 하나를 처리하는 모든 단계를 책임지는 클래스"""

    def __init__(self, filepath: Path, s3_key: str):
        self.filepath = filepath
        self.s3_key = s3_key
        self.filename = filepath.name

    def run(self):
        """처리 파이프라인 전체를 실행합니다."""
        logging.info(f"'{self.filename}' 처리 시작.")
        try:
            # 1. 정보 파싱
            video_info = self._parse_info()
            
            # 2. S3 업로드
            s3_url = self._upload_to_s3()
            if s3_url is None:
                raise Exception("S3 업로드에 실패했습니다.")
            video_info["s3_url"] = s3_url

            # TODO : 상태 서버와 연결 테스트            
            # 3. 상태 서버로 정보 전송
            # if not self._send_info_to_server(video_info):
            #     raise Exception("상태 서버로 정보 전송에 실패했습니다.")
            
            # 4. 성공 시 파일 이동
            self._move_to(config.COMPLETED_DIR)
            logging.info(f"'{self.filename}' 작업 완료.")

        except Exception as e:
            logging.error(f"'{self.filename}' 처리 중 에러 발생: {e}")
            self._move_to(config.FAILED_DIR)

    def _parse_info(self) -> dict:
        """경로와 파일로부터 메타데이터를 파싱합니다."""
        parts = self.filepath.parts
        base_index = parts.index(config.PROCESSING_DIR.name)
        
        blackbox_uuid = parts[base_index + 1]
        stream_started_at_str = parts[base_index + 2]
        created_at_str = self.filepath.stem
        file_type = self.filepath.suffix[1:]

        stream_started_at = datetime.strptime(stream_started_at_str, "%Y%m%d-%H%M%S")
        created_at = datetime.strptime(created_at_str, "%Y%m%d-%H%M%S")
        
        file_size = self.filepath.stat().st_size
        with VideoFileClip(str(self.filepath)) as clip:
            duration = clip.duration

        return {
            "blackbox_uuid": blackbox_uuid,
            "stream_started_at": stream_started_at.isoformat(),
            "created_at": created_at.isoformat(),
            "file_size": file_size,
            "duration": round(duration, 2),
            "object_key": self.s3_key,
            "file_type": file_type,
        }

    def _upload_to_s3(self) -> str | None:
        """파일을 S3에 업로드합니다."""
        s3_client = boto3.client('s3')
        try:
            s3_client.upload_file(str(self.filepath), config.S3_BUCKET_NAME, self.s3_key)
            region = s3_client.meta.region_name
            s3_url = f"https://{config.S3_BUCKET_NAME}.s3.{region}.amazonaws.com/{self.s3_key}"
            logging.info(f"S3 업로드 성공. URL: {s3_url}")
            return s3_url
        except ClientError as e:
            logging.error(f"S3 업로드 실패: {e}")
            return None

    def _send_info_to_server(self, data: dict) -> bool:
        """파싱된 정보를 상태 서버로 전송합니다."""
        try:
            response = requests.post(config.STATUS_SERVER_URL, json=data, timeout=10)
            response.raise_for_status()
            logging.info(f"상태 서버로 정보 전송 성공: {data.get('object_key')}")
            return True
        except requests.exceptions.RequestException as e:
            logging.error(f"상태 서버로 정보 전송 실패: {data.get('object_key')}, 에러: {e}")
            return False

    def _move_to(self, destination_dir: Path):
        """파일을 지정된 목적지 디렉터리로 이동시킵니다."""
        try:
            # s3_key를 사용하여 폴더 구조를 유지
            destination_path = destination_dir / self.s3_key
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(self.filepath, destination_path)
            logging.info(f"'{self.filename}'을 '{destination_path}' 경로로 이동.")
        except Exception as e:
            logging.error(f"'{self.filename}' 파일 이동 실패: {e}")


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
    found_videos = scanner.find_new_videos()

    for source_path in found_videos:
        try:
            relative_path = source_path.relative_to(config.BASE_DIR)
            
            if len(relative_path.parts) < 2:
                logging.warning(f"예상과 다른 경로 구조의 파일은 건너뜁니다: {source_path}")
                continue
            
            uuid_folder = relative_path.parts[0]
            filename = relative_path.name
            s3_key = f"{uuid_folder}/{filename}"

            processing_path = config.PROCESSING_DIR / relative_path
            processing_path.parent.mkdir(parents=True, exist_ok=True)
            
            shutil.move(source_path, processing_path)
            logging.info(f"'{source_path.name}' 파일을 processing 폴더로 이동.")
            
            # VideoProcessor 객체를 생성하고 실행하여 파일 처리
            processor = VideoProcessor(processing_path, s3_key)
            processor.run()
            
        except FileNotFoundError:
            continue
        except Exception as e:
            logging.error(f"'{source_path.name}' 파일을 처리하는 중 에러 발생: {e}")

if __name__ == "__main__":
    while True:
        main_loop()
        time.sleep(config.SCAN_INTERVAL_SECONDS)