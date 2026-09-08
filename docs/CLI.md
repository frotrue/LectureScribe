# LectureScribe CLI — 자동화·LLM 에이전트 사용법

GUI를 열지 않고 녹음 파일과 폴더를 처리합니다. 전사 기본값은 로컬 CPU / small 모델 / 한국어 / 요약 OFF입니다. 첫 실행에는 모델 다운로드가 필요할 수 있습니다.

## 준비

저장소 루트에서 실행합니다.

```powershell
uv sync
uv run python cli.py --help
uv run python cli.py transcribe --help
```

CLI 진입점은 Qt를 import하지 않습니다. 전사·요약 엔진은 GUI와 공유합니다. 프로젝트 전체 의존성에는 GUI용 PySide6도 포함되지만, CLI 실행 자체에는 디스플레이가 필요하지 않습니다.

## 폴더 전체 전사 — 요약 끄기

```powershell
uv run python cli.py transcribe "D:\Lectures" --recursive --summary off --output-dir "D:\LectureNotes" --json
```

- 지원 확장자: m4a, mp3, wav, flac, aac, ogg, opus, mp4, webm (대소문자 무관)
- 폴더에서는 지원 파일만 처리합니다. 오디오가 없는 동영상이나 손상 파일은 해당 파일 실패로 보고합니다.
- `--recursive`를 생략하면 지정한 폴더 바로 아래 파일만 처리합니다.
- `--output-dir`을 생략하면 각 원본 파일 옆에 저장합니다.
- 출력 폴더를 지정하면 입력의 하위 폴더 구조를 유지합니다. 별도의 출력 하위 폴더는 입력 탐색에서 제외합니다.
- 파일 또는 폴더를 여러 개 지정할 수 있습니다. 동일한 실제 경로는 한 번만 처리합니다.
- 폴더 안의 심볼릭 링크 파일은 자동 수집하지 않습니다.
- 모델은 배치 실행 중 재사용합니다. 파일은 한 개씩 처리합니다.
- 기존 결과가 있으면 `_1`, `_2` 등 번호를 붙여 보호합니다. 재실행 시 자동으로 건너뛰지는 않습니다.

## 전사 후 요약 켜기

API 키는 환경변수 `OPENAI_API_KEY`로 제공하세요. CLI 인자로 키를 전달하거나 결과 JSON에 키를 출력하지 않습니다.

```powershell
uv run python cli.py transcribe "D:\Lectures" --recursive --summary on --summary-model gpt-5.4-mini --output-dir "D:\LectureNotes" --json
```

요약은 OpenAI API에 전사 텍스트를 전송하며 별도 API 사용료가 발생합니다. API 키가 없으면 전사를 시작하기 전에 종료 코드 2로 끝납니다. 요약 모델명은 본인 API에서 사용할 모델로 지정할 수 있습니다.

`--summary on`은 Markdown 출력을 자동 포함합니다. 전사에 성공한 파일을 요약하고 같은 출력 폴더에 저장합니다. 요약만 실패해도 전사 결과는 유지하며, 해당 입력은 `failed`로 보고합니다.

## GPU·고급 옵션

```powershell
uv run python cli.py transcribe "D:\Lectures" -r -o "D:\LectureNotes" --device cuda --model large-v3-turbo --compute-type float16 --language ko --formats md,srt --summary off --json
```

| 옵션 | 기본값 / 의미 |
|---|---|
| `--model` | `small`; 모델명, Hugging Face 저장소 또는 로컬 모델 폴더 |
| `--device` | `cpu`; `cuda` 선택 가능 |
| `--compute-type` | CPU는 `int8`, CUDA는 `float16` |
| `--language` | `ko`; `en`, `ja`, `auto` 등 |
| `--beam-size` | `5`; `1`, `3`, `5` 지원 |
| `--vad` | `on`; `off`로 침묵 필터 비활성화 |
| `--formats` | `txt,md,srt`; 쉼표로 지정 |
| `--summary` | `off`; 전사 후 요약은 `on` |
| `--summary-model` | `gpt-5.4-mini`; 모델명 직접 지정 |
| `--prompt-file` | 기본 지침 대신 사용할 UTF-8 텍스트 파일 |
| `--chunk-chars` | `30000`; 요약 분할 목표 글자 수 |
| `--verbose` | 상세 처리 로그 포함 |
| `--fail-fast` | 첫 실패 이후 다음 입력을 처리하지 않음 |

CUDA 옵션은 NVIDIA GPU와 준비된 CUDA 실행 환경이 필요합니다. CPU에서 `float16` 또는 `int8_float16`을 지정하면 실행 전에 오류를 반환합니다.

## 기존 전사본만 요약

```powershell
uv run python cli.py summarize "D:\LectureNotes" --recursive --output-dir "D:\Summaries" --json
```

TXT와 Markdown을 처리합니다. 폴더 탐색에서 이름에 `_요약`이 포함된 파일은 제외하여 기존 요약을 다시 요약하지 않습니다. 해당 파일을 명시적으로 입력하면 처리할 수 있습니다. 같은 강의의 TXT와 Markdown을 모두 넣으면 각각 요약하므로, 필요한 형식만 모은 폴더나 개별 파일 목록을 전달하세요.

## 실행 전 대상 확인

```powershell
uv run python cli.py transcribe "D:\Lectures" --recursive --summary on --output-dir "D:\LectureNotes" --dry-run --json
```

모델 다운로드, 파일 생성, API 호출 없이 입력·출력 경로를 확인합니다. `--dry-run`에는 API 키가 필요하지 않습니다. 실제 파일 처리 가능 여부나 CUDA 환경까지 검증하는 기능은 아닙니다.

## LLM·스크립트 출력 계약

`--json`을 지정하면 stdout은 한 줄에 하나의 JSON 객체인 **JSON Lines** 형식입니다. 종속 라이브러리의 일반 출력은 stderr로 보냅니다. stdout 전체를 하나의 JSON 문서로 해석하지 말고 줄 단위로 파싱하세요.

모든 이벤트는 `schema_version: 1`을 포함합니다.

| event | 주요 필드 |
|---|---|
| `batch_start` | `total`, `command`, `summary`, `dry_run`, `formats` |
| `planned_file` | `input`, `output_dir`; dry-run에서만 출력 |
| `file_start` | `index`, `total`, `input`, `output_dir` |
| `phase_start` | `input`, `phase`: `transcribe` 또는 `summarize` |
| `progress` | `input`, `phase`, `percent`; 로딩 중에는 없을 수 있음 |
| `file_saved` | `input`, `phase`, `path`: 실제 생성된 파일 경로 |
| `log` | `input`, `phase`, `message`; `--verbose`에서만 출력 |
| `error` | `message`; 파일 작업 오류는 `input`, `phase`, 사전 검증 오류는 `exit_code` 포함 |
| `file_complete` | `input`, `status`, `outputs`, `error` |
| `batch_complete` | `total`, `succeeded`, `failed`, `cancelled`, `unprocessed`, `exit_code` |

예시:

```json
{"schema_version":1,"event":"file_complete","input":"D:\\Lectures\\class01.m4a","status":"succeeded","outputs":["D:\\LectureNotes\\class01_원본.md"],"error":null}
{"schema_version":1,"event":"batch_complete","total":1,"succeeded":1,"failed":0,"cancelled":0,"unprocessed":0,"elapsed_seconds":34.2,"exit_code":0}
```

`status`는 `succeeded`, `failed`, `cancelled` 중 하나입니다. 결과 파일명은 추측하지 말고 `outputs` 또는 `file_saved.path`를 사용하세요. 중단된 전사 결과는 파일명에 `_부분`이 붙으며 전체 전사로 취급하면 안 됩니다.

일반 실행은 `total = succeeded + failed + cancelled + unprocessed`입니다. dry-run은 성공 수를 늘리지 않고 `planned`에 대상 수, `unprocessed`에 처리하지 않은 전체 수를 반환합니다.

### 종료 코드

| 코드 | 의미 |
|---|---|
| `0` | 전체 성공 또는 dry-run 성공 |
| `1` | 하나 이상의 파일 처리 실패 |
| `2` | 잘못된 입력·옵션, 대상 파일 없음, API 키 누락 등 실행 전 오류 |
| `130` | Ctrl+C로 중단 |

argparse 문법 오류와 `--help`는 표준 CLI 동작으로 일반 텍스트를 출력합니다. 정상적으로 해석된 명령의 입력 검증 오류는 JSON 이벤트로 출력합니다.

기본적으로 파일 하나가 실패해도 다음 파일을 계속 처리합니다. Ctrl+C는 현재 작업에 중단을 요청하고 다음 파일 처리를 막습니다. 모델 다운로드·현재 처리 구간·API 요청이 종료될 때까지 기다릴 수 있습니다.

## 에이전트 실행 순서

1. `--dry-run --json`으로 대상 경로를 확인합니다.
2. 사용자 요청에 맞춰 `--summary off` 또는 `on`을 명시하여 실행합니다.
3. JSON Lines를 줄 단위로 읽고 `file_complete.outputs`를 수집합니다.
4. 프로세스 종료 코드와 `batch_complete`를 확인합니다. 실패·중단·미처리 파일을 성공으로 보고하지 않습니다.
5. 요약 실패 시 남아 있는 Markdown 전사본으로 `summarize`를 실행할 수 있습니다. 유료 요청 재실행 여부는 호출하는 에이전트가 사용자 요청 범위에 맞춰 결정합니다.
