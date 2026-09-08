"""Batch interface for shells, scripts and LLM agents. Does not import Qt."""
import argparse
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import signal
import sys
import time

from core import (
    AUDIO_EXTENSIONS, TranscribeConfig, SummaryConfig, TranscribeJob, SummaryJob,
    default_summary_prompt,
)


class UsageError(ValueError):
    pass


def parser():
    p = argparse.ArgumentParser(description='LectureScribe: 로컬 전사와 선택적 API 요약. GUI 없이 실행합니다.')
    sub = p.add_subparsers(dest='command', required=True)
    for name, help_text in [('transcribe', '파일 또는 폴더의 녹음을 일괄 전사'), ('summarize', 'TXT/Markdown 파일 또는 폴더를 일괄 요약')]:
        command = sub.add_parser(name, help=help_text)
        command.add_argument('inputs', nargs='+', type=Path, help='입력 파일 또는 폴더 (여러 개 가능)')
        command.add_argument('-o', '--output-dir', type=Path, help='출력 폴더. 생략하면 각 원본 옆에 저장')
        command.add_argument('-r', '--recursive', action='store_true', help='입력 폴더의 하위 폴더 포함')
        command.add_argument('--json', action='store_true', help='stdout에 JSON Lines 이벤트 출력 (schema_version=1)')
        command.add_argument('--verbose', action='store_true', help='상세 처리 로그도 출력')
        command.add_argument('--fail-fast', action='store_true', help='첫 실패 이후 나머지 파일을 처리하지 않음')
        command.add_argument('--dry-run', action='store_true', help='대상 파일과 설정만 확인. 다운로드·전사·API 호출 없음')
        command.add_argument('--summary-model', default='gpt-5.4-mini', help='OpenAI 요약 모델명')
        command.add_argument('--prompt-file', type=Path, help='기본 요약 지침 대신 사용할 UTF-8 파일')
        command.add_argument('--chunk-chars', type=int, default=30000, help='요약 분할 크기 (기본 30000자)')
        if name == 'transcribe':
            command.add_argument('--summary', choices=['on', 'off'], default='off', help='전사 후 API 요약 여부 (기본 off)')
            command.add_argument('--model', default='small', help='Whisper 모델명, Hugging Face 저장소 또는 로컬 모델 경로')
            command.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
            command.add_argument('--compute-type', choices=['int8', 'float32', 'float16', 'int8_float16'], help='기본값: CPU int8 / CUDA float16')
            command.add_argument('--language', default='ko', help='언어 코드 또는 auto (기본 ko)')
            command.add_argument('--beam-size', type=int, choices=[1, 3, 5], default=5)
            command.add_argument('--vad', choices=['on', 'off'], default='on')
            command.add_argument('--formats', default='txt,md,srt', help='쉼표로 구분: txt,md,srt. 요약 on이면 md 자동 포함')
    return p


class Reporter:
    def __init__(self, machine=False):
        self.machine = machine
        self.stream = sys.stdout

    def emit(self, event, **data):
        record = {'schema_version': 1, 'event': event, **data}
        if self.machine:
            print(json.dumps(record, ensure_ascii=False), file=self.stream, flush=True)
        elif event != 'progress':
            detail = data.get('message') or data.get('path') or data.get('input') or ''
            if event == 'batch_complete':
                detail = f"성공 {data['succeeded']} · 실패 {data['failed']} · 중단 {data['cancelled']} · 미처리 {data['unprocessed']}"
            print(f'[{event}] {detail}', file=self.stream, flush=True)


def discover(args):
    extensions = AUDIO_EXTENSIONS if args.command == 'transcribe' else {'.md', '.txt'}
    output = args.output_dir.expanduser().resolve() if args.output_dir else None
    if output and output.exists() and not output.is_dir():
        raise UsageError('출력 경로가 폴더가 아닙니다.')
    found = {}
    directory_count = sum(path.expanduser().is_dir() for path in args.inputs)
    for raw in args.inputs:
        source = raw.expanduser().resolve()
        if source.is_file():
            if source.suffix.lower() not in extensions:
                raise UsageError(f'지원하지 않는 입력 형식입니다: {source}')
            found.setdefault(source, output or source.parent)
        elif source.is_dir():
            candidates = source.rglob('*') if args.recursive else source.iterdir()
            for candidate in sorted(candidates):
                # Do not follow symlink inputs or re-ingest a separate output subtree.
                if candidate.is_symlink() or not candidate.is_file() or candidate.suffix.lower() not in extensions:
                    continue
                if output and output != source and output.is_relative_to(source) and candidate.is_relative_to(output):
                    continue
                # Directory summary does not summarize previous *_요약 outputs again.
                if args.command == 'summarize' and ('_요약' in candidate.stem):
                    continue
                destination = candidate.parent
                if output:
                    prefix = Path(source.name) if directory_count > 1 else Path()
                    destination = output / prefix / candidate.parent.relative_to(source)
                found.setdefault(candidate.resolve(), destination)
        else:
            raise UsageError(f'입력 경로가 존재하지 않습니다: {source}')
    if not found:
        raise UsageError('처리할 파일이 없습니다. 지원 형식과 --recursive 옵션을 확인하세요.')
    return list(found.items())


def validate(args):
    summary = args.command == 'summarize' or args.summary == 'on'
    if args.chunk_chars <= 0:
        raise UsageError('--chunk-chars는 양수여야 합니다.')
    if summary and not args.summary_model.strip():
        raise UsageError('요약 모델명을 입력해 주세요.')
    if summary and not args.dry_run and not os.getenv('OPENAI_API_KEY', '').strip():
        raise UsageError('요약에는 OPENAI_API_KEY 환경변수가 필요합니다. 전사만 하려면 --summary off를 사용하세요.')
    prompt = default_summary_prompt()
    if args.prompt_file:
        try:
            prompt = args.prompt_file.expanduser().read_text(encoding='utf-8').strip()
        except (OSError, UnicodeError) as error:
            raise UsageError(f'프롬프트 파일을 읽을 수 없습니다: {error}') from error
        if not prompt:
            raise UsageError('프롬프트 파일이 비어 있습니다.')
    formats = set()
    if args.command == 'transcribe':
        args.compute_type = args.compute_type or ('int8' if args.device == 'cpu' else 'float16')
        if args.device == 'cpu' and args.compute_type in {'float16', 'int8_float16'}:
            raise UsageError('CPU는 --compute-type int8 또는 float32를 사용하세요.')
        if not args.model.strip() or not args.language.strip():
            raise UsageError('모델과 언어는 비워 둘 수 없습니다.')
        formats = {part.strip().lower() for part in args.formats.split(',') if part.strip()}
        if not formats or not formats <= {'txt', 'md', 'srt'}:
            raise UsageError('--formats에는 txt,md,srt 중 하나 이상을 지정하세요.')
        if summary:
            formats.add('md')
    return summary, prompt, formats


class BatchRunner:
    def __init__(self, args, reporter):
        self.args = args
        self.reporter = reporter
        self.current = None
        self.interrupted = False
        self.model_cache = {}

    def interrupt(self, signum, frame):
        self.interrupted = True
        if self.current:
            self.current.request_cancel()

    def run_job(self, job, source, phase):
        self.current = job
        state = {'outputs': [], 'error': None, 'cancelled': False, 'completed': False}
        def artifact(path):
            state['outputs'].append(path)
            self.reporter.emit('file_saved', input=str(source), phase=phase, path=path)
        def failed(message):
            state['error'] = message
            self.reporter.emit('error', input=str(source), phase=phase, message=message)
        def cancelled():
            state['cancelled'] = True
        job.artifact_created.connect(artifact)
        job.failed.connect(failed)
        job.cancelled.connect(cancelled)
        job.finished_ok.connect(lambda _: state.update(completed=True))
        job.progress.connect(lambda value: self.reporter.emit('progress', input=str(source), phase=phase, percent=value))
        if self.args.verbose:
            job.log.connect(lambda message: self.reporter.emit('log', input=str(source), phase=phase, message=message))
        self.reporter.emit('phase_start', input=str(source), phase=phase)
        if self.interrupted:
            state['cancelled'] = True
            self.current = None
            return state
        try:
            # Dependencies may print progress. Keep stdout valid JSONL for agents.
            with redirect_stdout(sys.stderr):
                job.run()
        finally:
            self.current = None
        if not state['completed'] and not state['cancelled'] and not state['error']:
            state['error'] = '작업이 완료 상태를 반환하지 않았습니다.'
        return state

    def run(self, files, summary, prompt, formats):
        started = time.monotonic()
        self.reporter.emit('batch_start', total=len(files), command=self.args.command,
                           summary=summary, dry_run=self.args.dry_run, formats=sorted(formats))
        if self.args.dry_run:
            for source, output in files:
                self.reporter.emit('planned_file', input=str(source), output_dir=str(output))
            self.reporter.emit('batch_complete', total=len(files), succeeded=0, failed=0, cancelled=0,
                               unprocessed=len(files), planned=len(files), dry_run=True, exit_code=0)
            return 0
        succeeded = failed = cancelled = processed = 0
        for index, (source, output) in enumerate(files, start=1):
            if self.interrupted:
                break
            self.reporter.emit('file_start', index=index, total=len(files), input=str(source), output_dir=str(output))
            outputs = []
            if self.args.command == 'transcribe':
                cfg = TranscribeConfig(source, output, self.args.model, self.args.device, self.args.compute_type,
                                       '' if self.args.language == 'auto' else self.args.language, self.args.beam_size,
                                       self.args.vad == 'on', 'txt' in formats, 'md' in formats, 'srt' in formats,
                                       False, self.args.summary_model, prompt, self.args.chunk_chars)
                state = self.run_job(TranscribeJob(cfg, model_cache=self.model_cache), source, 'transcribe')
                outputs.extend(state['outputs'])
                if summary and state['completed'] and not state['error'] and not self.interrupted:
                    md = next(Path(path) for path in outputs if Path(path).suffix == '.md')
                    cfg = SummaryConfig(md, output, self.args.summary_model, prompt, self.args.chunk_chars)
                    state = self.run_job(SummaryJob(cfg), source, 'summarize')
                    outputs.extend(state['outputs'])
            else:
                cfg = SummaryConfig(source, output, self.args.summary_model, prompt, self.args.chunk_chars)
                state = self.run_job(SummaryJob(cfg), source, 'summarize')
                outputs.extend(state['outputs'])
            if state['cancelled'] or self.interrupted:
                status = 'cancelled'
                cancelled += 1
            elif state['error']:
                status = 'failed'
                failed += 1
            else:
                status = 'succeeded'
                succeeded += 1
            processed += 1
            self.reporter.emit('file_complete', input=str(source), status=status, outputs=outputs, error=state['error'])
            if status == 'cancelled' or (failed and self.args.fail_fast):
                break
        code = 130 if self.interrupted or cancelled else (1 if failed else 0)
        self.reporter.emit('batch_complete', total=len(files), succeeded=succeeded, failed=failed, cancelled=cancelled,
                           unprocessed=len(files) - processed, elapsed_seconds=round(time.monotonic() - started, 2), exit_code=code)
        return code


def main(argv=None):
    args = parser().parse_args(argv)
    reporter = Reporter(args.json)
    try:
        summary, prompt, formats = validate(args)
        files = discover(args)
    except UsageError as error:
        reporter.emit('error', message=str(error), exit_code=2)
        return 2
    runner = BatchRunner(args, reporter)
    previous = signal.signal(signal.SIGINT, runner.interrupt)
    try:
        return runner.run(files, summary, prompt, formats)
    finally:
        signal.signal(signal.SIGINT, previous)


if __name__ == '__main__':
    sys.exit(main())
