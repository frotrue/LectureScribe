"""Offline regression tests: Qt widgets and real workers with fake inference/API."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from PySide6.QtCore import QSettings, QMimeData, QUrl
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
import core
from ui_support import AUDIO_EXTENSIONS, DropZone


@pytest.fixture(scope='session')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.setattr(QMessageBox, 'warning', Mock())
    monkeypatch.setattr(QMessageBox, 'critical', Mock())
    w = main.WhisperUI(QSettings(str(tmp_path / 'prefs.ini'), QSettings.IniFormat))
    yield w
    if w.active_worker:
        w.active_worker.request_cancel()
        w.active_worker.wait(5000)
        app.processEvents()
    w.close()


def config(tmp_path, **kwargs):
    args = dict(audio_path=tmp_path / 'lecture.wav', output_dir=tmp_path, model_name='small', device='cpu',
                compute_type='int8', language='ko', beam_size=5, vad_filter=True,
                output_txt=True, output_md=True, output_srt=True, auto_summary=False,
                summary_model='test-model', summary_prompt='test prompt', chunk_chars=5000)
    args.update(kwargs)
    return main.TranscribeConfig(**args)


def fake_transcription(monkeypatch, segments):
    model = Mock()
    model.transcribe.return_value = (segments, SimpleNamespace(language='ko', language_probability=1.0))
    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=Mock(return_value=model)))
    monkeypatch.setattr(core, 'materialize_faster_whisper_model', lambda *a: 'fake-model')
    monkeypatch.setattr(core, 'get_audio_duration_seconds', lambda *a: 20)
    return model


def fake_api(monkeypatch, respond):
    create = Mock(side_effect=respond)
    factory = Mock(return_value=SimpleNamespace(responses=SimpleNamespace(create=create)))
    monkeypatch.setitem(sys.modules, 'openai', SimpleNamespace(OpenAI=factory))
    return factory, create


def summary_config(tmp_path, text='강의 내용'):
    path = tmp_path / 'lecture.md'
    path.write_text(text, encoding='utf-8')
    return main.SummaryConfig(path, tmp_path, 'test-model', 'prompt', 5000, 'test-session-key')


def wait_idle(app, window):
    for _ in range(200):
        app.processEvents()
        if window.active_worker is None:
            return
        QTest.qWait(10)
    pytest.fail('Worker did not return to idle')


def test_preferences_round_trip_without_api_key(window, app):
    window.preset_combo.setCurrentIndex(2)
    window.language_combo.setCurrentIndex(1)
    window.srt_check.setChecked(False)
    window.prompt_box.setPlainText('custom instructions')
    window.api_key_input.setText('must-not-be-persisted')
    window.save_settings()
    restored = main.WhisperUI(window.settings)
    assert restored.device_combo.currentText() == 'cuda'
    assert restored.compute_combo.currentText() == 'float16'
    assert restored.language_combo.currentData() == 'en'
    assert not restored.srt_check.isChecked()
    assert restored.prompt_box.toPlainText() == 'custom instructions'
    assert restored.api_key_input.text() == ''
    assert 'must-not-be-persisted' not in Path(window.settings.fileName()).read_text()
    restored.close()


def test_auto_summary_enables_markdown(window):
    window.md_check.setChecked(False)
    window.auto_summary_check.setChecked(True)
    assert window.md_check.isChecked() and not window.md_check.isEnabled()
    window.auto_summary_check.setChecked(False)
    assert window.md_check.isEnabled()


def test_validation_file_outputs_and_cpu_precision(window, tmp_path):
    window.audio_input.setText(str(tmp_path))
    assert window.validate_transcribe_config() is None
    audio = tmp_path / 'lecture.wav'
    audio.touch()
    window.audio_input.setText(str(audio))
    cfg = window.validate_transcribe_config()
    assert cfg is not None and cfg.output_dir == tmp_path
    window.compute_combo.setCurrentText('float16')
    assert window.validate_transcribe_config() is None
    window.compute_combo.setCurrentText('int8')
    for check in [window.txt_check, window.md_check, window.srt_check]:
        check.setChecked(False)
    assert window.validate_transcribe_config() is None


def test_drop_accepts_single_local_supported_file(app, tmp_path):
    zone = DropZone(AUDIO_EXTENSIONS, 'title', 'detail', lambda: None)
    audio = tmp_path / '녹음.M4A'
    audio.touch()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(audio))])
    assert zone.local_file(mime) == str(audio)
    mime.setUrls([QUrl('https://example.com/recording.mp3')])
    assert zone.local_file(mime) is None
    mime.setUrls([QUrl.fromLocalFile(str(audio))] * 2)
    assert zone.local_file(mime) is None


def test_transcribe_outputs_preview_and_duplicate_protection(app, tmp_path, monkeypatch):
    segments = [SimpleNamespace(start=0, end=2, text=' 첫 문장 ')]
    fake_transcription(monkeypatch, segments)
    worker = main.TranscribeWorker(config(tmp_path))
    artifacts, preview, complete = [], [], []
    worker.artifact_created.connect(artifacts.append)
    worker.segment_ready.connect(preview.append)
    worker.finished_ok.connect(complete.append)
    worker.run()
    worker.run()
    assert len(artifacts) == 6 and len(set(artifacts)) == 6
    assert all(Path(p).is_file() for p in artifacts)
    assert preview[0] == '[00:00] 첫 문장'
    assert len(complete) == 2


def test_cancel_saves_partial_and_does_not_request_summary(app, tmp_path, monkeypatch):
    worker = main.TranscribeWorker(config(tmp_path, auto_summary=True))
    def segments():
        yield SimpleNamespace(start=0, end=2, text='첫 구간')
        worker.request_cancel()
        yield SimpleNamespace(start=2, end=3, text='미완료 구간')
    fake_transcription(monkeypatch, segments())
    done, cancelled, summaries, artifacts = [], [], [], []
    worker.finished_ok.connect(done.append)
    worker.cancelled.connect(lambda: cancelled.append(True))
    worker.summary_requested.connect(summaries.append)
    worker.artifact_created.connect(artifacts.append)
    worker.run()
    assert cancelled and not done and not summaries
    assert len(artifacts) == 3
    assert all('_부분_원본' in p for p in artifacts)
    assert '미완료 구간' not in Path(artifacts[0]).read_text()


def test_summary_cancel_after_request_does_not_save_or_merge(app, tmp_path, monkeypatch):
    worker = main.SummaryWorker(summary_config(tmp_path))
    def respond(**kwargs):
        worker.request_cancel()
        return SimpleNamespace(output_text='ignored')
    factory, create = fake_api(monkeypatch, respond)
    cancelled, complete = [], []
    worker.cancelled.connect(lambda: cancelled.append(True))
    worker.finished_ok.connect(complete.append)
    worker.run()
    assert cancelled and not complete
    assert create.call_count == 1
    assert not list(tmp_path.glob('*요약*'))
    assert factory.call_args.kwargs['api_key'] == 'test-session-key'


def test_empty_summary_never_calls_api(app, tmp_path, monkeypatch):
    factory, create = fake_api(monkeypatch, lambda **k: None)
    worker = main.SummaryWorker(summary_config(tmp_path, '   '))
    errors = []
    worker.failed.connect(errors.append)
    worker.run()
    assert errors and '내용이 없습니다' in errors[0]
    factory.assert_not_called()


def test_summary_cancel_restores_controls(window, app, tmp_path, monkeypatch):
    cfg = summary_config(tmp_path)
    window.summary_md_input.setText(str(cfg.md_path))
    window.api_key_input.setText('test-key')
    fake_api(monkeypatch, lambda **k: SimpleNamespace(output_text='result'))
    window.start_summary()
    assert not window.start_btn.isEnabled() and not window.summary_btn.isEnabled()
    worker = window.active_worker
    window.start_summary()
    assert window.active_worker is worker
    window.cancel_summary()
    wait_idle(app, window)
    assert window.start_btn.isEnabled() and window.summary_btn.isEnabled()
    assert not window.cancel_summary_btn.isEnabled()
    assert '중단됨' in window.status_label.text()


def test_auto_summary_handoff_uses_job_output_and_settings(window, app, tmp_path, monkeypatch):
    source = tmp_path / 'lecture.wav'
    source.touch()
    window.audio_input.setText(str(source))
    window.api_key_input.setText('job-key')
    window.auto_summary_check.setChecked(True)
    window.summary_output_input.setText(str(tmp_path / 'unrelated'))
    window.summary_model_combo.setCurrentText('job-model')
    fake_transcription(monkeypatch, [SimpleNamespace(start=0, end=2, text='강의')])
    factory, create = fake_api(monkeypatch, lambda **k: SimpleNamespace(output_text='# 요약\n강의 노트'))
    window.start_transcription()
    wait_idle(app, window)
    assert create.call_args.kwargs['model'] == 'job-model'
    assert (tmp_path / 'lecture_요약.md').is_file()
    assert not (tmp_path / 'unrelated').exists()
    assert window.results.count() == 4
    assert '요약 완료' in window.status_label.text()
    assert window.start_btn.isEnabled()


def test_failure_restores_controls(window, app, tmp_path, monkeypatch):
    source = tmp_path / 'lecture.wav'
    source.touch()
    window.audio_input.setText(str(source))
    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=Mock(side_effect=RuntimeError('model unavailable'))))
    monkeypatch.setattr(core, 'materialize_faster_whisper_model', lambda *a: 'fake')
    monkeypatch.setattr(core, 'get_audio_duration_seconds', lambda *a: 20)
    window.start_transcription()
    wait_idle(app, window)
    assert window.start_btn.isEnabled() and window.summary_btn.isEnabled()
    assert '실패' in window.status_label.text()
    assert window.result_tabs.currentIndex() == 1


def test_result_preview_uses_plain_text(window, tmp_path):
    path = tmp_path / 'lecture.txt'
    path.write_text('<b>literal text</b>', encoding='utf-8')
    window.add_result(str(path))
    assert window.preview.toPlainText() == '<b>literal text</b>'
    assert window.use_summary_btn.isEnabled()
    window.use_result_for_summary()
    assert window.summary_md_input.text() == str(path)
    assert window.tabs.currentIndex() == 1


def test_close_waits_for_active_worker(window, app, tmp_path, monkeypatch):
    import threading
    entered, release = threading.Event(), threading.Event()
    cfg = summary_config(tmp_path)
    window.summary_md_input.setText(str(cfg.md_path))
    window.api_key_input.setText('test-key')
    def respond(**kwargs):
        entered.set()
        release.wait(3)
        return SimpleNamespace(output_text='cancelled response')
    fake_api(monkeypatch, respond)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Yes)
    window.show()
    window.start_summary()
    assert entered.wait(2)
    window.close()
    assert window.closing and window.isVisible()
    release.set()
    wait_idle(app, window)
    assert not window.isVisible()
    assert not list(tmp_path.glob('*요약*'))


def test_cancel_prevents_queued_auto_summary(window):
    worker = main.TranscribeWorker(config(Path('/tmp')))
    window.active_worker = worker
    window.cancel_active()
    window.queue_summary('/tmp/lecture.md')
    assert window.pending_summary is None
    window.active_worker = None
