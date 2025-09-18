# upload_server/app/main.py

from fastapi import FastAPI, File, UploadFile, HTTPException
from pathlib import Path
import shutil

app = FastAPI(title="Video Upload Server")

# 컨테이너 내부의 마운트된 볼륨 경로
# 이 경로는 호스트의 server/recordings 와 연결됩니다.
BASE_SAVE_DIR = Path("/data")

@app.post("/upload/video/{client_uuid}")
def upload_video(client_uuid: str, video_file: UploadFile = File(...)):
    try:
        # 1. 저장할 경로를 /data 기준으로 정의합니다.
        save_dir = BASE_SAVE_DIR / client_uuid / "offline"

        # 2. 폴더가 존재하지 않으면 생성합니다.
        save_dir.mkdir(parents=True, exist_ok=True)

        # 3. 파일을 저장할 최종 경로를 설정합니다.
        file_path = save_dir / video_file.filename

        # 4. 파일을 디스크에 씁니다.
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(video_file.file, buffer)

        return {
            "message": f"Video '{video_file.filename}' uploaded successfully for client '{client_uuid}'.",
            "saved_path": str(file_path)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
    finally:
        video_file.file.close()