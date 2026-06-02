import os
import sys
import subprocess
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# PyInstaller 패키징 환경에서 ffmpeg/ffprobe 및 CUDA DLL 경로를 동적으로 추가
if hasattr(sys, '_MEIPASS'):
    bundle_dir = Path(sys._MEIPASS)
    # ffmpeg 및 ffprobe 실행 경로 추가
    os.environ["PATH"] = str(bundle_dir) + os.pathsep + os.environ["PATH"]
    # nvidia-cublas, nvidia-cudnn 등 하위 폴더의 모든 DLL 로드를 위해 PATH와 DLL 디렉토리로 동적 추가
    for path in bundle_dir.rglob("*.dll"):
        dll_dir = path.parent
        if str(dll_dir) not in os.environ["PATH"]:
            os.environ["PATH"] = str(dll_dir) + os.pathsep + os.environ["PATH"]
            if hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(str(dll_dir))
                except Exception:
                    pass

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QComboBox,
    QProgressBar,
    QTextEdit,
    QLineEdit,
    QCheckBox,
    QMessageBox,
    QGroupBox,
    QFormLayout,
    QTabWidget,
    QSpinBox,
)


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
    """Return a real-file model directory, avoiding Windows HF snapshot symlinks."""
    model_path = Path(model_name).expanduser()
    if model_path.exists():
        return str(model_path)

    repo_id = FASTER_WHISPER_REPOS.get(model_name, model_name if "/" in model_name else None)
    if not repo_id:
        return model_name

    from huggingface_hub import snapshot_download

    if log:
        log(f"모델 캐시 확인 중: {repo_id}")

    snapshot_dir = Path(snapshot_download(repo_id))
    materialized_dir = (
        Path.home()
        / ".cache"
        / "lecture-scribe"
        / "models"
        / repo_id.replace("/", "--")
    )
    materialized_dir.mkdir(parents=True, exist_ok=True)

    for source in snapshot_dir.iterdir():
        if not source.is_file():
            continue

        resolved_source = source.resolve()
        destination = materialized_dir / source.name
        source_size = resolved_source.stat().st_size

        if destination.exists() and destination.stat().st_size == source_size:
            continue

        if destination.exists():
            destination.unlink()

        try:
            os.link(resolved_source, destination)
        except OSError:
            shutil.copy2(resolved_source, destination)

    model_file = materialized_dir / "model.bin"
    if not model_file.exists() or model_file.stat().st_size == 0:
        raise RuntimeError(f"모델 파일을 준비하지 못했습니다: {model_file}")

    if log:
        log(f"모델 로컬 경로: {materialized_dir}")

    return str(materialized_dir)


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


class SummaryWorker(QThread):
    log = Signal(str)
    progress = Signal(int)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, config: SummaryConfig):
        super().__init__()
        self.config = config
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    def run(self):
        try:
            from openai import OpenAI

            if not os.getenv("OPENAI_API_KEY"):
                raise RuntimeError("OPENAI_API_KEY 환경변수가 설정되어 있지 않습니다.")

            cfg = self.config
            cfg.output_dir.mkdir(parents=True, exist_ok=True)

            text = cfg.md_path.read_text(encoding="utf-8")
            chunks = split_text_by_chars(text, cfg.chunk_chars)

            self.log.emit(f"요약 입력 파일: {cfg.md_path}")
            self.log.emit(f"요약 모델: {cfg.model_name}")
            self.log.emit(f"분할 개수: {len(chunks)}")

            client = OpenAI()
            partial_summaries: list[str] = []

            for idx, chunk in enumerate(chunks, start=1):
                if self._cancel_requested:
                    self.log.emit("사용자 요청으로 요약을 중단했습니다.")
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

            base_name = cfg.md_path.stem
            if base_name.endswith("_원본"):
                summary_name = base_name[:-3] + "_요약.md"
            else:
                summary_name = f"{base_name}_요약.md"
                
            out_path = get_unique_path(cfg.output_dir / summary_name)
            out_path.write_text(final_summary, encoding="utf-8")

            self.progress.emit(100)
            self.log.emit(f"요약 저장: {out_path}")
            self.finished_ok.emit(str(out_path))

        except Exception as e:
            self.failed.emit(str(e))


class TranscribeWorker(QThread):
    log = Signal(str)
    progress = Signal(int)
    finished_ok = Signal(str)
    failed = Signal(str)
    summary_requested = Signal(str)

    def __init__(self, config: TranscribeConfig):
        super().__init__()
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

            model_path = materialize_faster_whisper_model(cfg.model_name, self.log.emit)

            model = WhisperModel(
                model_path,
                device=cfg.device,
                compute_type=cfg.compute_type,
            )

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

                if duration and duration > 0:
                    percent = min(99, int((segment.end / duration) * 100))
                    if percent > last_percent:
                        last_percent = percent
                        self.progress.emit(percent)

                if i % 10 == 0:
                    self.log.emit(f"진행 중... 마지막 구간 {timestamp}")

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
                self.log.emit(f"Markdown 저장: {original_md_path}")

            if cfg.output_txt:
                original_txt_path = get_unique_path(cfg.output_dir / f"{base_name}_원본.txt")
                txt_lines = [
                    f"{txt_timestamp(entry['start'])} {entry['text']}"
                    for entry in transcript_entries
                ]
                original_txt_path.write_text("\n".join(txt_lines) + "\n", encoding="utf-8")
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
                self.log.emit(f"SRT 저장: {original_srt_path}")

            self.progress.emit(100)
            self.finished_ok.emit(str(cfg.output_dir))

            if cfg.auto_summary and original_md_path is not None and not cancelled:
                self.summary_requested.emit(str(original_md_path))

        except Exception as e:
            self.failed.emit(str(e))


class WhisperUI(QWidget):
    def __init__(self):
        super().__init__()
        self.transcribe_worker: Optional[TranscribeWorker] = None
        self.summary_worker: Optional[SummaryWorker] = None
        self.setWindowTitle("LectureScribe")
        self.resize(920, 760)
        self.build_ui()

    def build_ui(self):
        root = QVBoxLayout()

        title = QLabel("LectureScribe")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        root.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self.build_transcribe_tab(), "전사")
        tabs.addTab(self.build_summary_tab(), "요약")
        root.addWidget(tabs)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        root.addWidget(self.progress_bar)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        root.addWidget(self.log_box)

        self.setLayout(root)

    def build_transcribe_tab(self) -> QWidget:
        tab = QWidget()
        root = QVBoxLayout()

        file_group = QGroupBox("파일 설정")
        file_layout = QFormLayout()

        self.audio_input = QLineEdit()
        self.audio_input.setPlaceholderText("m4a/mp3/wav 파일 선택")
        browse_audio_btn = QPushButton("오디오 선택")
        browse_audio_btn.clicked.connect(self.select_audio)
        audio_row = QHBoxLayout()
        audio_row.addWidget(self.audio_input)
        audio_row.addWidget(browse_audio_btn)
        file_layout.addRow("오디오 파일", audio_row)

        self.output_input = QLineEdit()
        self.output_input.setPlaceholderText("출력 폴더 선택")
        browse_output_btn = QPushButton("출력 폴더")
        browse_output_btn.clicked.connect(self.select_output_dir)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_input)
        output_row.addWidget(browse_output_btn)
        file_layout.addRow("출력 폴더", output_row)

        file_group.setLayout(file_layout)
        root.addWidget(file_group)

        model_group = QGroupBox("전사 모델 설정")
        model_layout = QFormLayout()

        self.model_combo = QComboBox()
        self.model_combo.addItems(["large-v3-turbo", "large-v3", "medium", "small", "base"])
        model_layout.addRow("모델", self.model_combo)

        self.device_combo = QComboBox()
        self.device_combo.addItems(["cpu", "cuda"])
        model_layout.addRow("장치", self.device_combo)

        self.compute_combo = QComboBox()
        self.compute_combo.addItems(["float16", "int8_float16", "int8", "float32"])
        self.compute_combo.setCurrentText("int8")
        model_layout.addRow("compute_type", self.compute_combo)

        self.language_combo = QComboBox()
        self.language_combo.addItems(["ko", "en", "ja", "auto"])
        model_layout.addRow("언어", self.language_combo)

        self.beam_combo = QComboBox()
        self.beam_combo.addItems(["1", "3", "5"])
        self.beam_combo.setCurrentText("5")
        model_layout.addRow("beam_size", self.beam_combo)

        self.vad_check = QCheckBox("VAD 사용: 침묵 구간 건너뛰기")
        self.vad_check.setChecked(True)
        model_layout.addRow("VAD", self.vad_check)

        model_group.setLayout(model_layout)
        root.addWidget(model_group)

        output_group = QGroupBox("출력 형식")
        output_layout = QHBoxLayout()
        self.txt_check = QCheckBox("TXT")
        self.md_check = QCheckBox("Markdown")
        self.srt_check = QCheckBox("SRT")
        self.txt_check.setChecked(True)
        self.md_check.setChecked(True)
        self.srt_check.setChecked(True)
        output_layout.addWidget(self.txt_check)
        output_layout.addWidget(self.md_check)
        output_layout.addWidget(self.srt_check)
        output_group.setLayout(output_layout)
        root.addWidget(output_group)

        auto_group = QGroupBox("전사 후 자동 요약")
        auto_layout = QFormLayout()
        self.auto_summary_check = QCheckBox("전사 완료 후 Markdown 파일을 자동 요약")
        self.auto_summary_check.setChecked(False)
        auto_layout.addRow("자동 요약", self.auto_summary_check)
        auto_group.setLayout(auto_layout)
        root.addWidget(auto_group)

        button_row = QHBoxLayout()
        self.start_btn = QPushButton("전사 시작")
        self.start_btn.clicked.connect(self.start_transcription)
        self.cancel_transcribe_btn = QPushButton("전사 중단")
        self.cancel_transcribe_btn.clicked.connect(self.cancel_transcription)
        self.cancel_transcribe_btn.setEnabled(False)
        button_row.addWidget(self.start_btn)
        button_row.addWidget(self.cancel_transcribe_btn)
        root.addLayout(button_row)

        tab.setLayout(root)
        return tab

    def build_summary_tab(self) -> QWidget:
        tab = QWidget()
        root = QVBoxLayout()

        summary_file_group = QGroupBox("요약할 Markdown 파일")
        summary_file_layout = QFormLayout()

        self.summary_md_input = QLineEdit()
        self.summary_md_input.setPlaceholderText("전사된 .md 파일 선택")
        browse_md_btn = QPushButton("MD 선택")
        browse_md_btn.clicked.connect(self.select_summary_md)
        md_row = QHBoxLayout()
        md_row.addWidget(self.summary_md_input)
        md_row.addWidget(browse_md_btn)
        summary_file_layout.addRow("Markdown", md_row)

        self.summary_output_input = QLineEdit()
        self.summary_output_input.setPlaceholderText("요약 출력 폴더")
        browse_summary_output_btn = QPushButton("출력 폴더")
        browse_summary_output_btn.clicked.connect(self.select_summary_output_dir)
        summary_output_row = QHBoxLayout()
        summary_output_row.addWidget(self.summary_output_input)
        summary_output_row.addWidget(browse_summary_output_btn)
        summary_file_layout.addRow("출력 폴더", summary_output_row)

        summary_file_group.setLayout(summary_file_layout)
        root.addWidget(summary_file_group)

        summary_model_group = QGroupBox("요약 API 설정")
        summary_model_layout = QFormLayout()

        self.summary_model_combo = QComboBox()
        self.summary_model_combo.setEditable(True)
        self.summary_model_combo.addItems([
            "gpt-5.4-mini",
            "gpt-5.4-nano",
            "gpt-5.5",
            "gpt-5-mini",
            "gpt-4.1-mini",
            "gpt-4o-mini",
        ])
        summary_model_layout.addRow("요약 모델", self.summary_model_combo)

        self.chunk_spin = QSpinBox()
        self.chunk_spin.setRange(5000, 100000)
        self.chunk_spin.setSingleStep(5000)
        self.chunk_spin.setValue(30000)
        summary_model_layout.addRow("분할 크기(chars)", self.chunk_spin)

        summary_model_group.setLayout(summary_model_layout)
        root.addWidget(summary_model_group)

        prompt_group = QGroupBox("요약 프롬프트")
        prompt_layout = QVBoxLayout()
        self.prompt_box = QTextEdit()
        self.prompt_box.setPlainText(default_summary_prompt())
        prompt_layout.addWidget(self.prompt_box)
        prompt_group.setLayout(prompt_layout)
        root.addWidget(prompt_group)

        button_row = QHBoxLayout()
        self.summary_btn = QPushButton("요약 시작")
        self.summary_btn.clicked.connect(self.start_summary)
        self.cancel_summary_btn = QPushButton("요약 중단")
        self.cancel_summary_btn.clicked.connect(self.cancel_summary)
        self.cancel_summary_btn.setEnabled(False)
        button_row.addWidget(self.summary_btn)
        button_row.addWidget(self.cancel_summary_btn)
        root.addLayout(button_row)

        tab.setLayout(root)
        return tab

    def select_audio(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "오디오 파일 선택",
            str(Path.home()),
            "Audio Files (*.m4a *.mp3 *.wav *.flac *.aac *.ogg);;All Files (*)",
        )
        if path:
            self.audio_input.setText(path)
            if not self.output_input.text().strip():
                self.output_input.setText(str(Path(path).parent))

    def select_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "출력 폴더 선택", str(Path.home()))
        if path:
            self.output_input.setText(path)

    def select_summary_md(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Markdown 파일 선택",
            str(Path.home()),
            "Markdown Files (*.md);;Text Files (*.txt);;All Files (*)",
        )
        if path:
            self.summary_md_input.setText(path)
            if not self.summary_output_input.text().strip():
                self.summary_output_input.setText(str(Path(path).parent))

    def select_summary_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "요약 출력 폴더 선택", str(Path.home()))
        if path:
            self.summary_output_input.setText(path)

    def append_log(self, message: str):
        self.log_box.append(message)

    def validate_transcribe_config(self) -> Optional[TranscribeConfig]:
        audio_text = self.audio_input.text().strip()
        output_text = self.output_input.text().strip()

        if not audio_text:
            QMessageBox.warning(self, "오류", "오디오 파일을 선택하세요.")
            return None

        audio_path = Path(audio_text)
        if not audio_path.exists():
            QMessageBox.warning(self, "오류", f"오디오 파일이 없습니다:\n{audio_path}")
            return None

        output_txt = self.txt_check.isChecked()
        output_md = self.md_check.isChecked()
        output_srt = self.srt_check.isChecked()
        auto_summary = self.auto_summary_check.isChecked()

        if not (output_txt or output_md or output_srt):
            QMessageBox.warning(self, "오류", "출력 형식을 하나 이상 선택하세요.")
            return None

        if auto_summary and not output_md:
            QMessageBox.warning(self, "오류", "자동 요약을 사용하려면 Markdown 출력이 필요합니다.")
            return None

        output_path = Path(output_text) if output_text else audio_path.parent

        language = self.language_combo.currentText()
        if language == "auto":
            language = ""

        return TranscribeConfig(
            audio_path=audio_path,
            output_dir=output_path,
            model_name=self.model_combo.currentText(),
            device=self.device_combo.currentText(),
            compute_type=self.compute_combo.currentText(),
            language=language,
            beam_size=int(self.beam_combo.currentText()),
            vad_filter=self.vad_check.isChecked(),
            output_txt=output_txt,
            output_md=output_md,
            output_srt=output_srt,
            auto_summary=auto_summary,
            summary_model=self.summary_model_combo.currentText().strip(),
            summary_prompt=self.prompt_box.toPlainText().strip(),
            chunk_chars=self.chunk_spin.value(),
        )

    def validate_summary_config(self) -> Optional[SummaryConfig]:
        md_text = self.summary_md_input.text().strip()
        output_text = self.summary_output_input.text().strip()

        if not md_text:
            QMessageBox.warning(self, "오류", "요약할 Markdown 파일을 선택하세요.")
            return None

        md_path = Path(md_text)
        if not md_path.exists():
            QMessageBox.warning(self, "오류", f"Markdown 파일이 없습니다:\n{md_path}")
            return None

        output_path = Path(output_text) if output_text else md_path.parent
        model_name = self.summary_model_combo.currentText().strip()
        if not model_name:
            QMessageBox.warning(self, "오류", "요약 모델명을 입력하세요.")
            return None

        return SummaryConfig(
            md_path=md_path,
            output_dir=output_path,
            model_name=model_name,
            summary_prompt=self.prompt_box.toPlainText().strip() or default_summary_prompt(),
            chunk_chars=self.chunk_spin.value(),
        )

    def start_transcription(self):
        cfg = self.validate_transcribe_config()
        if cfg is None:
            return

        if cfg.auto_summary and not os.getenv("OPENAI_API_KEY"):
            QMessageBox.warning(
                self,
                "오류",
                "자동 요약을 사용하려면 OPENAI_API_KEY 환경변수가 필요합니다."
            )
            return

        self.progress_bar.setValue(0)
        self.log_box.clear()
        self.append_log("전사 작업을 시작합니다.")

        self.transcribe_worker = TranscribeWorker(cfg)
        self.transcribe_worker.log.connect(self.append_log)
        self.transcribe_worker.progress.connect(self.progress_bar.setValue)
        self.transcribe_worker.finished_ok.connect(self.on_transcribe_finished)
        self.transcribe_worker.failed.connect(self.on_failed)
        self.transcribe_worker.summary_requested.connect(self.start_summary_from_path)

        self.start_btn.setEnabled(False)
        self.cancel_transcribe_btn.setEnabled(True)
        self.transcribe_worker.start()

    def cancel_transcription(self):
        if self.transcribe_worker:
            self.transcribe_worker.request_cancel()
            self.append_log("전사 중단 요청을 보냈습니다.")
            self.cancel_transcribe_btn.setEnabled(False)

    def on_transcribe_finished(self, output_dir: str):
        self.append_log("전사 완료")
        self.append_log(f"결과 폴더: {output_dir}")
        self.start_btn.setEnabled(True)
        self.cancel_transcribe_btn.setEnabled(False)

    def start_summary_from_path(self, md_path: str):
        self.summary_md_input.setText(md_path)
        if not self.summary_output_input.text().strip():
            self.summary_output_input.setText(str(Path(md_path).parent))
        self.append_log("자동 요약을 시작합니다.")
        self.start_summary()

    def start_summary(self):
        cfg = self.validate_summary_config()
        if cfg is None:
            return

        if not os.getenv("OPENAI_API_KEY"):
            QMessageBox.warning(self, "오류", "OPENAI_API_KEY 환경변수가 설정되어 있지 않습니다.")
            return

        self.progress_bar.setValue(0)
        self.append_log("요약 작업을 시작합니다.")

        self.summary_worker = SummaryWorker(cfg)
        self.summary_worker.log.connect(self.append_log)
        self.summary_worker.progress.connect(self.progress_bar.setValue)
        self.summary_worker.finished_ok.connect(self.on_summary_finished)
        self.summary_worker.failed.connect(self.on_failed)

        self.summary_btn.setEnabled(False)
        self.cancel_summary_btn.setEnabled(True)
        self.summary_worker.start()

    def cancel_summary(self):
        if self.summary_worker:
            self.summary_worker.request_cancel()
            self.append_log("요약 중단 요청을 보냈습니다.")
            self.cancel_summary_btn.setEnabled(False)

    def on_summary_finished(self, out_path: str):
        self.append_log("요약 완료")
        self.append_log(f"요약 파일: {out_path}")
        self.summary_btn.setEnabled(True)
        self.cancel_summary_btn.setEnabled(False)
        QMessageBox.information(self, "완료", f"요약이 완료되었습니다.\n{out_path}")

    def on_failed(self, error: str):
        self.append_log("오류 발생")
        self.append_log(error)
        self.start_btn.setEnabled(True)
        self.summary_btn.setEnabled(True)
        self.cancel_transcribe_btn.setEnabled(False)
        self.cancel_summary_btn.setEnabled(False)
        QMessageBox.critical(self, "오류", error)


def main():
    app = QApplication(sys.argv)
    window = WhisperUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
