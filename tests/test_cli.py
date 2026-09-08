"""Headless CLI tests; no Qt, model download or paid API calls."""
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cli
import core


@pytest.fixture
def fake_backend(monkeypatch):
    def transcribe(path, **kwargs):
        return iter([SimpleNamespace(start=0, end=1, text='강의 전사')]), SimpleNamespace(language='ko', language_probability=1.0)
    factory = Mock(return_value=SimpleNamespace(transcribe=transcribe))
    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=factory))
    monkeypatch.setattr(core, 'materialize_faster_whisper_model', lambda *a: 'fake')
    monkeypatch.setattr(core, 'get_audio_duration_seconds', lambda *a: 1)
    return factory


def records(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


def touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


def test_cli_import_and_help_without_qt():
    result = subprocess.run([sys.executable, '-c', "import cli,sys; assert not any(m.startswith('PySide6') for m in sys.modules); cli.parser().parse_args(['--help'])"],
                            cwd=Path(cli.__file__).parent, capture_output=True, text=True)
    assert result.returncode == 0
    assert 'transcribe' in result.stdout and 'summarize' in result.stdout


def test_recursive_dry_run_excludes_output_and_unsupported(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    touch(tmp_path / 'a.MP3')
    touch(tmp_path / 'nested' / 'b.wav')
    touch(tmp_path / 'readme.txt')
    output = tmp_path / 'out'
    touch(output / 'old.mp3')
    assert cli.main(['transcribe', str(tmp_path), '-r', '-o', str(output), '--summary', 'on', '--dry-run', '--json']) == 0
    events = records(capsys)
    planned = [r for r in events if r['event'] == 'planned_file']
    assert len(planned) == 2
    assert planned[1]['output_dir'] == str(output / 'nested')
    assert events[-1]['dry_run'] is True
    assert not (output / 'nested').exists()


def test_batch_outputs_reuses_model_and_defaults_no_summary(tmp_path, capsys, monkeypatch, fake_backend):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    root = tmp_path / 'input'
    touch(root / 'a.wav')
    touch(root / 'b.mp3')
    out = tmp_path / 'out'
    assert cli.main(['transcribe', str(root), '-o', str(out), '--json']) == 0
    events = records(capsys)
    assert events[-1]['succeeded'] == 2
    assert events[-1]['failed'] == 0
    assert len(list(out.iterdir())) == 6
    assert fake_backend.call_count == 1
    assert not any(event.get('phase') == 'summarize' for event in events)
    assert all(event['schema_version'] == 1 for event in events)


def test_summary_on_adds_markdown_and_saves_summary(tmp_path, capsys, monkeypatch, fake_backend):
    source = touch(tmp_path / 'a.wav')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    create = Mock(return_value=SimpleNamespace(output_text='# 요약\n내용'))
    monkeypatch.setitem(sys.modules, 'openai', SimpleNamespace(OpenAI=Mock(return_value=SimpleNamespace(responses=SimpleNamespace(create=create)))))
    assert cli.main(['transcribe', str(source), '--formats', 'txt', '--summary', 'on', '--json']) == 0
    events = records(capsys)
    assert set(events[0]['formats']) == {'txt', 'md'}
    assert (tmp_path / 'a_요약.md').is_file()
    complete = next(e for e in events if e['event'] == 'file_complete')
    assert len(complete['outputs']) == 3
    assert create.call_count == 1


def test_missing_api_key_fails_before_transcription(tmp_path, capsys, monkeypatch, fake_backend):
    source = touch(tmp_path / 'a.wav')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    assert cli.main(['transcribe', str(source), '--summary', 'on', '--json']) == 2
    assert records(capsys)[0]['exit_code'] == 2
    fake_backend.assert_not_called()
    assert list(tmp_path.glob('*원본*')) == []


@pytest.mark.parametrize('extra', [[], ['--fail-fast']])
def test_failure_exit_status_and_continue_behavior(tmp_path, capsys, monkeypatch, fake_backend, extra):
    touch(tmp_path / 'a.wav')
    touch(tmp_path / 'b.wav')
    def fail(path, **kwargs):
        if Path(path).name == 'a.wav':
            raise RuntimeError('broken audio')
        return iter([]), SimpleNamespace(language='ko', language_probability=1.0)
    fake_backend.return_value.transcribe = fail
    assert cli.main(['transcribe', str(tmp_path), '--json', *extra]) == 1
    events = records(capsys)
    assert events[-1]['failed'] == 1
    assert events[-1]['succeeded'] == (0 if extra else 1)
    assert events[-1]['unprocessed'] == (1 if extra else 0)


def test_json_stdout_is_not_polluted_by_dependency_prints(tmp_path, capsys, monkeypatch, fake_backend):
    source = touch(tmp_path / 'a.wav')
    def loader(*args):
        print('dependency progress')
        return 'fake'
    monkeypatch.setattr(core, 'materialize_faster_whisper_model', loader)
    assert cli.main(['transcribe', str(source), '--json']) == 0
    captured = capsys.readouterr()
    assert 'dependency progress' in captured.err
    assert all(json.loads(line) for line in captured.out.splitlines())


def test_interrupt_stops_batch_and_retains_partial_output(tmp_path, capsys, monkeypatch, fake_backend):
    import signal
    touch(tmp_path / 'a.wav')
    touch(tmp_path / 'b.wav')
    def transcribe(path, **kwargs):
        def segments():
            yield SimpleNamespace(start=0, end=1, text='partial')
            signal.raise_signal(signal.SIGINT)
            yield SimpleNamespace(start=1, end=2, text='unprocessed')
        return segments(), SimpleNamespace(language='ko', language_probability=1.0)
    fake_backend.return_value.transcribe = transcribe
    assert cli.main(['transcribe', str(tmp_path), '--json']) == 130
    events = records(capsys)
    assert events[-1]['cancelled'] == 1 and events[-1]['unprocessed'] == 1
    assert list(tmp_path.glob('a_부분_원본*'))
    assert not list(tmp_path.glob('b_원본*'))


def test_no_input_is_usage_error(tmp_path, capsys):
    assert cli.main(['transcribe', str(tmp_path), '--json']) == 2
    assert records(capsys)[0]['event'] == 'error'


def test_duplicate_inputs_are_processed_once(tmp_path, capsys, fake_backend):
    source = touch(tmp_path / 'a.wav')
    assert cli.main(['transcribe', str(source), str(tmp_path), '--json']) == 0
    assert records(capsys)[-1]['total'] == 1


def test_summarize_directory_skips_generated_summaries(tmp_path, capsys, monkeypatch):
    (tmp_path / 'lecture.md').write_text('source', encoding='utf-8')
    (tmp_path / 'lecture_요약.md').write_text('old summary', encoding='utf-8')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setitem(sys.modules, 'openai', SimpleNamespace(OpenAI=lambda **k: SimpleNamespace(responses=SimpleNamespace(create=lambda **k: SimpleNamespace(output_text='new summary')))))
    assert cli.main(['summarize', str(tmp_path), '--json']) == 0
    assert records(capsys)[-1]['total'] == 1
    assert (tmp_path / 'lecture_요약_1.md').read_text() == 'new summary'


def test_cpu_invalid_precision_is_usage_error(tmp_path, capsys):
    source = touch(tmp_path / 'a.wav')
    assert cli.main(['transcribe', str(source), '--compute-type', 'float16', '--json']) == 2
    assert records(capsys)[0]['exit_code'] == 2


def test_summary_failure_keeps_transcripts(tmp_path, capsys, monkeypatch, fake_backend):
    source = touch(tmp_path / 'a.wav')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setitem(sys.modules, 'openai', SimpleNamespace(OpenAI=Mock(side_effect=RuntimeError('API unavailable'))))
    assert cli.main(['transcribe', str(source), '--summary', 'on', '--json']) == 1
    events = records(capsys)
    complete = next(event for event in events if event['event'] == 'file_complete')
    assert complete['status'] == 'failed' and len(complete['outputs']) == 3
    assert all(Path(path).is_file() for path in complete['outputs'])
