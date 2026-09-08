import os
import sys
import subprocess
from pathlib import Path
from typing import Optional


class NullTextStream:
    def write(self, text):
        return len(text) if text is not None else 0

    def flush(self):
        pass

    def isatty(self):
        return False


if sys.stdout is None:
    sys.stdout = NullTextStream()
if sys.stderr is None:
    sys.stderr = NullTextStream()


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

from PySide6.QtCore import QThread, Signal, Qt, QSettings, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut, QTextCursor
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
    QSpinBox, QScrollArea, QSplitter, QListWidget, QListWidgetItem, QPlainTextEdit,
    QAbstractItemView,

)


from core import TranscribeConfig, SummaryConfig, default_summary_prompt, TranscribeJob, SummaryJob


class JobWorker(QThread):
    log = Signal(str)
    progress = Signal(int)
    finished_ok = Signal(str)
    failed = Signal(str)
    cancelled = Signal()
    artifact_created = Signal(str)
    summary_requested = Signal(str)
    segment_ready = Signal(str)
    job_type = None

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.job = self.job_type(config)
        for name in ('log', 'progress', 'finished_ok', 'failed', 'cancelled',
                     'artifact_created', 'summary_requested', 'segment_ready'):
            getattr(self.job, name).connect(getattr(self, name).emit)

    @property
    def _cancel_requested(self):
        return self.job._cancel_requested

    def request_cancel(self):
        self.job.request_cancel()

    def run(self):
        self.job.run()


class TranscribeWorker(JobWorker):
    job_type = TranscribeJob


class SummaryWorker(JobWorker):
    job_type = SummaryJob


from ui_support import AUDIO_EXTENSIONS, STYLE, Disclosure, DropZone
import time


class WhisperUI(QWidget):
    def __init__(self, settings=None):
        super().__init__()
        self.settings = settings if settings is not None else QSettings('LectureScribe', 'LectureScribe')
        self.transcribe_worker = None
        self.summary_worker = None
        self.active_worker = None
        self.pending_summary = None
        self.run_config = None
        self.run_api_key = ''
        self.closing = False
        self.started_at = None
        self.setWindowTitle('LectureScribe — 강의를 나의 노트로')
        self.setObjectName('window')
        self.resize(1180, 820)
        self.setMinimumSize(880, 640)
        self.setStyleSheet(STYLE)
        self.build_ui()
        self.restore_settings()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_elapsed)
        self.timer.start(1000)
        QShortcut(QKeySequence('Ctrl+O'), self, activated=self.select_current_file)
        QShortcut(QKeySequence('Ctrl+Return'), self, activated=self.start_current)

    @staticmethod
    def label(text, name='muted'):
        label = QLabel(text)
        label.setObjectName(name)
        label.setWordWrap(True)
        return label

    @staticmethod
    def combo(items, value=None):
        combo = QComboBox()
        combo.addItems(items)
        if value:
            combo.setCurrentText(value)
        return combo

    @staticmethod
    def group(title):
        group = QGroupBox(title)
        form = QFormLayout(group)
        form.setSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        return group, form

    def path_row(self, placeholder, callback):
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        button = QPushButton('찾기…')
        button.clicked.connect(callback)
        row = QHBoxLayout()
        row.addWidget(edit, 1)
        row.addWidget(button)
        return edit, row

    def build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 20)
        root.setSpacing(14)
        header = QHBoxLayout()
        header.addWidget(self.label('LectureScribe', 'brand'))
        header.addStretch()
        header.addWidget(self.label('녹음에서 학습 노트까지'))
        root.addLayout(header)
        root.addWidget(self.label('강의를 담고, 읽고, 나의 노트로 정리하세요.'))
        self.splitter = QSplitter(Qt.Horizontal)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.build_transcribe_tab(), '01  강의 전사')
        self.tabs.addTab(self.build_summary_tab(), '02  노트 요약')
        self.splitter.addWidget(self.tabs)
        self.splitter.addWidget(self.build_results())
        self.splitter.setSizes([630, 450])
        self.splitter.setChildrenCollapsible(False)
        root.addWidget(self.splitter, 1)
        status_row = QHBoxLayout()
        self.status_label = self.label('준비됨 · 파일을 선택해 주세요.', 'status')
        self.elapsed_label = self.label('')
        status_row.addWidget(self.status_label, 1)
        status_row.addWidget(self.elapsed_label)
        root.addLayout(status_row)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        root.addWidget(self.progress_bar)

    @staticmethod
    def scroll(widget):
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(widget)
        return area

    def build_transcribe_tab(self):
        tab = QWidget()
        root = QVBoxLayout(tab)
        root.setContentsMargins(0, 0, 12, 0)
        root.setSpacing(12)
        self.audio_drop = DropZone(AUDIO_EXTENSIONS, '녹음 파일을 여기에 놓으세요',
                                   '오디오·동영상 한 개  ·  M4A, MP3, WAV, MP4 등', self.select_audio)
        self.audio_drop.file_selected.connect(self.set_audio)
        root.addWidget(self.audio_drop)
        file_group, form = self.group('입력과 저장 위치')
        self.audio_input, row = self.path_row('녹음 파일 경로', self.select_audio)
        form.addRow('강의 파일', row)
        self.output_input, row = self.path_row('비워 두면 원본 파일 옆에 저장', self.select_output_dir)
        form.addRow('저장 폴더', row)
        self.audio_input.textChanged.connect(lambda text: self.audio_drop.title.setText(Path(text).name if text else '녹음 파일을 여기에 놓으세요'))
        root.addWidget(file_group)

        options, form = self.group('전사 옵션')
        self.preset_combo = self.combo(['CPU · 빠르게', 'CPU · 정확하게', 'NVIDIA GPU · 균형', '직접 설정'])
        self.language_combo = QComboBox()
        for label, code in [('한국어', 'ko'), ('영어', 'en'), ('일본어', 'ja'), ('자동 감지', 'auto')]:
            self.language_combo.addItem(label, code)
        form.addRow('처리 방식', self.preset_combo)
        form.addRow('강의 언어', self.language_combo)
        self.preset_hint = self.label('CPU로 실행합니다. 첫 실행에는 모델 다운로드가 필요할 수 있어요.')
        form.addRow(self.preset_hint)
        advanced, advanced_form = self.group('세부 설정')
        self.model_combo = self.combo(['large-v3-turbo', 'large-v3', 'medium', 'small', 'base'], 'small')
        self.device_combo = self.combo(['cpu', 'cuda'])
        self.compute_combo = self.combo(['int8', 'float32', 'float16', 'int8_float16'])
        self.beam_combo = self.combo(['1', '3', '5'], '5')
        self.vad_check = QCheckBox('침묵 구간 건너뛰기 (VAD)')
        self.vad_check.setChecked(True)
        for label, widget in [('모델', self.model_combo), ('장치', self.device_combo), ('연산 정밀도', self.compute_combo), ('탐색 폭', self.beam_combo)]:
            advanced_form.addRow(label, widget)
            widget.currentTextChanged.connect(self.mark_custom)
        advanced_form.addRow(self.vad_check)
        self.advanced = Disclosure('고급 전사 설정', advanced)
        form.addRow(self.advanced)
        formats = QHBoxLayout()
        self.txt_check, self.md_check, self.srt_check = QCheckBox('TXT'), QCheckBox('Markdown'), QCheckBox('SRT 자막')
        for check in [self.txt_check, self.md_check, self.srt_check]:
            check.setChecked(True)
            formats.addWidget(check)
        form.addRow('저장 형식', formats)
        self.auto_summary_check = QCheckBox('완료 후 노트도 자동 요약')
        self.auto_summary_check.toggled.connect(self.toggle_auto_summary)
        form.addRow(self.auto_summary_check)
        form.addRow(self.label('전사는 로컬에서 처리됩니다. 요약은 OpenAI API로 텍스트를 전송하며 별도 요금이 발생합니다.'))
        root.addWidget(options)
        self.preset_combo.currentIndexChanged.connect(self.apply_preset)
        row = QHBoxLayout()
        self.start_btn = QPushButton('전사 시작')
        self.start_btn.setObjectName('primary')
        self.start_btn.clicked.connect(self.start_transcription)
        self.cancel_transcribe_btn = QPushButton('중단')
        self.cancel_transcribe_btn.clicked.connect(self.cancel_transcription)
        self.cancel_transcribe_btn.setEnabled(False)
        row.addWidget(self.start_btn, 1)
        row.addWidget(self.cancel_transcribe_btn)
        root.addStretch()
        self.transcribe_form = [self.audio_drop, file_group, options]
        return self.with_actions(tab, row)

    def build_summary_tab(self):
        tab = QWidget()
        root = QVBoxLayout(tab)
        root.setContentsMargins(0, 0, 12, 0)
        root.setSpacing(12)
        drop = DropZone({'.md', '.txt'}, '전사본을 학습 노트로', 'Markdown 또는 TXT 파일을 놓으세요.', self.select_summary_md)
        drop.file_selected.connect(self.set_summary_file)
        root.addWidget(drop)
        files, form = self.group('요약할 파일')
        self.summary_md_input, row = self.path_row('전사본 .md 또는 .txt', self.select_summary_md)
        form.addRow('전사본', row)
        self.summary_output_input, row = self.path_row('비워 두면 전사본 옆에 저장', self.select_summary_output_dir)
        form.addRow('저장 폴더', row)
        root.addWidget(files)
        api, form = self.group('요약 설정')
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText('환경변수 사용 중' if os.getenv('OPENAI_API_KEY') else 'API 키 입력 · 이번 실행 동안만 사용')
        form.addRow('OpenAI API 키', self.api_key_input)
        form.addRow(self.label('입력한 키는 저장하지 않습니다. OPENAI_API_KEY 환경변수도 사용할 수 있어요.'))
        self.summary_model_combo = self.combo(['gpt-5.4-mini', 'gpt-5.4-nano', 'gpt-5.5', 'gpt-5-mini', 'gpt-4.1-mini', 'gpt-4o-mini'])
        self.summary_model_combo.setEditable(True)
        form.addRow('요약 모델', self.summary_model_combo)
        advanced, advanced_form = self.group('요약 지침')
        self.chunk_spin = QSpinBox()
        self.chunk_spin.setRange(5000, 100000)
        self.chunk_spin.setSingleStep(5000)
        self.chunk_spin.setValue(30000)
        self.chunk_spin.setSuffix(' 자')
        advanced_form.addRow('분할 크기', self.chunk_spin)
        self.prompt_box = QTextEdit()
        self.prompt_box.setPlainText(default_summary_prompt())
        self.prompt_box.setMinimumHeight(200)
        advanced_form.addRow(self.prompt_box)
        reset = QPushButton('기본 지침 복원')
        reset.clicked.connect(lambda: self.prompt_box.setPlainText(default_summary_prompt()))
        advanced_form.addRow(reset)
        form.addRow(Disclosure('프롬프트·분할 크기', advanced))
        form.addRow(self.label('선택한 전사본이 OpenAI API로 전송됩니다. ChatGPT 구독과 별도로 과금됩니다.'))
        root.addWidget(api)
        row = QHBoxLayout()
        self.summary_btn = QPushButton('요약 시작')
        self.summary_btn.setObjectName('primary')
        self.summary_btn.clicked.connect(self.start_summary)
        self.cancel_summary_btn = QPushButton('중단')
        self.cancel_summary_btn.clicked.connect(self.cancel_summary)
        self.cancel_summary_btn.setEnabled(False)
        row.addWidget(self.summary_btn, 1)
        row.addWidget(self.cancel_summary_btn)
        root.addStretch()
        self.summary_form = [drop, files, api]
        return self.with_actions(tab, row)

    def with_actions(self, content, actions):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.addWidget(self.scroll(content), 1)
        layout.addLayout(actions)
        layout.addWidget(self.label('Ctrl+O 파일 선택   ·   Ctrl+Enter 시작'))
        return page

    def build_results(self):
        panel = QWidget()
        panel.setMinimumWidth(300)
        root = QVBoxLayout(panel)
        root.setContentsMargins(8, 8, 0, 0)
        root.addWidget(self.label('작업 결과', 'sectionTitle'))
        root.addWidget(self.label('전사 중에는 문장이, 완료 후에는 저장한 파일이 표시됩니다.'))
        self.result_tabs = QTabWidget()
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText('아직 전사한 내용이 없어요.\n\n왼쪽에서 강의 녹음 파일을 선택해 시작하세요.')
        self.preview.document().setMaximumBlockCount(5000)
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.document().setMaximumBlockCount(2000)
        self.result_tabs.addTab(self.preview, '미리보기')
        self.result_tabs.addTab(self.log_box, '작업 기록')
        root.addWidget(self.result_tabs, 1)
        self.copy_btn = QPushButton('내용 복사')
        self.copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.preview.toPlainText()))
        root.addWidget(self.copy_btn)
        root.addWidget(self.label('생성된 파일', 'status'))
        self.results = QListWidget()
        self.results.setMaximumHeight(135)
        self.results.setSelectionMode(QAbstractItemView.SingleSelection)
        self.results.currentItemChanged.connect(self.select_result)
        self.results.itemDoubleClicked.connect(lambda _: self.open_result())
        root.addWidget(self.results)
        row = QHBoxLayout()
        self.open_btn = QPushButton('파일 열기')
        self.folder_btn = QPushButton('폴더 열기')
        self.use_summary_btn = QPushButton('이 파일 요약')
        for button, slot in [(self.open_btn, self.open_result), (self.folder_btn, self.open_folder), (self.use_summary_btn, self.use_result_for_summary)]:
            button.setEnabled(False)
            button.clicked.connect(slot)
            row.addWidget(button)
        root.addLayout(row)
        return panel

    def mark_custom(self):
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentIndex(3)
        self.preset_combo.blockSignals(False)
        self.preset_hint.setText('직접 설정을 사용합니다. CPU에서는 int8 또는 float32를 선택하세요.')

    def apply_preset(self, index):
        presets = [('small', 'cpu', 'int8'), ('medium', 'cpu', 'int8'), ('large-v3-turbo', 'cuda', 'float16')]
        if index >= len(presets):
            self.advanced.button.setChecked(True)
            return
        for widget, value in zip([self.model_combo, self.device_combo, self.compute_combo], presets[index]):
            widget.blockSignals(True)
            widget.setCurrentText(value)
            widget.blockSignals(False)
        self.preset_hint.setText('NVIDIA GPU와 CUDA 실행 환경이 필요합니다.' if index == 2 else 'CPU로 실행합니다. 첫 실행에는 모델 다운로드가 필요할 수 있어요.')

    def toggle_auto_summary(self, checked):
        if checked:
            self.md_check.setChecked(True)
        self.md_check.setEnabled(not checked)

    def select_current_file(self):
        if not self.active_worker:
            (self.select_audio if self.tabs.currentIndex() == 0 else self.select_summary_md)()

    def start_current(self):
        if not self.active_worker:
            (self.start_transcription if self.tabs.currentIndex() == 0 else self.start_summary)()

    def set_audio(self, path):
        self.audio_input.setText(path)

    def set_summary_file(self, path):
        self.summary_md_input.setText(path)
        self.tabs.setCurrentIndex(1)

    def choose_file(self, title, filters, target):
        path, _ = QFileDialog.getOpenFileName(self, title, self.settings.value('last_dir', str(Path.home())), filters)
        if path:
            self.settings.setValue('last_dir', str(Path(path).parent))
            target(path)

    def select_audio(self):
        self.choose_file('강의 파일 선택', '미디어 파일 (*.m4a *.mp3 *.wav *.flac *.aac *.ogg *.opus *.mp4 *.webm);;모든 파일 (*)', self.set_audio)

    def select_summary_md(self):
        self.choose_file('전사본 선택', '전사본 (*.md *.txt);;모든 파일 (*)', self.set_summary_file)

    def choose_folder(self, edit):
        path = QFileDialog.getExistingDirectory(self, '저장 폴더 선택', edit.text() or str(Path.home()))
        if path:
            edit.setText(path)

    def select_output_dir(self):
        self.choose_folder(self.output_input)

    def select_summary_output_dir(self):
        self.choose_folder(self.summary_output_input)

    def append_log(self, message):
        self.log_box.appendPlainText(message)
        if self.active_worker and not self.closing and not self.active_worker._cancel_requested:
            self.status_label.setText(message)

    def warn(self, message):
        QMessageBox.warning(self, '설정을 확인해 주세요', message)

    def input_path(self, edit, description):
        raw = edit.text().strip()
        path = Path(raw).expanduser()
        if not raw or not path.is_file():
            self.warn(f'{description}을 선택해 주세요. 파일이 존재하는지 확인하세요.')
            return None
        return path

    def output_path(self, edit, source):
        path = Path(edit.text().strip()).expanduser() if edit.text().strip() else source.parent
        if path.exists() and not path.is_dir():
            self.warn('저장 위치가 파일입니다. 폴더를 선택해 주세요.')
            return None
        return path

    def api_key(self):
        return self.api_key_input.text().strip() or os.getenv('OPENAI_API_KEY', '')

    def validate_transcribe_config(self):
        source = self.input_path(self.audio_input, '강의 파일')
        if source is None:
            return None
        output = self.output_path(self.output_input, source)
        if output is None:
            return None
        if not any(c.isChecked() for c in [self.txt_check, self.md_check, self.srt_check]):
            self.warn('저장 형식을 하나 이상 선택해 주세요.')
            return None
        if self.device_combo.currentText() == 'cpu' and self.compute_combo.currentText() in ['float16', 'int8_float16']:
            self.warn('CPU에서는 int8 또는 float32 연산 정밀도를 선택해 주세요.')
            return None
        auto = self.auto_summary_check.isChecked()
        if auto and (not self.api_key() or not self.summary_model_combo.currentText().strip()):
            self.tabs.setCurrentIndex(1)
            self.warn('자동 요약을 사용하려면 요약 설정에서 API 키와 모델을 입력해 주세요.')
            return None
        language = self.language_combo.currentData()
        return TranscribeConfig(source, output, self.model_combo.currentText(), self.device_combo.currentText(),
                                self.compute_combo.currentText(), '' if language == 'auto' else language,
                                int(self.beam_combo.currentText()), self.vad_check.isChecked(), self.txt_check.isChecked(),
                                self.md_check.isChecked(), self.srt_check.isChecked(), auto,
                                self.summary_model_combo.currentText().strip(),
                                self.prompt_box.toPlainText().strip() or default_summary_prompt(), self.chunk_spin.value())

    def validate_summary_config(self):
        source = self.input_path(self.summary_md_input, '전사본 파일')
        if source is None:
            return None
        output = self.output_path(self.summary_output_input, source)
        if output is None:
            return None
        if not self.api_key() or not self.summary_model_combo.currentText().strip():
            self.warn('요약할 모델과 OpenAI API 키를 입력해 주세요.')
            return None
        return SummaryConfig(source, output, self.summary_model_combo.currentText().strip(),
                             self.prompt_box.toPlainText().strip() or default_summary_prompt(), self.chunk_spin.value(), self.api_key())

    def start_transcription(self):
        if self.active_worker:
            return
        config = self.validate_transcribe_config()
        if config is None:
            return
        self.run_config = config
        self.run_api_key = self.api_key() if config.auto_summary else ''
        self.pending_summary = None
        self.preview.clear()
        worker = TranscribeWorker(config)
        self.transcribe_worker = worker
        worker.segment_ready.connect(self.preview.appendPlainText)
        worker.summary_requested.connect(self.queue_summary)
        self.launch(worker, '전사')

    def start_summary(self):
        if self.active_worker:
            return
        config = self.validate_summary_config()
        if config is None:
            return
        self.summary_worker = SummaryWorker(config)
        self.launch(self.summary_worker, '요약')

    def launch(self, worker, kind):
        self.save_settings()
        self.active_worker = worker
        self.started_at = time.monotonic()
        self.progress_bar.setRange(0, 0)
        self.status_label.setText(f'{kind} 준비 중…')
        self.append_log(f'{kind} 작업을 시작합니다.')
        worker.log.connect(self.append_log)
        worker.progress.connect(self.on_progress)
        worker.artifact_created.connect(self.add_result)
        worker.finished_ok.connect(lambda _: self.complete(kind))
        worker.cancelled.connect(self.on_cancelled)
        worker.failed.connect(self.on_failed)
        worker.finished.connect(self.worker_finished)
        self.set_busy(True, kind)
        worker.start()

    def set_busy(self, busy, kind=''):
        for widget in self.transcribe_form + self.summary_form:
            widget.setEnabled(not busy)
        self.start_btn.setEnabled(not busy)
        self.summary_btn.setEnabled(not busy)
        self.cancel_transcribe_btn.setEnabled(busy and kind == '전사')
        self.cancel_summary_btn.setEnabled(busy and kind == '요약')
        self.use_summary_btn.setEnabled(not busy and self.selected_path() is not None and self.selected_path().suffix.lower() in {'.txt', '.md'})

    def on_progress(self, value):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(value)

    def update_elapsed(self):
        if self.started_at is not None:
            seconds = int(time.monotonic() - self.started_at)
            suffix = f'  ·  {self.progress_bar.value()}%' if self.progress_bar.maximum() else ''
            self.elapsed_label.setText(f'{seconds // 60:02}:{seconds % 60:02} 경과{suffix}')

    def complete(self, kind):
        self.status_label.setText(f'{kind} 완료 · 생성된 파일을 확인하세요.')
        self.log_box.appendPlainText(f'{kind} 완료')

    def queue_summary(self, path):
        if self.active_worker and not self.active_worker._cancel_requested and not self.closing:
            self.pending_summary = path

    def worker_finished(self):
        worker = self.active_worker
        self.active_worker = None
        self.update_elapsed()
        self.started_at = None
        if self.progress_bar.maximum() == 0:
            self.on_progress(0)
        self.set_busy(False)
        if worker is self.transcribe_worker:
            self.transcribe_worker = None
        if worker is self.summary_worker:
            self.summary_worker = None
        if worker:
            worker.deleteLater()
        if self.closing:
            self.run_api_key = ''
            self.close()
            return
        if self.pending_summary:
            path, self.pending_summary = self.pending_summary, None
            cfg = self.run_config
            self.set_summary_file(path)
            # Automatic summary uses the immutable transcription job settings.
            config = SummaryConfig(Path(path), cfg.output_dir, cfg.summary_model, cfg.summary_prompt, cfg.chunk_chars, self.run_api_key)
            self.run_api_key = ''
            self.summary_worker = SummaryWorker(config)
            self.launch(self.summary_worker, '요약')
        else:
            self.run_api_key = ''

    def cancel_transcription(self):
        self.cancel_active()

    def cancel_summary(self):
        self.cancel_active()

    def cancel_active(self):
        if self.active_worker:
            self.pending_summary = None
            self.active_worker.request_cancel()
            self.cancel_transcribe_btn.setEnabled(False)
            self.cancel_summary_btn.setEnabled(False)
            self.status_label.setText('중단 요청됨 · 현재 처리 구간이 끝나면 멈춥니다.')
            self.log_box.appendPlainText('중단 요청을 보냈습니다. 모델 로딩이나 API 응답을 기다리는 동안에는 시간이 걸릴 수 있습니다.')

    def on_cancelled(self):
        self.pending_summary = None
        self.status_label.setText('중단됨 · 일부 전사 결과는 “부분” 파일로 저장됩니다.')
        self.log_box.appendPlainText('작업이 중단되었습니다.')

    def on_failed(self, error):
        self.pending_summary = None
        self.status_label.setText('작업 실패 · 작업 기록에서 원인을 확인하세요.')
        self.log_box.appendPlainText(error)
        self.result_tabs.setCurrentIndex(1)
        if not self.closing:
            QMessageBox.critical(self, '작업을 완료하지 못했어요', error)

    def add_result(self, path):
        item = QListWidgetItem(Path(path).name)
        item.setData(Qt.UserRole, path)
        item.setToolTip(path)
        self.results.insertItem(0, item)
        self.results.setCurrentItem(item)

    def selected_path(self):
        item = self.results.currentItem()
        return Path(item.data(Qt.UserRole)) if item else None

    def select_result(self, current, previous=None):
        path = self.selected_path()
        self.open_btn.setEnabled(path is not None)
        self.folder_btn.setEnabled(path is not None)
        self.use_summary_btn.setEnabled(path is not None and path.suffix.lower() in {'.md', '.txt'} and not self.active_worker)
        if path:
            try:
                # Keep large lecture files from blocking the UI. Opening uses the complete file.
                with path.open(encoding='utf-8') as stream:
                    text = stream.read(200001)
                self.preview.setPlainText(text[:200000] + ('\n\n[미리보기 생략 · 전체 내용은 파일 열기]' if len(text) > 200000 else ''))
                self.result_tabs.setCurrentIndex(0)
            except (OSError, UnicodeError) as error:
                self.log_box.appendPlainText(f'미리보기를 열지 못했습니다: {error}')

    def open_result(self):
        self.open_path(self.selected_path())

    def open_folder(self):
        path = self.selected_path()
        if path:
            self.open_path(path.parent)

    def open_path(self, path):
        if path:
            if not path.exists():
                self.warn('파일 또는 폴더가 이동되었거나 삭제되었습니다.')
            elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
                self.warn('연결된 앱으로 열지 못했습니다. 작업 기록의 저장 경로를 확인해 주세요.')

    def use_result_for_summary(self):
        path = self.selected_path()
        if path and not self.active_worker:
            self.set_summary_file(str(path))

    def preference_widgets(self):
        return ['model_combo', 'device_combo', 'compute_combo', 'beam_combo', 'summary_model_combo',
                'vad_check', 'txt_check', 'md_check', 'srt_check', 'auto_summary_check',
                'output_input', 'summary_output_input', 'chunk_spin', 'prompt_box']

    def save_settings(self):
        for name in self.preference_widgets():
            widget = getattr(self, name)
            if isinstance(widget, QComboBox):
                value = widget.currentText()
            elif isinstance(widget, QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, QSpinBox):
                value = widget.value()
            elif isinstance(widget, QTextEdit):
                value = widget.toPlainText()
            else:
                value = widget.text()
            self.settings.setValue(name, value)
        self.settings.setValue('language', self.language_combo.currentData())
        self.settings.setValue('preset', self.preset_combo.currentIndex())
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('splitter', self.splitter.saveState())
        self.settings.sync()

    def restore_settings(self):
        for name in self.preference_widgets():
            if not self.settings.contains(name):
                continue
            widget = getattr(self, name)
            value = self.settings.value(name)
            if isinstance(widget, QComboBox):
                widget.setCurrentText(str(value))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(str(value).lower() in ['true', '1'])
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(value))
            elif isinstance(widget, QTextEdit):
                widget.setPlainText(str(value))
            else:
                widget.setText(str(value))
        index = self.language_combo.findData(self.settings.value('language', 'ko'))
        self.language_combo.setCurrentIndex(max(0, index))
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentIndex(int(self.settings.value('preset', 0)))
        self.preset_combo.blockSignals(False)
        if self.preset_combo.currentIndex() < 3:
            self.apply_preset(self.preset_combo.currentIndex())
        self.toggle_auto_summary(self.auto_summary_check.isChecked())
        for key, restore in [('geometry', self.restoreGeometry), ('splitter', self.splitter.restoreState)]:
            if self.settings.contains(key):
                restore(self.settings.value(key))

    def closeEvent(self, event):
        if self.active_worker:
            if not self.closing:
                answer = QMessageBox.question(self, '작업을 중단하고 종료할까요?',
                                              '진행 중인 작업에 중단을 요청하고 안전하게 끝난 뒤 종료합니다.',
                                              QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if answer == QMessageBox.Yes:
                    self.closing = True
                    self.cancel_active()
            event.ignore()
            return
        self.save_settings()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = WhisperUI()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
