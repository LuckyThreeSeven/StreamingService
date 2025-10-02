# StreamingService

클라이언트(블랙박스) + 영상 업로드 서버(fast-api)

## 실행 방법
#### 1. 환경변수 파일 추가
- `./db_upload_server` 에 `.env` 파일 추가

#### 2. docker로 서버 실행
- `docker compose up --build -d`

#### 3. 클라이언트(카메라) 실행
client 폴더에서 파이썬 스크립트 실행 시 카메라 녹화 및 전송 시작
- `python client.py`