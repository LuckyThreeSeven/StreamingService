import subprocess
import uuid
import sys
from datetime import datetime
import platform
import socket
import time

# --- 설정 ---
SERVER_IP = '127.0.0.1'
SERVER_PORT = 8890
SERVER_CHECK_PORT = 9997
CLIENT_UUID = str(uuid.uuid4())

def check_server_connection(ip, port):
    """서버의 TCP 포트가 열려 있는지 확인합니다."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(2)
        if sock.connect_ex((ip, port)) == 0:
            print(f"✅ 서버 연결 확인: {ip}:{port} 포트가 열려 있습니다.")
            return True
        else:
            print(f"❌ 서버 연결 실패: {ip}:{port} 포트가 닫혀 있거나 응답이 없습니다.")
            return False

def run_ffmpeg_stream():
    """FFmpeg 스트리밍 프로세스를 실행하고 끝날 때까지 기다립니다."""
    REQUEST_TIME = datetime.now().strftime("%Y%m%d-%H%M%S")
    SRT_URL = f'srt://{SERVER_IP}:{SERVER_PORT}?streamid=publish:{CLIENT_UUID}/{REQUEST_TIME}'
    
    command = []
    current_os = platform.system()
    if current_os == "Darwin":
        command = [
            'ffmpeg', '-f', 'avfoundation', '-framerate', '30', '-pix_fmt', 'nv12',
            '-i', '0:0', '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'zerolatency',
            '-c:a', 'aac', '-b:a', '128k', '-f', 'mpegts', SRT_URL
        ]
    elif current_os == "Linux":
        command = [
            'ffmpeg', '-f', 'v4l2', '-framerate', '30', '-video_size', '1280x720',
            '-i', '/dev/video0', '-f', 'alsa', '-i', 'hw:0', '-c:v', 'libx264',
            '-preset', 'veryfast', '-tune', 'zerolatency', '-c:a', 'aac',
            '-b:a', '128k', '-f', 'mpegts', SRT_URL
        ]
    else:
        print(f"오류: 지원되지 않는 운영체제({current_os})입니다.")
        return

    print("-" * 40)
    print(f"클라이언트 UUID: {CLIENT_UUID}")
    print(f"MediaMTX 서버로 영상 전송을 시작합니다: {SRT_URL}")
    print("실행될 FFmpeg 명령어: ", ' '.join(command))
    print("-" * 40)
    
    # ⬇️이 함수는 FFmpeg이 끝날 때까지 자동으로 기다립니다.
    subprocess.run(command, stderr=sys.stderr, text=True)

# --- 메인 실행 루프 ---
if __name__ == "__main__":
    try:
        while True:
            # 1. 서버 헬스 체크 포트 확인
            if check_server_connection(SERVER_IP, SERVER_CHECK_PORT):
                print("🚀 서버 연결이 확인되었습니다. FFmpeg 스트리밍을 시작합니다.")
                
                # ⬇️ 이제 함수 호출 한 줄로 '실행과 기다림'이 모두 끝납니다.
                run_ffmpeg_stream()
                
                print("📡 FFmpeg 프로세스가 종료되었습니다. 잠시 후 재연결을 시도합니다.")
            
            # 2. 서버 연결 실패 또는 FFmpeg 종료 시 10초 대기
            print("10초 후 재연결을 시도합니다...")
            time.sleep(10)

    except KeyboardInterrupt:
        print("\n사용자에 의해 프로그램이 중단되었습니다.")
        # run을 사용하면 별도의 프로세스 종료 코드가 필요 없습니다.
        # 함수가 끝나면 프로세스도 끝나기 때문입니다.
    except Exception as e:
        print(f"예상치 못한 오류 발생: {e}")
    finally:
        print("프로그램을 종료합니다.")