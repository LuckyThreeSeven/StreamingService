from queue import Queue

# 1차 처리를 위한 작업 큐
WORK_QUEUE = Queue()
# 재시도 전용 작업 큐
RETRY_QUEUE = Queue()
# 실패 작업 대기 큐
SCHEDULER_QUEUE = Queue()