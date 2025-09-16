import subprocess
import uuid
import sys
from datetime import datetime

# --- 설정 ---
SERVER_IP = '127.0.0.1'
SERVER_PORT = 8890  # MediaMTX에 설정한 SRT 포트

# --- 동적 streamid 생성 ---
# 1. 클라이언트를 식별하기 위한 고유 ID를 생성합니다.
CLIENT_UUID = str(uuid.uuid4())
# 2. 현재 시간을 "YYYYMMDD-HHMMSS" 형식의 문자열로 변환합니다.
REQUEST_TIME = datetime.now().strftime("%Y%m%d-%H%M%S")

# 3. 'publish:uuid/timestamp' 형식에 맞게 SRT URL을 생성합니다.
SRT_URL = f'srt://{SERVER_IP}:{SERVER_PORT}?streamid=publish:{CLIENT_UUID}/{REQUEST_TIME}'


# --- FFmpeg 명령어 생성 ---
# 사용자가 요청한 새로운 명령어 형식에 맞게 재구성합니다.
# macOS (avfoundation) 기준입니다.
command = [
    'ffmpeg',
    '-f', 'avfoundation',
    '-framerate', '30',
    '-pix_fmt', 'nv12',  # 입력 픽셀 포맷
    '-i', '0',           # 입력 장치 (0번 비디오)
    '-c:v', 'libx264',
    '-preset', 'veryfast',
    '-tune', 'zerolatency',
    '-f', 'mpegts',      # SRT 전송을 위한 컨테이너 포맷
    SRT_URL
]

print("-" * 40)
print(f"클라이언트 UUID: {CLIENT_UUID}")
print(f"요청 시간: {REQUEST_TIME}")
print(f"MediaMTX 서버로 영상 전송을 시작합니다.")
print(f"  ==> {SRT_URL}")
print("실행될 FFmpeg 명령어:")
print(' '.join(command))
print("-" * 40)

try:
    # FFmpeg 프로세스를 실행합니다.
    process = subprocess.Popen(command)
    process.wait()
except FileNotFoundError:
    print("오류: ffmpeg이 설치되어 있지 않거나 PATH에 등록되지 않았습니다.")
    sys.exit()
except KeyboardInterrupt:
    print("\n사용자에 의해 전송이 중단되었습니다.")
    process.terminate()
finally:
    # 프로세스가 여전히 실행 중이면 강제 종료합니다.
    if 'process' in locals() and process.poll() is None:
        process.kill()
    print("프로그램을 종료합니다.")