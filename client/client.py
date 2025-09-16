import subprocess
import uuid
import sys
from datetime import datetime
import platform  # ⬅️ 운영체제 확인을 위해 추가

# --- 설정 ---
SERVER_IP = '127.0.0.1'
SERVER_PORT = 8890  # MediaMTX에 설정한 SRT 포트

# --- 동적 streamid 생성 ---
CLIENT_UUID = str(uuid.uuid4())
REQUEST_TIME = datetime.now().strftime("%Y%m%d-%H%M%S")
SRT_URL = f'srt://{SERVER_IP}:{SERVER_PORT}?streamid=publish:{CLIENT_UUID}/{REQUEST_TIME}'

# --- 운영체제에 따라 FFmpeg 명령어 분기 ---
command = []
current_os = platform.system()

if current_os == "Darwin":  # 🍎 "Darwin"은 macOS의 커널 이름입니다.
    print(">>> macOS 환경을 감지했습니다.")
    command = [
        'ffmpeg',
        '-f', 'avfoundation',
        '-framerate', '30',
        '-pix_fmt', 'nv12',
        '-i', '0:0',           # macOS: 비디오장치 0번, 오디오장치 0번
        '-c:v', 'libx264',
        '-preset', 'veryfast',
        '-tune', 'zerolatency',
        '-c:a', 'aac',
        '-b:a', '128k',
        '-f', 'mpegts',
        SRT_URL
    ]
elif current_os == "Linux":  # 🐧 "Linux"는 Ubuntu를 포함한 리눅스 계열입니다.
    print(">>> Linux 환경(Ubuntu)을 감지했습니다.")
    command = [
        'ffmpeg',
        # 비디오 입력 (웹캠)
        '-f', 'v4l2',
        '-framerate', '30',
        '-video_size', '1280x720',
        '-i', '/dev/video0',      # Linux: 첫 번째 웹캠
        # 오디오 입력 (마이크)
        '-f', 'alsa',
        '-i', 'hw:0',             # Linux: 첫 번째 사운드카드
        # 출력 및 인코딩 설정
        '-c:v', 'libx264',
        '-preset', 'veryfast',
        '-tune', 'zerolatency',
        '-c:a', 'aac',
        '-b:a', '128k',
        '-f', 'mpegts',
        SRT_URL
    ]
else:
    print(f"오류: 지원되지 않는 운영체제({current_os})입니다. macOS 또는 Linux에서 실행해주세요.")
    sys.exit()


print("-" * 40)
print(f"클라이언트 UUID: {CLIENT_UUID}")
print(f"요청 시간: {REQUEST_TIME}")
print(f"MediaMTX 서버로 영상 전송을 시작합니다.")
print(f"  ==> {SRT_URL}")
print("실행될 FFmpeg 명령어:")
print(' '.join(command))
print("-" * 40)

try:
    process = subprocess.Popen(command)
    process.wait()
except FileNotFoundError:
    print("오류: ffmpeg이 설치되어 있지 않거나 PATH에 등록되지 않았습니다.")
    sys.exit()
except KeyboardInterrupt:
    print("\n사용자에 의해 전송이 중단되었습니다.")
    process.terminate()
finally:
    if 'process' in locals() and process.poll() is None:
        process.kill()
    print("프로그램을 종료합니다.")