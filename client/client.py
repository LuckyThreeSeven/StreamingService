import subprocess
import uuid
import sys
from datetime import datetime
import platform
import socket
import time
import os

# --- 설정 ---
SERVER_IP = '127.0.0.1'
SERVER_PORT = 8890
SERVER_CHECK_PORT = 9997
CLIENT_UUID = str(uuid.uuid4())
LOCAL_REC_PATH = f'./{CLIENT_UUID}'
# 오프라인 녹화 시간
OFFLINE_REC_DURATION = 30 

def check_server_connection(ip, port):
    """서버의 TCP 포트가 열려 있는지 확인합니다."""
    print(f"📡 {ip}:{port} 서버 연결 상태 확인 중...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(2)
        if sock.connect_ex((ip, port)) == 0:
            print(f"✅ 연결 성공.")
            return True
        else:
            print(f"❌ 연결 실패.")
            return False

def get_base_ffmpeg_command(os_type):
    """운영체제에 따라 기본 FFmpeg 입력 명령을 반환합니다."""
    if os_type == "Darwin":
        return [
            'ffmpeg', '-f', 'avfoundation', '-framerate', '30', '-pix_fmt', 'nv12',
            '-i', '0:0'
        ]
    elif os_type == "Linux":
        return [
            'ffmpeg', '-f', 'v4l2', '-framerate', '30', '-video_size', '1280x720',
            '-i', '/dev/video0',
            '-f', 'alsa', '-i', 'hw:0'
        ]
    return None

def stream_to_server():
    """온라인 모드: 서버로 스트리밍을 시작합니다. 연결이 끊기면 함수가 종료됩니다."""
    print("\n🚀 [온라인 모드] 서버로 스트리밍을 시작합니다.")
    REQUEST_TIME = datetime.now().strftime("%Y%m%d-%H%M%S")
    SRT_URL = f'srt://{SERVER_IP}:{SERVER_PORT}?streamid=publish:{CLIENT_UUID}/{REQUEST_TIME}'
    
    command = get_base_ffmpeg_command(platform.system())
    if not command: return

    command.extend([
        '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'zerolatency',
        '-c:a', 'aac', '-b:a', '128k',
        '-f', 'mpegts', SRT_URL
    ])
    
    print("실행될 명령어: ", ' '.join(command))
    subprocess.run(command, stderr=sys.stderr)

def record_clip_locally(duration):
    """오프라인 모드: 클립을 로컬에 저장합니다."""
    print(f"\n [오프라인 모드] {duration}초 로컬 녹화를 시작합니다.")
    os.makedirs(LOCAL_REC_PATH, exist_ok=True)
    
    file_name = datetime.now().strftime("%Y%m%d-%H%M%S") + ".mp4"
    output_path = os.path.join(LOCAL_REC_PATH, file_name)

    command = get_base_ffmpeg_command(platform.system())
    if not command: return

    command.extend([
        '-t', str(duration),
        '-c:v', 'libx264', '-preset', 'veryfast',
        '-c:a', 'aac', '-b:a', '128k',
        output_path
    ])

    print(f"녹화 파일 경로: {output_path}")
    print("실행될 명령어: ", ' '.join(command))
    subprocess.run(command, stderr=sys.stderr)
    print(f" {duration}초 녹화 완료.")

# --- 메인 실행 루프 ---
if __name__ == "__main__":
    try:
        while True:
            if check_server_connection(SERVER_IP, SERVER_CHECK_PORT):
                stream_to_server()
                print("\n 스트리밍이 중단되었습니다. 연결 상태를 다시 확인합니다...")
                time.sleep(2)
            
            else:
                # 함수 호출 시 설정된 OFFLINE_REC_DURATION 값을 전달
                record_clip_locally(OFFLINE_REC_DURATION)

    except KeyboardInterrupt:
        print("\n사용자에 의해 프로그램이 중단되었습니다.")
    except Exception as e:
        print(f"예상치 못한 오류 발생: {e}")
    finally:
        print("프로그램을 종료합니다.")