import logging
import shutil
import boto3
import requests
from botocore.exceptions import ClientError
from datetime import datetime, timedelta
from pathlib import Path
from moviepy.editor import VideoFileClip

# config에서 설정값을 가져옴
import config

class VideoProcessor:
    """영상 파일 하나를 처리하는 모든 단계를 책임지는 클래스"""

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.original_filename = filepath.name
        self.video_info = {}
        self.parsed_data = {}

    def _parse_info(self):
        """경로와 파일로부터 메타데이터를 파싱합니다."""
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

        self.parsed_data = {
            "blackbox_uuid": parts[base_index + 1],
            "stream_started_at_kst": stream_started_at_kst,
            "created_at_kst": self._change_utc_to_kst(created_at_utc),
            "file_type": self.filepath.suffix[1:],
            "file_size": self.filepath.stat().st_size,
            "duration": duration,
        }

    def _generate_new_names(self):
        """파싱된 데이터를 바탕으로 새 이름과 S3 키를 생성합니다."""
        created_at_kst = self.parsed_data["created_at_kst"]
        blackbox_uuid = self.parsed_data["blackbox_uuid"]
        file_type = self.parsed_data["file_type"]
        stream_started_at_kst = self.parsed_data["stream_started_at_kst"]

        new_filename_kst = created_at_kst.strftime("%Y%m%d-%H%M%S") + f".{file_type}"
        new_s3_key = f"{blackbox_uuid}/{new_filename_kst}"

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
        """S3 업로드. 실패 시 None 반환."""
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
        """상태 서버 전송. 실패 시 False 반환."""
        try:
            response = requests.post(config.STATUS_SERVER_URL, json=self.video_info, timeout=10)
            response.raise_for_status()
            logging.info(f"상태 서버로 정보 전송 성공: {self.video_info.get('object_key')}")
            return True
        except requests.exceptions.RequestException as e:
            logging.error(f"상태 서버로 정보 전송 실패: {self.video_info.get('object_key')}, 에러: {e}")
            return False

    def _move_to(self, destination_dir: Path):
        """파일을 최종 목적지로 이동."""
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