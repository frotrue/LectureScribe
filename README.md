# LectureScribe

LectureScribe는 Faster-Whisper 기반 로컬 강의 전사와 OpenAI API 기반 Markdown 요약을 제공하는 PySide6 GUI 애플리케이션입니다.

전사는 로컬 PC에서 실행되며 `OPENAI_API_KEY` 없이 사용할 수 있습니다. 요약 탭에서 직접 요약하거나 전사 후 자동 요약을 사용할 때만 `OPENAI_API_KEY`가 필요합니다.

## 주요 기능

- 로컬 음성 전사: `faster-whisper`와 `ctranslate2` 기반 전사
- 출력 형식 선택: TXT, Markdown, SRT 저장 지원
- OpenAI 요약: 전사 Markdown을 강의 노트 형식으로 요약
- 자동 요약: 전사 완료 후 Markdown 파일을 바로 요약
- 중복 파일 보호: 같은 이름의 결과물이 있으면 `_1`, `_2` 형식으로 자동 저장
- Windows 배포: PyInstaller와 Inno Setup 기반 설치 파일 생성

## 요구 사항

- Python 3.11 이상
- `uv`
- Windows 권장
- `bin/ffmpeg.exe`, `bin/ffprobe.exe`

주요 Python 의존성은 `pyproject.toml`에서 관리합니다.

- `faster-whisper`
- `huggingface-hub`
- `openai`
- `pyside6`

## 설치

일반 사용자는 GitHub Release에서 Windows 설치 파일을 내려받아 사용하는 것을 권장합니다.

1. [LectureScribe 최신 릴리즈](https://github.com/frotrue/LectureScribe/releases/latest)에 접속합니다.
2. Assets에서 `LectureScribe_Setup.exe`를 다운로드합니다.
3. 설치 파일을 실행합니다.
4. 요약 기능을 사용할 경우에만 실행 전에 `OPENAI_API_KEY` 환경 변수를 설정합니다.

현재 릴리즈:

- [LectureScribe v1.1.3](https://github.com/frotrue/LectureScribe/releases/tag/v1.1.3)
- 설치 파일: [`LectureScribe_Setup.exe`](https://github.com/frotrue/LectureScribe/releases/download/v1.1.3/LectureScribe_Setup.exe)
- SHA256: `CD6160F546A8B5355C4123741DBE36CC8E0CA837D256416447FCF7B3B7D6EBDC`

## 개발 환경 실행

```powershell
uv sync
uv run python main.py
```

요약 기능을 사용할 경우 `OPENAI_API_KEY`를 설정합니다.

PowerShell:

```powershell
[System.Environment]::SetEnvironmentVariable('OPENAI_API_KEY', 'your-api-key', 'User')
```

CMD:

```cmd
setx OPENAI_API_KEY "your-api-key"
```

환경 변수를 설정한 뒤에는 터미널 또는 앱을 다시 실행하세요.

## 사용 방법

### 전사

1. `전사` 탭에서 오디오 파일을 선택합니다.
2. 출력 폴더를 선택합니다. 비워 두면 오디오 파일이 있는 폴더를 사용합니다.
3. 모델, 장치, `compute_type`, 언어, `beam_size`, VAD 옵션을 설정합니다.
4. 필요한 출력 형식인 TXT, Markdown, SRT를 선택합니다. 최소 하나는 선택해야 합니다.
5. 필요한 경우 `전사 완료 후 Markdown 파일을 자동 요약`을 켭니다.
6. `전사 시작`을 누릅니다.

전사만 실행할 때는 `OPENAI_API_KEY`가 필요하지 않습니다.

### 요약

1. `요약` 탭에서 전사 Markdown 파일을 선택합니다.
2. 출력 폴더를 선택합니다. 비워 두면 Markdown 파일이 있는 폴더를 사용합니다.
3. 요약 모델과 분할 크기를 설정합니다.
4. 필요한 경우 요약 프롬프트를 수정합니다.
5. `요약 시작`을 누릅니다.

요약 탭에서 직접 요약할 때는 `OPENAI_API_KEY`가 필요합니다.

### 자동 요약

자동 요약은 전사 결과 Markdown 파일을 입력으로 사용합니다. 따라서 자동 요약을 켜려면 Markdown 출력도 함께 켜야 합니다.

자동 요약을 켰는데 `OPENAI_API_KEY`가 없으면 전사를 시작하기 전에 경고가 표시되고 작업이 시작되지 않습니다.

## 장치 설정

기본 장치는 `cpu`입니다. NVIDIA GPU가 없는 PC에서도 기본 설정으로 앱을 실행할 수 있게 하기 위한 설정입니다.

CUDA 환경이 준비된 사용자는 UI의 장치 콤보박스에서 `cuda`를 선택하세요. CUDA 사용 시 NVIDIA 드라이버와 필요한 CUDA 계열 패키지가 설치되어 있어야 합니다.

CPU 기본 `compute_type`은 안정성을 위해 `int8`입니다. GPU를 사용할 때 더 빠른 설정이 필요하면 `float16` 등을 선택할 수 있습니다.

## 출력 파일

전사 결과는 입력 파일명을 기준으로 저장됩니다.

```text
{파일명}_원본.txt
{파일명}_원본.md
{파일명}_원본.srt
{파일명}_요약.md
```

TXT 파일은 타임스탬프가 포함된 일반 텍스트입니다.

```text
00:03 전사 문장...
01:12 다음 문장...
```

Markdown 파일은 모델, 장치, 감지 언어 정보와 타임스탬프 포함 전사본을 저장합니다.

SRT 파일은 표준 자막 형식으로 저장됩니다.

같은 이름의 파일이 이미 있으면 다음처럼 번호가 붙습니다.

```text
{파일명}_원본_1.md
{파일명}_요약_1.md
```

## 빌드

### PyInstaller

```powershell
uv run pyinstaller --noconfirm LectureScribe.spec
```

결과 폴더:

```text
dist/LectureScribe/
```

### Windows 설치 파일

1. [Inno Setup 6](https://jrsoftware.org/isdl.php)을 설치합니다.
2. `setup.iss`를 Inno Setup Compiler로 엽니다.
3. `Compile`을 실행합니다.

결과 파일:

```text
dist/LectureScribe_Setup.exe
```

## 수동 테스트 기준

1. `OPENAI_API_KEY` 없이 앱 실행 후 전사만 실행 가능해야 합니다.
2. 자동 요약 OFF 상태에서 전사 완료 후 요약이 시작되지 않아야 합니다.
3. 자동 요약 ON + `OPENAI_API_KEY` 없음이면 전사 시작 전에 경고가 떠야 합니다.
4. 자동 요약 ON + `OPENAI_API_KEY` 있음이면 전사 후 요약 Markdown 파일이 생성되어야 합니다.
5. TXT/MD/SRT 체크 상태에 따라 실제 파일 생성 결과가 일치해야 합니다.
6. NVIDIA GPU 없는 PC에서도 기본 CPU 설정으로 앱이 실행되어야 합니다.

## 문제 해결

### `OPENAI_API_KEY` 오류

전사만 사용할 때는 API 키가 필요하지 않습니다. 요약 또는 자동 요약을 사용할 때만 `OPENAI_API_KEY`를 설정하세요.

### `ffmpeg` 또는 `ffprobe` 오류

`bin/ffmpeg.exe`, `bin/ffprobe.exe`가 있는지 확인하세요. PyInstaller 빌드 시에도 두 파일이 포함되어야 합니다.

### CUDA 또는 DLL 오류

GPU 실행에서 DLL 로딩 오류가 나면 NVIDIA 드라이버, CUDA 계열 패키지, `nvidia-cublas-cu12` 설치 여부를 확인하세요. CUDA 환경이 준비되지 않은 PC에서는 UI에서 장치를 `cpu`로 두고 실행하세요.

## 라이선스

이 프로젝트의 소스 코드는 [MIT License](./LICENSE)를 따릅니다.

번들 및 의존성 라이선스 정보는 [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)를 확인하세요.
