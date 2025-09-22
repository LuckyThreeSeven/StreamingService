import time
import shutil
import logging
from moviepy.editor import VideoFileClip
from pathlib import Path
import boto3
from botocore.exceptions import ClientError
import logging

# --- 설정 ---
BASE_DIR = Path("../server/recordings")
S3_BUCKET_NAME = "nev-video-bucket"
STATUS_SERVER_URL = "http://status-server.com/api/video-info" # TODO : 상태 서버 URL 수정

NEW_DIR = BASE_DIR / "new"
PROCESSING_DIR = BASE_DIR / "processing"
COMPLETED_DIR = BASE_DIR / "completed"
FAILED_DIR = BASE_DIR / "failed"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def upload_to_s3(local_filepath, bucket_name, s3_object_key):
    """
    파일을 S3 버킷에 업로드한다.
    :param local_filepath: 업로드할 로컬 파일의 경로 (Path 객체)
    :param bucket_name: 업로드할 S3 버킷 이름
    :param s3_object_key: S3 버킷에 저장될 파일의 이름/경로
    :return: 업로드 성공 시 파일 URL, 실패 시 None
    """
    s3_client = boto3.client('s3')
    
    try:
        logging.info(f"S3 오브젝트 키: {s3_object_key}")
        # boto3의 upload_file 메서드는 대용량 파일(영상 등)을 알아서
        # 여러 부분으로 나누어(multipart) 효율적으로 업로드해줍니다.
        s3_client.upload_file(
            str(local_filepath),  # 로컬 파일 경로 (문자열이어야 함)
            bucket_name,          # 버킷 이름
            s3_object_key,        # S3에 저장될 객체 키 (파일 이름)
        )
        
        # 업로드된 파일의 URL 생성
        # 리전 정보를 가져와서 정확한 URL을 만듭니다.
        region = s3_client.meta.region_name
        s3_url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{s3_object_key}"
        
        logging.info(f"S3 업로드 성공. URL: {s3_url}")
        return s3_url

    except ClientError as e:
        logging.error(f"S3 업로드 실패: {e}")
        return None
    except FileNotFoundError:
        logging.error(f"S3에 업로드할 파일을 찾을 수 없습니다: {local_filepath}")
        return None

def process_file(filepath: Path, s3_key): # 타입 힌트를 Path로 명시하면 더 좋습니다.
    """하나의 파일을 받아 모든 처리 단계를 수행한다."""
    # os.path.basename(filepath) 대신 .name 속성을 사용
    filename = filepath.name
    logging.info(f"'{filename}' 처리 시작.")
    logging.info(f"S3에 저장될 경로(Key): {s3_key}")

    try:
        # 1. 메타데이터 추출
        # TODO : API 명세에 맞게 추출 (파일명, UUID 등)
        file_size = filepath.stat().st_size
        with VideoFileClip(str(filepath)) as clip: # moviepy는 문자열 경로가 필요
            duration = clip.duration
        logging.info(f"파일 크기: {file_size}, 파일 길이: {duration}")

        # 2. S3에 업로드
        # S3에 저장할 파일 이름/경로를 정의합니다. 여기서는 원본 파일명을 그대로 사용합니다.
        s3_url = upload_to_s3(filepath, S3_BUCKET_NAME, s3_key)

        # 업로드 실패 시 예외 발생시켜 FAILED 처리
        if s3_url is None:
            raise Exception("S3 업로드에 실패했습니다.")
        logging.info(f"'{filename}' S3 업로드 성공 (시뮬레이션).")

        # 3. 다른 서버에 정보 전송
        # TODO: 1번 후 구현
        video_info = {
            "filename": filename,
            "size": file_size,
            "duration": duration
        }
        logging.info(f"'{filename}' 다른 서버로 정보 전송 성공.")
        
        # 4. 모든 작업 성공 시, completed 폴더로 이동
        completed_path = COMPLETED_DIR / filename
        shutil.move(filepath, completed_path)
        logging.info(f"'{filename}' 작업 완료. completed 폴더로 이동.")

    except Exception as e:
        # 5. 어떤 단계든 실패 시, failed 폴더로 이동
        logging.error(f"'{filename}' 처리 중 에러 발생: {e}")
        failed_path = FAILED_DIR / filename
        # 실패 시 목적지 폴더가 없을 수 있으므로 생성
        failed_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(filepath, failed_path)

def main_loop():
    """메인 루프: new 폴더를 스캔하고 작업을 분배한다."""
    logging.info("워커 시작. new 폴더를 스캔합니다...")
    
    # 1. new 폴더에서 처리할 파일 찾기
    # .glob('**/*.mp4')를 사용해 모든 하위 폴더의 .mp4 파일을 찾음
    found_videos = list(NEW_DIR.glob('**/*.mp4'))
    print(found_videos)

    # 결과 출력
    for video_path in found_videos:
        source_path = video_path

        # 처리 중 경로는 소스 경로의 'new' 부분을 'processing'으로 바꿔서 만듦
        # str()로 감싸서 문자열로 바꾼 뒤 replace 함수를 사용합니다.
        processing_path = Path(
            str(source_path).replace(str(NEW_DIR), str(PROCESSING_DIR), 1)
        )

        print(f"파일 원본 경로: {source_path}")
        print(f"파일 처리 경로: {processing_path}\n")

        try:
            # 1. 파일을 옮기기 전에 원본 경로(source_path)로 S3 키를 미리 계산합니다.
            relative_path = source_path.relative_to(NEW_DIR)
            uuid_folder = relative_path.parts[0]
            filename = relative_path.name
            s3_key = f"{uuid_folder}/{filename}"

            # 1-2. 파일을 옮길 목적지 폴더 경로를 가져옴
            destination_parent_dir = processing_path.parent
            
            # 2. 목적지 폴더가 없다면, 중간 폴더까지 포함하여 모두 생성
            #    exist_ok=True는 폴더가 이미 있어도 에러를 발생시키지 않음
            destination_parent_dir.mkdir(parents=True, exist_ok=True)

            # 3. 파일을 processing 폴더로 이동시켜 '선점(Lock)'
            # 이 작업으로 다른 워커가 이 파일을 동시에 처리하는 것을 막음
            logging.info(f"파일 이동 중...: {source_path} -> {destination_parent_dir}")
            shutil.move(source_path, processing_path)
            
            # 3. 실제 파일 처리 함수 호출
            process_file(processing_path, s3_key)
            
        except FileNotFoundError:
            # 다른 워커가 방금 파일을 옮긴 경우, 무시하고 넘어감
            continue
        except Exception as e:
            logging.error(f"'{source_path}' 파일을 옮기는 중 에러 발생: {e}")


if __name__ == "__main__":
    while True:
        main_loop()
        time.sleep(10) # 10초마다 new 폴더 스캔