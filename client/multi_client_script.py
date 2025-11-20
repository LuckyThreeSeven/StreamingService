# multi_client.py

import subprocess
import time
import os
import sys

# --- 테스트 설정 ---
NUM_PROCESSES = 2  # 👈 동시에 실행할 클라이언트(스트림) 수

# --------------------

def run_client(client_uuid):
    """
    고유한 CLIENT_UUID 환경 변수를 설정하여
    client.py 스크립트를 별도의 프로세스로 실행합니다.
    """
    print(f"[Launcher] 클라이언트 프로세스 시작: {client_uuid}")

    # 현재 스크립트의 환경 변수를 복사
    env = os.environ.copy()

    # ⚠️ 이 프로세스 고유의 CLIENT_UUID를 환경 변수로 주입
    env['CLIENT_UUID'] = client_uuid

    try:
        # Popen을 사용하여 client.py를 비동기적으로 실행
        process = subprocess.Popen(
            [sys.executable, 'client_script.py'],  # sys.executable은 'python3' 또는 'python'
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return process
    except Exception as e:
        print(f"❌ [Launcher] {client_uuid} 시작 실패: {e}")
        return None


if __name__ == "__main__":
    processes = []

    print(f"🚀 {NUM_PROCESSES}개의 동시 스트림 부하 테스트를 시작합니다...")

    try:
        # 설정한 수만큼 클라이언트 프로세스 시작
        for i in range(NUM_PROCESSES):
            client_id = f"load-test-client-{i + 1}"  # 고유한 UUID 생성
            proc = run_client(client_id)
            if proc:
                processes.append(proc)
            time.sleep(0.5)  # 서버에 한 번에 몰리지 않도록 0.5초 간격으로 시작

        print(f"\n✅ {len(processes)}개의 클라이언트가 실행 중입니다. (Ctrl+C로 종료)")

        # 모든 프로세스가 종료될 때까지 대기
        for proc in processes:
            proc.wait()  # 각 프로세스가 끝날 때까지 기다림

            # (선택 사항) 각 프로세스의 로그 출력
            stdout, stderr = proc.communicate()
            print(f"\n--- [Launcher] {proc.args[1]} (PID: {proc.pid}) 로그 ---")
            if stdout:
                print("[STDOUT]:\n", stdout)
            if stderr:
                print("[STDERR]:\n", stderr)
            print("-------------------------------------------------")

    except KeyboardInterrupt:
        print("\n🚫 [Launcher] 사용자에 의해 중단 요청. 모든 클라이언트 프로세스를 종료합니다...")
        for proc in processes:
            proc.terminate()  # 자식 프로세스들에게 종료 신호 전송
        print("모든 프로세스 종료 완료.")

    except Exception as e:
        print(f"❌ [Launcher] 메인 프로세스 오류: {e}")

    finally:
        print("[Launcher] 부하 테스트 종료.")