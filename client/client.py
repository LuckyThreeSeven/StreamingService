import subprocess
import sys
from datetime import datetime, timezone
import platform
import socket
import time
import os
import glob
import threading
import config

# --- 설정 ---
CLIENT_UUID = config.CLIENT_UUID

MEDIAMTX_SERVER_URL = config.MEDIAMTX_SERVER_URL
MEDIAMTX_SERVER_CHECK_URL = config.MEDIAMTX_SERVER_CHECK_URL

LOCAL_REC_PATH = config.LOCAL_REC_PATH

# 오프라인
OFFLINE_REC_DURATION = config.OFFLINE_REC_DURATION
# The following are no longer used for upload but are kept to avoid breaking config imports.
OFFLINE_UPLOAD_SERVER_BASE_URL = config.OFFLINE_UPLOAD_SERVER_BASE_URL
OFFLINE_UPLOAD_SERVER_URL = f'{OFFLINE_UPLOAD_SERVER_BASE_URL}{CLIENT_UUID}'


def check_server_connection(url):
    """서버의 TCP 포트가 열려 있는지 확인합니다."""
    print(f"\n mediaMTX 서버 연결 상태 확인 중...")
    # print(f"SERVER_URL: {MEDIAMTX_SERVER_URL}")
    # print(f"SERVER_CHECK_URL: {MEDIAMTX_SERVER_CHECK_URL}")
    try:
        # 1. URL을 ':' 기준으로 IP와 포트로 분리합니다.
        ip, port_str = url.split(':')
        port = int(port_str)
        # print(f"파싱 성공! {ip}, {port}")

        # 2. 소켓 연결 시도
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)  # 응답 대기 시간
            if sock.connect_ex((ip, port)) == 0:
                print("연결 성공.")
                return True
            else:
                print("연결 실패.")
                return False
    except ValueError:
        print(f"오류: '{url}'은(는) 유효한 'IP:포트' 형식이 아닙니다.")
        return False
    except socket.gaierror:
        print("연결 실패: 호스트 이름을 확인할 수 없습니다.")
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
    print("\n [메인 스레드] 실시간 스트리밍을 시작합니다.")
    REQUEST_TIME = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    SRT_URL = f'srt://{MEDIAMTX_SERVER_URL}?streamid=publish:{CLIENT_UUID}/{REQUEST_TIME}'

    command = get_base_ffmpeg_command(platform.system())
    if not command: return

    command[1:1] = ['-v', 'quiet', '-stats']  # 로그 간단하게

    command.extend([
        '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'zerolatency',
        '-c:a', 'aac', '-b:a', '128k',
        '-f', 'mpegts', SRT_URL
    ])

    print(" [메인 스레드] 실행될 명령어: ", ' '.join(command))
    subprocess.run(command, stderr=sys.stderr)


def record_clip_locally(duration):
    """오프라인 모드: 클립을 로컬에 임시 파일로 저장하고, 완료되면 '-ready' 태그를 붙입니다."""
    print(f"\n [오프라인 모드] {duration}초 로컬 녹화를 시작합니다.")
    os.makedirs(LOCAL_REC_PATH, exist_ok=True)

    base_name = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    temp_output_path = os.path.join(LOCAL_REC_PATH, base_name + ".mp4")
    ready_output_path = os.path.join(LOCAL_REC_PATH, base_name + "-ready.mp4")

    command = get_base_ffmpeg_command(platform.system())
    if not command: return

    command.extend([
        '-t', str(duration),
        '-c:v', 'libx264', '-preset', 'veryfast',
        '-c:a', 'aac', '-b:a', '128k',
        temp_output_path
    ])

    print(f"임시 녹화 파일 경로: {temp_output_path}")
    result = subprocess.run(command, stderr=sys.stderr)

    if result.returncode == 0:
        print(f" {duration}초 녹화 완료. 파일을 '{os.path.basename(ready_output_path)}'(으)로 변경합니다.")
        os.rename(temp_output_path, ready_output_path)
    else:
        print(f" 녹화 중 오류 발생. 불완전한 파일 '{os.path.basename(temp_output_path)}'이(가) 남았을 수 있습니다.")


def get_base_ffmpeg_command_for_offline(input_file):
    """특정 영상을 무한 반복 스트리밍하기 위한 FFmpeg 입력 명령을 반환합니다."""

    return [
        'ffmpeg',
        '-stream_loop', '0',
        '-i', input_file
    ]


def upload_local_files_via_srt():
    """새로운 오프라인 업로드 파일 처리 함수"""

    """(백그라운드 작업) 로컬에 저장된 '-ready.mp4' 파일들을 SRT로 스트리밍하여 업로드합니다."""
    print("\n [업로드 스레드] 오프라인 영상 파일 SRT 스트리밍 업로드를 시작합니다.")
    # '-ready.mp4' 패턴을 사용하여 완료된 파일만 대상으로 지정
    files_to_upload = sorted(glob.glob(os.path.join(LOCAL_REC_PATH, "*")))

    if not files_to_upload:
        print(" [업로드 스레드] 업로드할 파일이 없습니다.")
        return

    print(f" [업로드 스레드] 총 {len(files_to_upload)}개의 파일을 업로드합니다.")

    for file_path in files_to_upload:
        # 업로드 시작 전 서버 연결 상태 재확인
        if not check_server_connection(MEDIAMTX_SERVER_CHECK_URL):
            print(" [업로드 스레드] 업로드 중 서버 연결 끊김. 업로드를 중단합니다.")
            return

        file_name = os.path.basename(file_path)
        new_file_name = file_name.replace("-ready.mp4", ".mp4")
        base_name = new_file_name.replace('-ready.mp4', '').replace('.mp4', '')
        print(f"\n [업로드 스레드] '{file_name}' 파일 스트리밍 시도...")

        SRT_URL = f'srt://{MEDIAMTX_SERVER_URL}?streamid=publish:{CLIENT_UUID}/offline{base_name}'

        # 3. FFmpeg 기본 명령 (무한 루프)
        command = get_base_ffmpeg_command_for_offline(file_path)

        # 4. 출력 및 인코딩 설정 추가
        command.extend([
            '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'zerolatency',  # 비디오 인코딩
            '-c:a', 'aac', '-b:a', '128k',  # 오디오 인코딩
            '-f', 'mpegts',  # 출력 형식
            '-v', 'quiet', '-stats',  # 로그 간소화
            SRT_URL
        ])

        print(" [업로드 스레드] 실행될 명령어: ", ' '.join(command))

        result = subprocess.run(command, stderr=sys.stderr)
        if result.returncode == 0:
            print(f" [업로드 스레드] 스트리밍 성공. 로컬 파일 '{file_name}'을(를) 삭제합니다.")
            try:
                os.remove(file_path)
            except OSError as e:
                print(f" [업로드 스레드] 파일 삭제 실패: {e}")
        else:
            print(f" [업로드 스레드] 스트리밍 실패: FFmpeg 오류 발생. 다음 파일로 넘어갑니다.")
            continue

    print(" [업로드 스레드] 모든 오프라인 파일 업로드 작업 완료.")


def start_concurrent_streaming_and_uploading():
    """
    로컬 파일 업로드와 실시간 스트리밍을 동시에 진행합니다.
    - 업로드: 백그라운드 스레드에서 실행
    - 실시간 스트리밍: 메인 스레드에서 실행
    """
    print("\n[온라인 모드] 로컬 파일 업로드와 실시간 스트리밍을 동시에 시작합니다.")

    # 1. 로컬 파일 업로드를 위한 백그라운드 스레드 생성 및 시작
    uploader_thread = threading.Thread(target=upload_local_files_via_srt(), daemon=True)
    uploader_thread.start()

    # 2. 메인 스레드에서 실시간 스트리밍 시작
    stream_to_server()


# --- 메인 실행 루프 ---
if __name__ == "__main__":
    print(f"오프라인 업로드 서버 URL (사용 안 함): {OFFLINE_UPLOAD_SERVER_URL}")
    try:
        while True:
            if check_server_connection(MEDIAMTX_SERVER_CHECK_URL):
                # [온라인] 업로드와 스트리밍 동시 진행
                start_concurrent_streaming_and_uploading()

                print("\n 스트리밍이 중단되었습니다. 연결 상태를 다시 확인합니다...")
                time.sleep(1)

            else:
                # [오프라인] 연결 실패 시 로컬에 영상 녹화
                record_clip_locally(OFFLINE_REC_DURATION)

    except KeyboardInterrupt:
        print("\n사용자에 의해 프로그램이 중단되었습니다.")
    except Exception as e:
        print(f"예상치 못한 오류 발생: {e}")
    finally:
        print("프로그램을 종료합니다.")