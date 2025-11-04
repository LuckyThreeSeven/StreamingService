from pathlib import Path
from datetime import datetime

class JobItem:
    """
    큐를 통해 전달되는 작업 아이템(정보 전달)
    속성:
        filepath (Path): 처리할 비디오 파일의 경로 (/processing/...)
        start_timestamp (float): E2E 지연 시간 측정을 위한 파일의 mtime
        video_info (dict): 1차 워커가 파싱 후 채우는 비디오 메타데이터
        attempts (int): 현재까지의 재시도 횟수
        next_retry_time (datetime): 다음 재시도 예정 시간
    """
    def __init__(self, filepath: Path, start_timestamp: float, attempts: int = 1):
        self.filepath = filepath # /processing/... 경로
        self.start_timestamp = start_timestamp # E2E 지연 시간 측정을 위한 mtime
        self.video_info = {}     # 1차 워커가 파싱 후 채움
        self.attempts = attempts
        self.next_retry_time: datetime = datetime.now() # 다음 재시도 시간