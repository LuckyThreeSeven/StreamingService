import logging
import time
import os
import shutil
from pathlib import Path

# config, global_state 분리 임포트
import config
import global_state
from models import JobItem
from metrics import EFS_SCAN_DURATION, FILE_MOVE_DURATION_SECONDS

class FileScanner:
    """처리할 새로운 영상 파일을 찾아내는 클래스"""
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        # config에서 경로를 가져옴
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

def main_scanner_loop():
    """메인 루프: 스캐너 역할만 수행하며 WORK_QUEUE에 작업을 추가한다."""
    # config에서 BASE_DIR을 가져옴
    logging.info(f"스캐너 실행. '{config.BASE_DIR}' 폴더를 스캔합니다...")
    scanner = FileScanner(config.BASE_DIR)

    scan_start_time = time.time()
    try:
        found_videos = scanner.find_new_videos()
    finally:
        scan_end_time = time.time()
        EFS_SCAN_DURATION.set(scan_end_time - scan_start_time)

    if not found_videos:
        return # 처리할 파일 없음

    logging.info(f"{len(found_videos)}개의 새 파일을 발견. 1차 작업 큐에 추가합니다.")

    for source_path in found_videos:
        try:
            start_timestamp = os.path.getmtime(source_path)
            # config에서 BASE_DIR을 가져옴
            relative_path = source_path.relative_to(config.BASE_DIR)

            if len(relative_path.parts) < 2:
                logging.warning(f"예상과 다른 경로 구조의 파일은 건너뜁니다: {source_path}")
                continue

            # config에서 PROCESSING_DIR을 가져옴
            processing_path = config.PROCESSING_DIR / relative_path
            processing_path.parent.mkdir(parents=True, exist_ok=True)

            # --- 파일 이동 시간 측정 ---
            move_start_time = time.time()
            shutil.move(source_path, processing_path)
            move_duration = time.time() - move_start_time
            FILE_MOVE_DURATION_SECONDS.observe(move_duration)
            # ---

            logging.info(f"'{source_path.name}' 파일을 processing 폴더로 이동.")
            
            # 1차 처리를 직접 하지 않고, WORK_QUEUE에 JobItem을 추가
            job = JobItem(filepath=processing_path, start_timestamp=start_timestamp, attempts=1)
            global_state.WORK_QUEUE.put(job)

        except FileNotFoundError:
            # 스캔과 이동 사이에 다른 워커가 파일을 가져간 경우 (경쟁 조건)
            logging.warning(f"'{source_path.name}' 처리 시도 중 파일을 찾을 수 없음 (무시).")
            continue
        except Exception as e:
            logging.error(f"'{source_path.name}' 파일을 큐에 추가하는 중 에러 발생: {e}", exc_info=True)