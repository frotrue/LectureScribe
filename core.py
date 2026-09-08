"""Headless transcription and summarization shared by desktop and CLI."""
import os
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


AUDIO_EXTENSIONS = {'.m4a', '.mp3', '.wav', '.flac', '.aac', '.ogg', '.opus', '.mp4', '.webm'}


class Event:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self, *args):
        for callback in self.callbacks:
            callback(*args)


class Job:
    def __init__(self):
        for name in ('log', 'progress', 'finished_ok', 'failed', 'cancelled',
                     'artifact_created', 'summary_requested', 'segment_ready'):
            setattr(self, name, Event())


@dataclass
class TranscribeConfig:
    audio_path: Path
    output_dir: Path
    model_name: str
    device: str
    compute_type: str
    language: str
    beam_size: int
    vad_filter: bool
    output_txt: bool
    output_md: bool
    output_srt: bool
    auto_summary: bool
    summary_model: str
    summary_prompt: str
    chunk_chars: int


@dataclass
class SummaryConfig:
    md_path: Path
    output_dir: Path
    model_name: str
    summary_prompt: str
    chunk_chars: int
    api_key: str = ""


def srt_time(seconds: float) -> str:
    millis = int((seconds - int(seconds)) * 1000)
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:02},{millis:03}"


def txt_timestamp(seconds: float) -> str:
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h:02}:{m:02}:{s:02}"
    return f"{m:02}:{s:02}"


def get_audio_duration_seconds(audio_path: Path) -> Optional[float]:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=30,
        )
        return float(result.stdout.strip())
    except Exception:
        return None


def split_text_by_chars(text: str, chunk_chars: int) -> list[str]:
    """Rough chunking for long transcript text. Prefer splitting by paragraphs."""
    if chunk_chars <= 0:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for p in paragraphs:
        p_len = len(p)
        if current and current_len + p_len > chunk_chars:
            chunks.append("\n\n".join(current).strip())
            current = [p]
            current_len = p_len
        else:
            current.append(p)
            current_len += p_len

    if current:
        chunks.append("\n\n".join(current).strip())

    return [c for c in chunks if c.strip()]


def get_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    ext = path.suffix
    parent = path.parent
    counter = 1
    while True:
        new_path = parent / f"{stem}_{counter}{ext}"
        if not new_path.exists():
            return new_path
        counter += 1


FASTER_WHISPER_REPOS = {
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    "large-v3": "Systran/faster-whisper-large-v3",
    "medium": "Systran/faster-whisper-medium",
    "small": "Systran/faster-whisper-small",
    "base": "Systran/faster-whisper-base",
}


def materialize_faster_whisper_model(model_name: str, log=None) -> str:
    """Return a local model directory without walking HF snapshot reparse points."""
    model_path = Path(model_name).expanduser()
    if model_path.exists():
        return str(model_path)

    repo_id = FASTER_WHISPER_REPOS.get(model_name, model_name if "/" in model_name else None)
    if not repo_id:
        return model_name

    from huggingface_hub import snapshot_download

    if log:
        log(f"모델 캐시 확인 중: {repo_id}")

    materialized_dir = (
        Path.home()
        / ".cache"
        / "lecture-scribe"
        / "models"
        / repo_id.replace("/", "--")
    )
    materialized_dir.mkdir(parents=True, exist_ok=True)

    downloaded_dir = Path(
        snapshot_download(
            repo_id,
            local_dir=materialized_dir,
            ignore_patterns=[".git", ".git/*"],
        )
    )

    model_file = downloaded_dir / "model.bin"
    if not model_file.exists() or model_file.stat().st_size == 0:
        raise RuntimeError(f"모델 파일을 준비하지 못했습니다: {model_file}")

    if log:
        log(f"모델 로컬 경로: {downloaded_dir}")

    return str(downloaded_dir)


def default_summary_prompt() -> str:
    return """너는 컴퓨터공학 강의를 정리하는 학습 도우미야.
아래 강의 전사본을 바탕으로 Obsidian Markdown 노트를 작성해줘.

요구사항:
1. 전사 오류로 보이는 전문용어를 자연스럽게 교정해줘.
2. 원문에 없는 내용을 과하게 추가하지 마.
3. 불확실한 내용은 [확인 필요]로 표시해줘.
4. 시험에 나올 만한 개념을 따로 정리해줘.
5. C언어/소프트웨어공학/프로그래밍 용어는 가능한 한 정확한 영어 원어를 같이 적어줘.

출력 형식:
# 강의 요약

## 1. 전체 핵심 요약

## 2. 주제별 개념 정리

## 3. 시험 포인트

## 4. 헷갈리기 쉬운 부분

## 5. 용어 교정 목록

## 6. 복습 질문
"""


class SummaryJob(Job):

    def __init__(self, config: SummaryConfig):
        super().__init__()
        self.config = config
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    def run(self):
        try:
            from openai import OpenAI

            if not (self.config.api_key or os.getenv("OPENAI_API_KEY")):
                raise RuntimeError("OPENAI_API_KEY 환경변수가 설정되어 있지 않습니다.")

            cfg = self.config
            cfg.output_dir.mkdir(parents=True, exist_ok=True)

            text = cfg.md_path.read_text(encoding="utf-8")
            chunks = split_text_by_chars(text, cfg.chunk_chars)

            self.log.emit(f"요약 입력 파일: {cfg.md_path}")
            self.log.emit(f"요약 모델: {cfg.model_name}")
            self.log.emit(f"분할 개수: {len(chunks)}")

            if not chunks:
                raise ValueError("요약할 내용이 없습니다. 다른 파일을 선택하세요.")
            client = OpenAI(api_key=cfg.api_key or os.getenv("OPENAI_API_KEY"), timeout=60.0, max_retries=1)
            partial_summaries: list[str] = []

            for idx, chunk in enumerate(chunks, start=1):
                if self._cancel_requested:
                    self.log.emit("사용자 요청으로 요약을 중단했습니다.")
                    self.cancelled.emit()
                    return

                self.log.emit(f"부분 요약 중... {idx}/{len(chunks)}")

                response = client.responses.create(
                    model=cfg.model_name,
                    input=[
                        {
                            "role": "developer",
                            "content": cfg.summary_prompt,
                        },
                        {
                            "role": "user",
                            "content": f"다음은 강의 전사본의 {idx}/{len(chunks)}번째 부분이야. 이 부분을 요약해줘.\n\n{chunk}",
                        },
                    ],
                )

                if self._cancel_requested:
                    self.cancelled.emit()
                    return
                partial_summaries.append(response.output_text.strip())
                self.progress.emit(int(idx / len(chunks) * 70))

            if len(partial_summaries) == 1:
                final_summary = partial_summaries[0]
            else:
                self.log.emit("부분 요약 통합 중...")
                merged = "\n\n---\n\n".join(
                    f"## 부분 요약 {i}\n\n{s}"
                    for i, s in enumerate(partial_summaries, start=1)
                )

                response = client.responses.create(
                    model=cfg.model_name,
                    input=[
                        {
                            "role": "developer",
                            "content": cfg.summary_prompt,
                        },
                        {
                            "role": "user",
                            "content": "아래 부분 요약들을 하나의 최종 Obsidian Markdown 강의노트로 통합해줘. 중복은 줄이고, 시험 포인트와 용어 교정을 강화해줘.\n\n" + merged,
                        },
                    ],
                )
                final_summary = response.output_text.strip()

            if self._cancel_requested:
                self.cancelled.emit()
                return

            base_name = cfg.md_path.stem
            if base_name.endswith("_원본"):
                summary_name = base_name[:-3] + "_요약.md"
            else:
                summary_name = f"{base_name}_요약.md"

            out_path = get_unique_path(cfg.output_dir / summary_name)
            out_path.write_text(final_summary, encoding="utf-8")

            self.artifact_created.emit(str(out_path))
            self.progress.emit(100)
            self.log.emit(f"요약 저장: {out_path}")
            self.finished_ok.emit(str(out_path))

        except Exception as e:
            self.failed.emit(str(e))


class TranscribeJob(Job):

    def __init__(self, config: TranscribeConfig, model_cache=None):
        super().__init__()
        self.model_cache = model_cache
        self.config = config
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    def run(self):
        try:
            from faster_whisper import WhisperModel

            cfg = self.config
            cfg.output_dir.mkdir(parents=True, exist_ok=True)

            self.log.emit(f"입력 파일: {cfg.audio_path}")
            self.log.emit(f"출력 폴더: {cfg.output_dir}")
            self.log.emit(f"모델 로딩 중: {cfg.model_name}")
            self.log.emit(f"device={cfg.device}, compute_type={cfg.compute_type}")

            duration = get_audio_duration_seconds(cfg.audio_path)
            if duration:
                self.log.emit(f"오디오 길이: 약 {duration / 60:.1f}분")
            else:
                self.log.emit("오디오 길이를 가져오지 못했습니다. 진행률은 대략적으로 표시됩니다.")

            cache_key = (cfg.model_name, cfg.device, cfg.compute_type)
            model = self.model_cache.get(cache_key) if self.model_cache is not None else None
            if model is None:
                model_path = materialize_faster_whisper_model(cfg.model_name, self.log.emit)
                if self._cancel_requested:
                    self.cancelled.emit()
                    return
                model = WhisperModel(model_path, device=cfg.device, compute_type=cfg.compute_type)
                if self.model_cache is not None:
                    self.model_cache[cache_key] = model
            else:
                self.log.emit('이미 로드된 모델을 재사용합니다.')

            if self._cancel_requested:
                self.cancelled.emit()
                return
            self.log.emit("전사 시작")

            segments, info = model.transcribe(
                str(cfg.audio_path),
                language=cfg.language or None,
                task="transcribe",
                beam_size=cfg.beam_size,
                vad_filter=cfg.vad_filter,
                vad_parameters=dict(min_silence_duration_ms=500),
            )

            self.log.emit(f"감지 언어: {info.language}, 확률: {info.language_probability:.2f}")

            base_name = cfg.audio_path.stem
            transcript_entries = []
            last_percent = 0
            cancelled = False

            for i, segment in enumerate(segments, start=1):
                if self._cancel_requested:
                    self.log.emit("사용자 요청으로 중단했습니다.")
                    cancelled = True
                    break

                text = segment.text.strip()
                if not text:
                    continue

                start_min = int(segment.start // 60)
                start_sec = int(segment.start % 60)
                timestamp = f"[{start_min:02}:{start_sec:02}]"
                transcript_entries.append(
                    {
                        "start": segment.start,
                        "end": segment.end,
                        "timestamp": timestamp,
                        "text": text,
                    }
                )

                self.segment_ready.emit(f"{timestamp} {text}")

                if duration and duration > 0:
                    percent = min(99, int((segment.end / duration) * 100))
                    if percent > last_percent:
                        last_percent = percent
                        self.progress.emit(percent)

                if i % 10 == 0:
                    self.log.emit(f"진행 중... 마지막 구간 {timestamp}")

            cancelled = cancelled or self._cancel_requested
            if cancelled:
                base_name += "_부분"
            if cancelled and not transcript_entries:
                self.cancelled.emit()
                return

            original_md_path: Optional[Path] = None

            if cfg.output_md:
                original_md_path = get_unique_path(cfg.output_dir / f"{base_name}_원본.md")
                md_lines = [
                    "# 강의 전사",
                    "",
                    f"- 파일: `{cfg.audio_path.name}`",
                    f"- 모델: `{cfg.model_name}`",
                    f"- 장치: `{cfg.device}`",
                    f"- compute_type: `{cfg.compute_type}`",
                    f"- 언어: `{info.language}`",
                    f"- 언어 확률: `{info.language_probability:.2f}`",
                    "",
                    "## 전사본",
                    "",
                ]
                for entry in transcript_entries:
                    md_lines.append(f"{entry['timestamp']} {entry['text']}")
                    md_lines.append("")
                original_md_path.write_text("\n".join(md_lines), encoding="utf-8")
                self.artifact_created.emit(str(original_md_path))
                self.log.emit(f"Markdown 저장: {original_md_path}")

            if cfg.output_txt:
                original_txt_path = get_unique_path(cfg.output_dir / f"{base_name}_원본.txt")
                txt_lines = [
                    f"{txt_timestamp(entry['start'])} {entry['text']}"
                    for entry in transcript_entries
                ]
                original_txt_path.write_text("\n".join(txt_lines) + "\n", encoding="utf-8")
                self.artifact_created.emit(str(original_txt_path))
                self.log.emit(f"TXT 저장: {original_txt_path}")

            if cfg.output_srt:
                original_srt_path = get_unique_path(cfg.output_dir / f"{base_name}_원본.srt")
                srt_blocks = []
                for idx, entry in enumerate(transcript_entries, start=1):
                    srt_blocks.append(
                        f"{idx}\n"
                        f"{srt_time(entry['start'])} --> {srt_time(entry['end'])}\n"
                        f"{entry['text']}"
                    )
                original_srt_path.write_text("\n\n".join(srt_blocks) + "\n", encoding="utf-8")
                self.artifact_created.emit(str(original_srt_path))
                self.log.emit(f"SRT 저장: {original_srt_path}")

            if cancelled:
                self.log.emit("전사를 중단했습니다. 생성된 파일은 일부 구간만 포함합니다.")
                self.cancelled.emit()
                return
            self.progress.emit(100)
            self.finished_ok.emit(str(cfg.output_dir))

            if cfg.auto_summary and original_md_path is not None and not cancelled:
                self.summary_requested.emit(str(original_md_path))

        except Exception as e:
            self.failed.emit(str(e))
