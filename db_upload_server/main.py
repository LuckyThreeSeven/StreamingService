import time
import shutil
import logging
from moviepy.editor import VideoFileClip
from pathlib import Path
import boto3
from botocore.exceptions import ClientError
import requests
from datetime import datetime

# --- 설정 ---
BASE_DIR = Path("../server/recordings")
S3_BUCKET_NAME = "nev-video-bucket"
STATUS_SERVER_URL = "http://status-server.com/metadata" # TODO : 상태 서버 URL 수정

NEW_DIR = BASE_DIR / "new"
PROCESSING_DIR = BASE_DIR / "processing"
COMPLETED_DIR = BASE_DIR / "completed"
FAILED_DIR = BASE_DIR / "failed"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def upload_to_s3(local_filepath, bucket_name, s3_object_key):
    s3_client = boto3.client('s3')
    logging.info(f"S3 오브젝트 키: {s3_object_key}")
    
    try:
        s3_client.upload_file(
            str(local_filepath),
            bucket_name,
            s3_object_key,
        )
        
        region = s3_client.meta.region_name
        s3_url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{s3_object_key}"
        logging.info(f"S3 업로드 성공. URL: {s3_url}")
        return s3_url
    except ClientError as e:
        logging.error(f"S3 업로드 실패: {e}")
        return None
    except FileNotFoundError:
        logging.error(f"S3에 업로드할 파일을 찾을 수 없습니다: {local_filepath}")
        return 

# TODO : 연결 테스트 필요
def send_info_to_status_server(data):
    try:
        # response = requests.post(STATUS_SERVER_URL, json=data, timeout=10)
        # response.raise_for_status()
        logging.info(f"테스트 - 상태 서버로 정보 전송 성공: {data.get('object_key')}")
        logging.info(data)
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"테스트 - 상태 서버로 정보 전송 실패: {data.get('object_key')}, 에러: {e}")
        return False

def process_file(filepath: Path, s3_key: str):
    """하나의 파일을 받아 모든 처리 단계를 수행한다."""
    filename = filepath.name
    logging.info(f"'{filename}' 처리 시작.")

    try:
        # 1. 경로 및 파일 정보 파싱
        parts = filepath.parts
        base_index = parts.index('processing') # 기준을 'processing'으로 변경
        
        blackbox_uuid = parts[base_index + 1]
        stream_started_at_str = parts[base_index + 2]
        created_at_str = filepath.stem
        file_type = filepath.suffix[1:]

        stream_started_at = datetime.strptime(stream_started_at_str, "%Y%m%d-%H%M%S")
        created_at = datetime.strptime(created_at_str, "%Y%m%d-%H%M%S")
        
        file_size = filepath.stat().st_size
        with VideoFileClip(str(filepath)) as clip:
            duration = clip.duration

        # 2. S3 업로드
        s3_url = upload_to_s3(filepath, S3_BUCKET_NAME, s3_key)
        if s3_url is None:
            raise Exception("S3 업로드에 실패했습니다.")

        # 3. 다른 서버에 정보 전송
        video_info = {
            "blackbox_uuid": blackbox_uuid,
            "stream_started_at": stream_started_at.isoformat(), # datetime을 ISO 형식 문자열로 변환
            "created_at": created_at.isoformat(),
            "file_size": file_size,
            "duration": round(duration, 2), # 소수점 2자리까지만 표시
            "object_key": s3_key,
            "file_type": file_type
        }
        if not send_info_to_status_server(video_info):
            raise Exception("상태 서버로 정보 전송에 실패했습니다.")
        
        # 4. 모든 작업 성공 시, completed 폴더로 이동
        # s3_key를 사용하여 폴더 구조를 유지
        completed_path = COMPLETED_DIR / s3_key
        completed_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(filepath, completed_path)
        logging.info(f"'{filename}' 작업 완료. '{completed_path}' 경로로 이동.")

    except Exception as e:
        # 5. 실패 시, failed 폴더로 이동
        logging.error(f"'{filename}' 처리 중 에러 발생: {e}")
        failed_path = FAILED_DIR / s3_key
        failed_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(filepath, failed_path)

def main_loop():
    """메인 루프: new 폴더를 스캔하고 작업을 분배한다."""
    logging.info("워커 시작. new 폴더를 스캔합니다...")
    
    found_videos = list(BASE_DIR.glob('**/*.mp4'))

    for source_path in found_videos:
        # 'processing', 'completed', 'failed' 폴더 안에 있는 파일 건너뜀
        if PROCESSING_DIR in source_path.parents or \
           COMPLETED_DIR in source_path.parents or \
           FAILED_DIR in source_path.parents:
            continue

        try:
            # 목적지 폴더 생성
            relative_path = source_path.relative_to(BASE_DIR)

            # s3 키 생성
            uuid_folder = relative_path.parts[0]
            filename = relative_path.name
            s3_key = f"{uuid_folder}/{filename}"

            processing_path = PROCESSING_DIR / relative_path
            processing_path.parent.mkdir(parents=True, exist_ok=True)

            shutil.move(source_path, processing_path)
            logging.info(f"'{source_path.name}' 파일을 processing 폴더로 이동.")
            
            process_file(processing_path, s3_key)
            
        except FileNotFoundError:
            continue
        except Exception as e:
            logging.error(f"'{source_path.name}' 파일을 처리하는 중 에러 발생: {e}")

if __name__ == "__main__":
    while True:
        main_loop()
        time.sleep(10) # 10초마다 new 폴더 스캔