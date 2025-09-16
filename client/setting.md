## 클라이언트 실행전 ffmpeg설치 필요

#### 맥 (brew 사용):

Homebrew 설치가 완료되면 다음 명령어로 FFmpeg을 설치합니다.

``` bash
brew install ffmpeg
```

&nbsp;

#### Ubuntu / Debian (APT 사용)

대부분의 데스크탑 리눅스 사용자가 이용하는 Ubuntu나 Debian 계열에서는 `apt` 명령어를 사용합니다.

```bash
sudo apt update
sudo apt install ffmpeg
```

&nbsp;

### 설치 확인

설치가 완료된 후, 터미널에 다음 명령어를 입력하여 버전 정보가 나오면 정상적으로 설치된 것입니다.

```bash
ffmpeg -version
```

