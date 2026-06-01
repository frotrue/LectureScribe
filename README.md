# Faster-Whisper Local GUI Transcriber + OpenAI Summary

이 프로젝트는 로컬 PC에서 **Faster-Whisper(CUDA GPU 가속 지원)**를 사용하여 오디오 파일을 빠르게 텍스트로 받아쓰기(Transcription)한 후, **OpenAI API**를 연동하여 깔끔한 **Obsidian Markdown 강의노트 및 요약본**을 자동으로 생성해 주는 PyQt6 기반 데스크톱 애플리케이션입니다.

---

## ✨ 핵심 기능

1. **로컬 고성능 음성 인식**:
   - `faster-whisper` (CTranslate2 연산 엔진) 기반으로 큰 리소스 없이 로컬에서 고품질 음성 인식을 지원합니다.
   - NVIDIA 외장 그래픽카드 장착 시 **CUDA GPU 가속**을 사용하여 초고속 처리가 가능합니다.
2. **AI 기반 Obsidian 강의노트 요약**:
   - 받아쓰기가 완료된 Markdown 파일을 대상으로 OpenAI API를 연동하여 주제별 핵심 요약, 시험 포인트, 오번역 용어 교정, 복습 질문이 완벽히 구성된 강의노트를 자동 제작합니다.
3. **파일명 중복 및 덮어쓰기 방지**:
   - 입력한 오디오 파일 이름에 맞추어 `[파일명]_원본.md`, `[파일명]_요약.md` 형식으로 저장됩니다.
   - 동일 폴더 내 동일 파일명이 있을 경우, `_1`, `_2` 등 숫자 접미사가 붙어 **기존 자료가 덮어씌워지는 것을 자동으로 완벽히 예방**합니다.
4. **배포용 초고압축 인스톨러 지원**:
   - 의존성 수집 빌드를 거쳐, 최종 사용자 배포용 **Inno Setup 기반 윈도우 단독 설치 파일(`Setup.exe`)** 빌드를 지원합니다.

---

## 🛠️ 필수 의존성 및 사전 설정

### 1. 🔑 OpenAI API 키 등록 (필수)
애플리케이션의 요약 기능을 정상적으로 사용하려면 **OpenAI API Key가 윈도우 환경변수에 등록되어 있어야 합니다.**

* **Windows PowerShell 설정 방법**:
  ```powershell
  [System.Environment]::SetEnvironmentVariable('OPENAI_API_KEY', 'your-actual-api-key-here', 'User')
  ```
  *(※ 환경변수를 설정한 후, 새로운 터미널이나 CMD 창을 열어야 설정이 정상적으로 반영됩니다.)*

* **Windows 명령 프롬프트(CMD) 설정 방법**:
  ```cmd
  setx OPENAI_API_KEY "your-actual-api-key-here"
  ```

---

## 🚀 로컬 개발 환경 구축 및 실행 방법

이 프로젝트는 차세대 파이썬 패키지 매니저인 **`uv`**를 사용하여 빠르고 안전하게 가상환경을 구성합니다.

### 1단계: 가상환경 동기화 및 의존성 설치
프로젝트 폴더 내에서 터미널을 열고 다음 명령을 실행합니다.
```powershell
# 가상환경 구축 및 pyproject.toml 의존성 동기화
uv sync

# GPU 가속(CUDA) 구동을 위한 필수 cublas 런타임 라이브러리 추가
uv pip install pyinstaller nvidia-cublas-cu12
```

### 2단계: 외부 미디어 도구 (`ffmpeg` & `ffprobe`) 배치
앱이 가동되기 위해 `bin/` 폴더 내에 `ffmpeg.exe`와 `ffprobe.exe` 바이너리가 존재해야 합니다.
아래 자동 다운로드 스크립트를 사용하여 1초 만에 세팅을 끝마칠 수 있습니다.
```powershell
uv run python scratch/download_ffmpeg.py
```

### 3단계: 애플리케이션 가동
```powershell
uv run python main.py
```

---

## 📦 독립 실행형 (.exe) 배포판 및 인스톨러 제작 방법

사용자 PC에 파이썬, 가상환경, CUDA Toolkit 등이 설치되어 있지 않아도 **더블클릭만으로 GPU 가속 음성인식**을 바로 가동할 수 있는 단독 배포판을 만듭니다.

### 1단계: PyInstaller를 통한 GPU 의존성 번들 빌드
아래 명령어를 입력하여 불필요한 DLL(cuDNN, NVRTC 등 1.2GB 상당)을 완벽히 소거하고, 오직 필수적인 cuBLAS 가속 라이브러리와 PyQt6를 포함한 최적의 패키지 폴더를 빌드합니다.
```powershell
uv run pyinstaller --noconfirm --onedir --windowed --name "WhisperTranscriber" `
  --collect-all faster_whisper `
  --collect-all ctranslate2 `
  --collect-all nvidia.cublas `
  --add-data "bin/ffmpeg.exe;." `
  --add-data "bin/ffprobe.exe;." `
  main.py
```
*(※ 빌드가 완료되면 `dist/WhisperTranscriber` 폴더(약 1.21 GB)가 생성됩니다.)*

### 2단계: Inno Setup을 사용한 초고압축 인스톨러(`Setup.exe`) 생성
대용량 패키지 폴더를 인터넷 배포가 용이하도록 **초고압축 단일 설치 파일(약 547 MB, 약 77% 크기 절감)**로 제작합니다.

1. [Inno Setup 6 공식 홈페이지](https://jrsoftware.org/isdl.php)에서 무료 컴파일러를 다운로드 및 설치합니다.
2. 프로젝트 폴더 내 **`setup.iss`** 파일을 열고 컴파일(`Ctrl + F9`)을 누릅니다.
3. 컴파일이 성공적으로 끝나면, **`dist/WhisperTranscriber_Setup.exe`** 설치 실행 파일 하나가 최종 완성됩니다.

---

## 🤝 라이선스 및 저작권
* 이 프로젝트의 파이썬 핵심 코드는 MIT License 하에 자유롭게 복제 및 수정하여 사용할 수 있습니다.
* 번들링된 `ffmpeg` 및 `ffprobe` 바이너리는 각각의 LGPL/GPL 라이선스를 준수합니다.
