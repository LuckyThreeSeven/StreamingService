import time
import logging

# config, global_state 임포트
import config
import global_state
import metrics
from workers import PrimaryWorker, RetryScheduler, RetryWorker
from scanner import main_scanner_loop

def main():
    # 1. 로깅 설정
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.info("애플리케이션 시작...")

    # 2. 프로메테우스 메트릭 서버 시작
    metrics.start_metrics_server()

    # 3. 1차 처리 워커 스레드 풀 시작
    # config에서 'NUM_WORKERS' 사용
    logging.info(f"{config.NUM_WORKERS}개의 1차 처리 워커를 시작합니다.")
    for _ in range(config.NUM_WORKERS):
        PrimaryWorker().start()

    # 4. 재시도 스케줄러 스레드 시작
    RetryScheduler().start()

    # 5. 재시도 워커 스레드 풀 시작
    # config에서 'NUM_RETRY_WORKER' 사용
    logging.info(f"{config.NUM_RETRY_WORKER}개의 재시도 워커를 시작합니다.")
    for _ in range(config.NUM_RETRY_WORKER):
        RetryWorker().start()

    # 6. 메인 스레드는 스캐너 루프만 실행
    logging.info("메인 스캐너 루프를 시작합니다.")
    while True:
        main_scanner_loop()
        logging.info(
            f"다음 스캔까지 {config.SCAN_INTERVAL_SECONDS}초 대기... "
            # global_state에서 큐를 가져옴
            f"(1차 큐: {global_state.WORK_QUEUE.qsize()}, "
            f"스케줄 큐: {global_state.SCHEDULER_QUEUE.qsize()}, "
            f"재시도 큐: {global_state.RETRY_QUEUE.qsize()})"
        )
        time.sleep(config.SCAN_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()