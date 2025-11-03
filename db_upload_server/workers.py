import logging
import time
from threading import Thread
from datetime import datetime, timedelta
import requests
from botocore.exceptions import ClientError

# config, global_state 분리 임포트
import config
import global_state
from models import JobItem
from video_processor import VideoProcessor
from metrics import LATENCY_HISTOGRAM, THROUGHPUT_COUNTER

class PrimaryWorker(Thread):
    """1차 처리 워커 (WORK_QUEUE 담당)"""
    def __init__(self):
        super().__init__()
        self.daemon = True

    def run(self):
        while True:
            # global_state에서 큐를 가져옴
            job_item: JobItem = global_state.WORK_QUEUE.get()
            processor = VideoProcessor(job_item.filepath)
            
            try:
                logging.info(f"'{processor.original_filename}' 1차 처리 시작.")
                
                # 1. 파싱 (영구 실패 가능)
                processor._parse_info()
                processor._generate_new_names()
                
                # 2. S3 업로드 (일시적 실패 가능)
                s3_url = processor._upload_to_s3()
                if s3_url is None:
                    raise requests.exceptions.RequestException("S3 업로드에 실패했습니다.")
                processor.video_info["s3_url"] = s3_url

                # 3. 상태 서버 전송 (일시적 실패 가능)
                if not processor._send_info_to_server():
                    raise requests.exceptions.RequestException("상태 서버로 정보 전송에 실패했습니다.")
                
                # 4. 1차 처리 성공
                end_timestamp = time.time()
                latency = end_timestamp - job_item.start_timestamp # mtime 기준
                LATENCY_HISTOGRAM.observe(latency)
                THROUGHPUT_COUNTER.labels(status='success').inc()
                processor._move_to(config.COMPLETED_DIR)
                logging.info(f"'{processor.original_filename}' 1차 처리 작업 완료.")

            except (ClientError, requests.exceptions.RequestException) as e:
                # 5. 일시적 실패 -> 스케줄 큐로 이동
                logging.warning(f"'{processor.original_filename}' 1차 처리 실패. {config.RETRY_DELAY_MINUTES}분 뒤 재시도하도록 스케줄합니다. 에러: {e}")
                
                # JobItem에 파싱된 정보(video_info)를 저장
                job_item.video_info = processor.video_info 
                job_item.next_retry_time = datetime.now() + timedelta(minutes=config.RETRY_DELAY_MINUTES)
                global_state.SCHEDULER_QUEUE.put(job_item)

            except Exception as e:
                # 6. 영구적 실패 (파싱 등) -> FAILED_DIR로 이동
                logging.error(f"'{processor.original_filename}' 1차 처리 중 영구적 에러 발생: {e}", exc_info=True)
                THROUGHPUT_COUNTER.labels(status='failed').inc()
                processor._move_to(config.FAILED_DIR)
            
            finally:
                global_state.WORK_QUEUE.task_done()

class RetryScheduler(Thread):
    """재시도 스케줄러 (SCHEDULER_QUEUE -> RETRY_QUEUE)"""
    def __init__(self):
        super().__init__()
        self.daemon = True

    def run(self):
        while True:
            # config에서 스케줄 간격을 가져옴
            time.sleep(config.SCHEDULER_INTERVAL_SECONDS)
            logging.debug(f"스케줄러 실행. {global_state.SCHEDULER_QUEUE.qsize()}개 항목 확인 중...")
            now = datetime.now()
            
            items_to_requeue = []
            
            # global_state에서 큐를 가져옴
            for _ in range(global_state.SCHEDULER_QUEUE.qsize()):
                try:
                    item: JobItem = global_state.SCHEDULER_QUEUE.get_nowait()
                    
                    # 시간이 되었는지 확인
                    if item.next_retry_time <= now:
                        # 시간이 되었으면 -> RETRY_QUEUE(작업 큐)로 이동
                        logging.info(f"'{item.filepath.name}' 재시도 시간 도래. 작업 큐로 이동.")
                        global_state.RETRY_QUEUE.put(item)
                    else:
                        # 아직 시간이 안 됐으면 -> 다시 SCHEDULER_QUEUE에 넣음
                        items_to_requeue.append(item)
                        
                except Exception:
                    # 큐가 비어있으면 중단
                    break
            
            # 큐에 다시 넣기
            for item in items_to_requeue:
                global_state.SCHEDULER_QUEUE.put(item)

class RetryWorker(Thread):
    """재시도 워커 (RETRY_QUEUE 담당)"""
    def __init__(self):
        super().__init__()
        self.daemon = True

    def run(self):
        while True:
            # global_state에서 큐를 가져옴
            retry_item: JobItem = global_state.RETRY_QUEUE.get()
            
            if not retry_item.filepath.exists():
                logging.warning(f"'{retry_item.filepath.name}' 재시도 하려했으나 파일이 PROCESSING에 없습니다. 작업을 스킵합니다.")
                global_state.RETRY_QUEUE.task_done()
                continue
            
            processor = VideoProcessor(retry_item.filepath)
            processor.video_info = retry_item.video_info # 1차 처리 때 파싱한 정보 사용
            
            logging.info(f"재시도 처리 시작: {processor.original_filename} (시도 {retry_item.attempts})")
            
            try:
                # 1. S3/서버 전송 재시도 (파싱은 건너뜀)
                s3_url = processor._upload_to_s3()
                if s3_url is None: raise Exception("S3 업로드 재시도 실패")
                processor.video_info["s3_url"] = s3_url
                if not processor._send_info_to_server(): raise Exception("상태 서버 전송 재시도 실패")

                # 2. 재시도 성공
                processor._move_to(config.COMPLETED_DIR)
                THROUGHPUT_COUNTER.labels(status='success').inc()
                logging.info(f"재시도 성공: {processor.original_filename}")

            except Exception as e:
                # 3. 재시도 또 실패
                retry_item.attempts += 1
                # config에서 최대 재시도 횟수를 가져옴
                if retry_item.attempts <= config.MAX_RETRIES:
                    # 10분 뒤 재시도하도록 다시 스케줄 큐에 넣음
                    logging.warning(f"재시도 또 실패. {config.RETRY_DELAY_MINUTES}분 뒤 재시도하도록 스케줄: {e}")
                    retry_item.next_retry_time = datetime.now() + timedelta(minutes=config.RETRY_DELAY_MINUTES)
                    global_state.SCHEDULER_QUEUE.put(retry_item)
                else:
                    # 4. 최종 실패
                    logging.error(f"최대 재시도({config.MAX_RETRIES}) 실패. FAILED_DIR로 이동: {processor.original_filename}")
                    THROUGHPUT_COUNTER.labels(status='failed').inc()
                    processor._move_to(config.FAILED_DIR)
            finally:
                global_state.RETRY_QUEUE.task_done()