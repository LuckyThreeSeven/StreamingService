from pathlib import Path
from datetime import datetime

class JobItem:
    """큐를 통해 전달되는 작업 아이템"""
    def __init__(self, filepath: Path, start_timestamp: float, attempts: int = 1):
        self.filepath = filepath # /processing/... 경로
        self.start_timestamp = start_timestamp # E2E 지연 시간 측정을 위한 mtime
        self.video_info = {}     # 1차 워커가 파싱 후 채움
        self.attempts = attempts
        self.next_retry_time: datetime = datetime.now() # 다음 재시도 시간