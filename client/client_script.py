import subprocess
import sys
from datetime import datetime, timezone
import socket
import time
import threading
from pathlib import Path
import config

CLIENT_UUID = config.CLIENT_UUID
MEDIAMTX_SERVER_URL = config.MEDIAMTX_SERVER_URL
MEDIAMTX_SERVER_CHECK_URL = config.MEDIAMTX_SERVER_CHECK_URL

# 오프라인 업로드 URL (사용되지 않지만 기존 구조 유지)
OFFLINE_UPLOAD_SERVER_BASE_URL = config.OFFLINE_UPLOAD_SERVER_BASE_URL
OFFLINE_UPLOAD_SERVER_URL = f'{OFFLINE_UPLOAD_SERVER_BASE_URL}{CLIENT_UUID}'

LOCAL_VIDEO_FILE = "video.mp4"

# --------------------------------------------------------------------------------

def check_server_connection(url):
    """서버의 TCP 포트가 열려 있는지 확인합니다."""
    print(f"\n[Connection Check] mediaMTX 서버 연결 상태 확인 중...")
    try:
        # 1. URL을 ':' 기준으로 IP와 포트로 분리합니다.
        ip, port_str = url.split(':')
        port = int(port_str)

    except ValueError:
        print(f"오류: '{url}'은(는) 유효한 'IP:포트' 형식이 아닙니다.")
        return False

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(2)  # 응답 대기 시간

        if sock.connect_ex((ip, port)) == 0:
            print("연결 성공.")
            return True
        else:
            print("연결 실패.")
            return False


def get_base_ffmpeg_command_for_loop(input_file):
    """특정 영상을 무한 반복 스트리밍하기 위한 FFmpeg 입력 명령을 반환합니다."""

    # -re : 리얼타임 속도로 읽기 (스트리밍 시 중요)
    # -stream_loop -1 : 파일을 무한 반복 (-1)

    return [
        'ffmpeg',
        '-stream_loop', '-1',
        '-i', input_file
    ]


def stream_to_server_loop():
    """온라인 모드: 로컬 영상 파일을 서버로 반복 스트리밍을 시작합니다."""
    print("\n [온라인 모드] 로컬 영상을 서버로 반복 스트리밍을 시작합니다.")

    # 1. 로컬 파일 존재 여부 확인
    if not Path(LOCAL_VIDEO_FILE).exists():
        print(f"오류: 로컬 영상 파일 '{LOCAL_VIDEO_FILE}'을(를) 찾을 수 없습니다. 파일을 준비해주세요.")
        return None

    # 2. 스트림 ID 설정
    # 서버에서 스트림을 식별할 수 있는 고유한 경로와 시간 정보를 사용합니다.
    REQUEST_TIME = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    SRT_URL = f'srt://{MEDIAMTX_SERVER_URL}?streamid=publish:{CLIENT_UUID}/{REQUEST_TIME}'

    # 3. FFmpeg 기본 명령 (무한 루프)
    command = get_base_ffmpeg_command_for_loop(LOCAL_VIDEO_FILE)

    # 4. 출력 및 인코딩 설정 추가
    # -re를 입력 파일 앞에 넣으면 무한 루프 (-stream_loop -1)가 제대로 작동하지 않으므로,
    # 파일을 먼저 읽도록 -i 뒤에 배치합니다.
    command.extend([
        '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'zerolatency',  # 비디오 인코딩
        '-c:a', 'aac', '-b:a', '128k',  # 오디오 인코딩
        '-f', 'mpegts',  # 출력 형식 (SRT와 함께 자주 사용됨)
        '-v', 'quiet', '-stats',  # 로그 간소화
        SRT_URL
    ])

    print("실행될 명령어 (ffmpeg): ", ' '.join(command))

    try:
        # subprocess.Popen을 사용하여 프로세스 객체를 반환합니다.
        process = subprocess.Popen(command, stderr=sys.stderr)
        return process
    except FileNotFoundError:
        print("오류: 'ffmpeg' 명령어를 찾을 수 없습니다. FFmpeg이 설치되어 있고 환경 변수에 등록되어 있는지 확인해주세요.")
        return None
    except Exception as e:
        print(f"스트리밍 시작 중 예상치 못한 오류 발생: {e}")
        return None


def upload_local_files_dummy():
    """
    (더미 함수) 오프라인 업로드 로직은 제거하고, 서버 연결 확인 시에만 실행됩니다.
    실제 파일 업로드 기능이 필요하면 이전 코드를 복구하세요.
    """
    # 이 로직은 온라인 모드가 시작될 때만 백그라운드에서 실행되도록 유지합니다.
    # 하지만 파일 업로드 기능은 제거하고, 연결 확인만 하는 더미 로직으로 변경합니다.
    print(" [업로드 모드] 오프라인 파일 업로드 기능은 현재 비활성화되어 있습니다.")


def start_online_and_upload_concurrently():
    """업로드는 백그라운드 스레드에서, 라이브 스트리밍은 메인 스레드에서 동시에 실행합니다."""

    # 1. 업로드 스레드 시작 (기존 로직 유지)
    # 실제로는 더미 함수이므로 큰 부하는 없습니다.
    uploader_thread = threading.Thread(target=upload_local_files_dummy, daemon=True)
    uploader_thread.start()

    # 2. 메인 스레드에서 반복 스트리밍 시작
    live_stream_process = stream_to_server_loop()

    # 3. 스트리밍 프로세스가 끝날 때까지 대기 (Ctrl+C를 누르거나 연결이 끊길 때까지)
    if live_stream_process:
        live_stream_process.wait()
        print("스트리밍 프로세스가 종료되었습니다.")


# --- 메인 실행 루프 ---
if __name__ == "__main__":
    try:
        # 서버 주소가 올바른지 확인합니다.
        print(f"MediaMTX Server URL: {MEDIAMTX_SERVER_URL}")

        while True:
            # 1. 서버 연결 상태 확인
            if check_server_connection(MEDIAMTX_SERVER_CHECK_URL):
                # 2. 연결 성공 시: 반복 스트리밍 시작
                start_online_and_upload_concurrently()

                # FFmpeg이 종료되면 (연결 끊김) 루프를 다시 돌려 연결을 확인합니다.
                print("\n스트리밍이 중단되었습니다. 연결 상태를 다시 확인합니다...")
                time.sleep(1)

            else:
                # 3. 연결 실패 시: 대기 후 재확인 (오프라인 녹화 로직 제거)
                print("\n [오프라인 대기] 서버 연결을 찾을 수 없습니다. 5초 후 재시도합니다...")
                time.sleep(5)

    except KeyboardInterrupt:
        print("\n사용자에 의해 프로그램이 중단되었습니다.")
    except Exception as e:
        print(f"예상치 못한 오류 발생: {e}")
    finally:
        print("프로그램을 종료합니다.")


        # REQUEST_TIME = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        SRT_URL = f'srt://{MEDIAMTX_SERVER_URL}?streamid=publish:{CLIENT_UUID}/offline'



        command = [
            'ffmpeg', '-re',
            '-i', file_path,
            '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'zerolatency',
            '-c:a', 'aac', '-b:a', '128k',
            '-f', 'mpegts', '-v', 'quiet', '-stats',
            SRT_URL
        ]

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