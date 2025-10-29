import subprocess
import sys
from datetime import datetime, timezone
import platform
import socket
import time
import os
import glob
import threading
import requests
import config

# --- 설정 ---
CLIENT_UUID = config.CLIENT_UUID

MEDIAMTX_SERVER_URL = config.MEDIAMTX_SERVER_URL
MEDIAMTX_SERVER_CHECK_URL = config.MEDIAMTX_SERVER_CHECK_URL

LOCAL_REC_PATH = config.LOCAL_REC_PATH

# 오프라인
OFFLINE_REC_DURATION = config.OFFLINE_REC_DURATION
OFFLINE_UPLOAD_SERVER_BASE_URL = config.OFFLINE_UPLOAD_SERVER_BASE_URL
OFFLINE_UPLOAD_SERVER_URL = f'{OFFLINE_UPLOAD_SERVER_BASE_URL}{CLIENT_UUID}'

def check_server_connection(url):
    """서버의 TCP 포트가 열려 있는지 확인합니다."""
    print(f" mediaMTX 서버 연결 상태 확인 중...")
    print(f"SERVER_URL: {MEDIAMTX_SERVER_URL}")
    print(f"SERVER_CHECK_URL: {MEDIAMTX_SERVER_CHECK_URL}")
    try:
        # 1. URL을 ':' 기준으로 IP와 포트로 분리합니다.
        ip, port_str = url.split(':')
        
        # 2. 포트 번호를 문자열에서 정수(int)로 변환합니다.
        port = int(port_str)
        print(f"파싱 성공! {ip}, {port}")
        
    except ValueError:
        print(f"오류: '{url}'은(는) 유효한 'IP:포트' 형식이 아닙니다.")
        return False

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(2) # 응답 대기 시간
        
        # 3. 분리된 ip와 port를 튜플 형태로 전달합니다.
        if sock.connect_ex((ip, port)) == 0:
            print("연결 성공.")
            return True
        else:
            print("연결 실패.")
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
    print("\n [온라인 모드] 서버로 스트리밍을 시작합니다.")
    REQUEST_TIME = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    SRT_URL = f'srt://{MEDIAMTX_SERVER_URL}?streamid=publish:{CLIENT_UUID}/{REQUEST_TIME}'
    
    command = get_base_ffmpeg_command(platform.system())
    if not command: return

    command[1:1] = ['-v', 'quiet', '-stats'] # 로그 간단하게

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
    
    file_name = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + ".mp4"
    output_path = os.path.join(LOCAL_REC_PATH, file_name)

    command = get_base_ffmpeg_command(platform.system())
    if not command: return

    # command[1:1] = ['-v', 'quiet', '-stats'] # 로그 간단하게

    command.extend([
        '-t', str(duration),
        '-c:v', 'libx264', '-preset', 'veryfast',
        '-c:a', 'aac', '-b:a', '128k',
        output_path
    ])

    print(f"녹화 파일 경로: {output_path}")
    # print("실행될 명령어: ", ' '.join(command))
    subprocess.run(command, stderr=sys.stderr)
    print(f" {duration}초 녹화 완료.")

def upload_local_files():
    """(백그라운드 스레드) 로컬 파일을 HTTP POST로 업로드하고 삭제합니다."""
    print("\n [업로드 모드] 백그라운드에서 오프라인 영상 파일 업로드를 시작합니다.")
    files_to_upload = sorted(glob.glob(os.path.join(LOCAL_REC_PATH, "*.mp4")))
    
    if not files_to_upload:
        print(" 업로드할 파일이 없습니다.")
        return

    print(f"총 {len(files_to_upload)}개의 파일을 업로드합니다.")
    
    for file_path in files_to_upload:
        file_name = os.path.basename(file_path)
        print(f"\n '{file_name}' 파일 업로드 시도...")
        
        try:
            # 파일을 바이너리 읽기 모드('rb')로 엽니다.
            with open(file_path, 'rb') as f:
                # 'multipart/form-data' 형식으로 보낼 파일 데이터 준비
                files = {'video_file': (file_name, f, 'video/mp4')}
                # 파일과 함께 보낼 추가 데이터 (예: UUID)
                payload = {'uuid': CLIENT_UUID}

                print(f"오프라인 서버 URL: {OFFLINE_UPLOAD_SERVER_URL}")

                # HTTP POST 요청 전송
                response = requests.post(OFFLINE_UPLOAD_SERVER_URL, files=files, data=payload, timeout=60)

                # 서버로부터 받은 응답 확인 (200은 성공을 의미)
                if response.status_code == 200:
                    print(f" 업로드 성공. 로컬 파일 '{file_name}'을(를) 삭제합니다.")
                    try:
                        os.remove(file_path)
                    except OSError as e:
                        print(f" 파일 삭제 실패: {e}")
                else:
                    print(f" 업로드 실패: 서버가 오류를 반환했습니다 (상태 코드: {response.status_code}).")
                    print(f"응답 내용: {response.text}")
                    # 서버가 오류를 반환하면 일단 중단하고 다음 사이클에서 재시도
                    return
        except requests.RequestException as e:
            print(f" 업로드 중 네트워크 오류 발생: {e}. 다음 사이클에서 재시도합니다.")
            return # 네트워크 오류 시 중단
        except FileNotFoundError:
            print(f" 파일을 찾을 수 없어 업로드를 건너뜁니다: {file_name}")
            continue

    print(" 모든 오프라인 파일 업로드 완료.")

def start_online_and_upload_concurrently():
    """업로드는 백그라운드 데몬 스레드에서, 라이브 스트리밍은 메인 스레드에서 동시에 실행합니다."""
    # 업로드 작업을 수행할 백그라운드 데몬 스레드 생성
    uploader_thread = threading.Thread(target=upload_local_files, daemon= True)
    
    # 백그라운드에서 업로드 시작
    uploader_thread.start()
    
    # 메인 스레드에서는 라이브 스트리밍 시작
    live_stream_process = stream_to_server()
    
    # 라이브 스트리밍이 끝날 때까지 기다림
    if live_stream_process:
        live_stream_process.wait()

# --- 메인 실행 루프 ---
if __name__ == "__main__":
    print(f"오프라인 서버 URL: {OFFLINE_UPLOAD_SERVER_URL}")
    try:
        while True:
            if check_server_connection(MEDIAMTX_SERVER_CHECK_URL):
                start_online_and_upload_concurrently()
                print("\n 스트리밍이 중단되었습니다. 연결 상태를 다시 확인합니다...")
                time.sleep(1)
            
            else:
                # 함수 호출 시 설정된 OFFLINE_REC_DURATION 값을 전달
                record_clip_locally(OFFLINE_REC_DURATION)

    except KeyboardInterrupt:
        print("\n사용자에 의해 프로그램이 중단되었습니다.")
    except Exception as e:
        print(f"예상치 못한 오류 발생: {e}")
    finally:
        print("프로그램을 종료합니다.")