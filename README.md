# LectureScribe

LectureScribe는 Faster-Whisper와 OpenAI API를 사용하는 로컬 강의 전사 및 요약 GUI 애플리케이션입니다.

PyQt6 기반 데스크톱 UI에서 오디오 파일을 선택하면 로컬 PC에서 음성을 텍스트로 전사하고, 전사된 Markdown 파일을 OpenAI API로 요약해 Obsidian에서 바로 사용할 수 있는 노트를 생성합니다.

## 주요 기능

- 로컬 음성 전사: `faster-whisper`와 `ctranslate2` 기반 전사
- GPU 가속 지원: NVIDIA CUDA 환경에서 빠른 전사 처리
- Markdown 출력: 타임스탬프가 포함된 강의 전사 파일 생성
- OpenAI 요약: 전사 Markdown을 강의 노트 형식으로 자동 요약
- 긴 문서 분할 처리: 긴 전사문을 chunk 단위로 나누어 요약
- 중복 파일 보호: 같은 이름의 결과물이 있으면 `_1`, `_2` 형식으로 자동 저장
- Windows 배포 지원: PyInstaller와 Inno Setup 기반 설치 파일 생성

## 프로젝트 구조

```text
.
├── .gitignore
├── .python-version
├── LectureScribe.spec
├── README.md
├── cuda_test.py
├── main.py
├── pyproject.toml
├── run_ui.sh
├── setup.iss
└── uv.lock
```

다음 항목은 로컬 실행, 빌드, 입력/출력 과정에서 생성되며 `.gitignore`로 Git 추적에서 제외됩니다.

```text
.
├── .venv/
├── __pycache__/
├── bin/
│   ├── ffmpeg.exe
│   └── ffprobe.exe
├── build/
├── dist/
│   ├── LectureScribe/
│   └── LectureScribe_Setup.exe
├── input/
├── output/
├── wheels/
├── *.egg-info
├── *.pyc
├── *.pyo
└── *.zip
```

핵심 파일 역할은 다음과 같습니다.

```text
├── main.py
│   └── PyQt6 GUI, 전사 작업자, 요약 작업자 구현
├── pyproject.toml
│   └── Python 패키지 메타데이터 및 의존성 정의
├── run_ui.sh
│   └── WSL/Linux용 실행 보조 스크립트
├── setup.iss
│   └── Inno Setup 설치 파일 빌드 스크립트
└── LectureScribe.spec
    └── PyInstaller 배포 폴더 빌드 스펙
```

## 요구사항

### 기본 요구사항

- Python 3.11 이상
- `uv`
- Windows 권장
- `ffmpeg.exe`, `ffprobe.exe`

### Python 패키지

주요 의존성은 `pyproject.toml`에서 관리합니다.

- `faster-whisper`
- `openai`
- `pyqt6`

### GPU 사용 시

- NVIDIA GPU
- 호환 가능한 NVIDIA 드라이버
- CUDA 12 계열 런타임 패키지
- `nvidia-cublas-cu12`

CPU 실행도 가능하지만, 큰 모델에서는 처리 시간이 길어질 수 있습니다.

## 설치 방법

일반 사용자는 GitHub Release에 올라간 Windows 설치 파일을 사용하는 것을 권장합니다.

1. [LectureScribe 최신 릴리즈](https://github.com/frotrue/LectureScribe/releases/latest)에 접속합니다.
2. Assets에서 `LectureScribe_Setup.exe`를 다운로드합니다.
3. 설치 파일을 실행해 안내에 따라 설치합니다.
4. 요약 기능을 사용하려면 실행 전에 `OPENAI_API_KEY` 환경 변수를 설정합니다.

현재 릴리즈:

- [LectureScribe v1.1.0](https://github.com/frotrue/LectureScribe/releases/tag/v1.1.0)
- 설치 파일: [`LectureScribe_Setup.exe`](https://github.com/frotrue/LectureScribe/releases/download/v1.1.0/LectureScribe_Setup.exe)
- SHA256: `7240577a7b6e5f4b6eda886946fa2d362a7de682df7f00d0c05d4bfd49a7582c`

## 환경 설정

아래 절차는 소스 코드로 직접 실행하거나 배포 파일을 새로 빌드할 때 사용합니다.

### 1. 의존성 설치

```powershell
uv sync
uv pip install pyinstaller nvidia-cublas-cu12
```

WSL 또는 Linux 환경에서 GPU 실행에 cuDNN이 필요한 경우:

```bash
uv pip install nvidia-cudnn-cu12==9.*
```

### 2. OpenAI API 키 설정

요약 기능을 사용하려면 `OPENAI_API_KEY` 환경 변수가 필요합니다.

PowerShell:

```powershell
[System.Environment]::SetEnvironmentVariable('OPENAI_API_KEY', 'your-api-key', 'User')
```

CMD:

```cmd
setx OPENAI_API_KEY "your-api-key"
```

환경 변수를 설정한 뒤에는 새 터미널을 열어 실행하세요.

### 3. FFmpeg 확인

`bin/` 폴더에 다음 파일이 있어야 합니다.

```text
bin/ffmpeg.exe
bin/ffprobe.exe
```

## 실행 방법

### Windows

```powershell
uv run python main.py
```

### WSL 또는 Linux

`run_ui.sh`는 WSL 경로 기준으로 작성되어 있습니다. 프로젝트 위치가 다르면 스크립트의 `cd` 경로를 먼저 수정하세요.

```bash
chmod +x run_ui.sh
./run_ui.sh
```

## 사용 방법

### 전사

1. `전사` 탭에서 오디오 파일을 선택합니다.
2. 출력 폴더를 선택합니다. 비워 두면 오디오 파일이 있는 폴더가 사용됩니다.
3. 모델, 장치, `compute_type`, 언어, `beam_size`, VAD 옵션을 설정합니다.
4. 필요한 경우 `전사 후 자동 요약`을 켭니다.
5. `전사 시작`을 누릅니다.

### 요약

1. `요약` 탭에서 전사된 Markdown 파일을 선택합니다.
2. 출력 폴더를 선택합니다. 비워 두면 Markdown 파일이 있는 폴더가 사용됩니다.
3. 요약 모델과 분할 크기를 설정합니다.
4. 필요하면 요약 프롬프트를 수정합니다.
5. `요약 시작`을 누릅니다.

## 주요 설정값

| 항목 | 설명 | 기본/예시 |
| --- | --- | --- |
| 모델 | Faster-Whisper 모델 | `large-v3-turbo` |
| 장치 | 전사 실행 장치 | `cuda`, `cpu` |
| compute_type | 연산 정밀도 | `float16`, `int8_float16`, `int8`, `float32` |
| 언어 | 전사 언어 | `ko`, `en`, `ja`, `auto` |
| beam_size | 디코딩 탐색 폭 | `1`, `3`, `5` |
| VAD | 침묵 구간 필터링 | 켜기/끄기 |
| 요약 모델 | OpenAI 요약 모델 | UI에서 선택 또는 직접 입력 |
| 분할 크기 | 긴 문서 분할 기준 | `30000` chars |

## 출력 파일

전사 결과는 입력 파일명을 기준으로 저장됩니다.

```text
{파일명}_원본.md
{파일명}_요약.md
```

이미 같은 이름의 파일이 있으면 다음처럼 번호가 붙습니다.

```text
{파일명}_원본_1.md
{파일명}_요약_1.md
```

전사 Markdown에는 다음 정보가 포함됩니다.

- 입력 파일명
- 사용 모델
- 실행 장치
- `compute_type`
- 감지 언어
- 언어 감지 확률
- 타임스탬프가 포함된 전사문

## 빌드

### PyInstaller 빌드

```powershell
uv run pyinstaller --noconfirm LectureScribe.spec
```

또는 옵션을 직접 지정해 빌드할 수 있습니다.

```powershell
uv run pyinstaller --noconfirm --onedir --windowed --name "LectureScribe" `
  --collect-all faster_whisper `
  --collect-all ctranslate2 `
  --collect-all nvidia.cublas `
  --add-data "bin/ffmpeg.exe;." `
  --add-data "bin/ffprobe.exe;." `
  main.py
```

빌드 결과는 다음 폴더에 생성됩니다.

```text
dist/LectureScribe/
```

### Windows 설치 파일 생성

1. [Inno Setup 6](https://jrsoftware.org/isdl.php)을 설치합니다.
2. `setup.iss`를 Inno Setup Compiler로 엽니다.
3. `Compile`을 실행합니다.

결과 파일:

```text
dist/LectureScribe_Setup.exe
```

## 문제 해결

### `OPENAI_API_KEY` 오류

요약 기능은 OpenAI API 키가 없으면 실행되지 않습니다. 환경 변수를 설정한 뒤 새 터미널에서 다시 실행하세요.

### `ffmpeg` 또는 `ffprobe` 오류

`bin/ffmpeg.exe`, `bin/ffprobe.exe`가 있는지 확인하세요. PyInstaller 빌드 시에도 두 파일이 포함되어야 합니다.

### CUDA 또는 DLL 오류

GPU 실행에서 DLL 로딩 오류가 나면 다음을 확인하세요.

- NVIDIA 드라이버가 설치되어 있는지
- `nvidia-cublas-cu12`가 설치되어 있는지
- WSL/Linux에서는 `nvidia-cudnn-cu12==9.*`가 필요한지
- CPU로 실행할 경우 UI에서 장치를 `cpu`로 변경했는지

### 큰 모델이 느리거나 메모리가 부족한 경우

`large-v3-turbo` 대신 `medium`, `small`, `base` 모델을 사용하거나 `compute_type`을 `int8`로 변경하세요.

## 라이선스

프로젝트 코드의 라이선스는 별도 라이선스 파일이 추가되기 전까지 저장소 정책을 따릅니다.

번들로 포함되는 `ffmpeg`와 `ffprobe`는 FFmpeg 프로젝트의 라이선스를 따릅니다. 배포 시 FFmpeg 라이선스 조건을 함께 확인하세요.
