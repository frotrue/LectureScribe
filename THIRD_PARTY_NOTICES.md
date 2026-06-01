# Third-Party Notices

LectureScribe source code is licensed under the MIT License. Runtime dependencies and bundled binaries remain under their own licenses.

This document is a practical license notice for the dependencies used by the packaged Windows installer. It is not legal advice.

## Bundled Binaries

### FFmpeg and ffprobe

- Files: `bin/ffmpeg.exe`, `bin/ffprobe.exe`
- Build: `8.1.1-essentials_build-www.gyan.dev`
- License reported by bundled binaries: GNU General Public License v3 or later
- Verification commands: `ffmpeg.exe -L`, `ffprobe.exe -L`
- Upstream legal information: https://www.ffmpeg.org/legal.html
- Gyan.dev builds: https://www.gyan.dev/ffmpeg/builds/

The bundled binaries were built with `--enable-gpl --enable-version3`, so the bundled FFmpeg executables should be treated as GPLv3-or-later components.

## GUI Toolkit

### PySide6 / shiboken6

- Packages: `pyside6`, `pyside6-addons`, `pyside6-essentials`, `shiboken6`
- License metadata in installed wheels: `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`
- Qt licensing documentation: https://doc.qt.io/qt-6/licensing.html
- Qt for Python documentation: https://doc.qt.io/qtforpython/
- Qt LGPL obligations overview: https://www.qt.io/licensing/open-source-lgpl-obligations

The Windows installer bundles PySide6/Qt runtime files for convenience. Keep Qt/PySide license notices available when redistributing the installer.

## Core Python Dependencies

| Component | License | Notes |
| --- | --- | --- |
| `faster-whisper` | MIT | Local Whisper transcription wrapper |
| `ctranslate2` | MIT | Faster-Whisper inference backend |
| `openai` | Apache-2.0 | OpenAI API client |
| `onnxruntime` | MIT | Runtime dependency used by transcription stack |
| `tokenizers` | Apache-2.0 | Hugging Face tokenizer library |
| `huggingface-hub` | Apache-2.0 | Model download/cache helper |
| `numpy` | BSD-style | NumPy reports modified BSD terms in official docs |
| `tqdm` | MPL-2.0 AND MIT | Progress utility dependency |
| `pyyaml` | MIT | YAML utility dependency |
| `httpx` | BSD-3-Clause | HTTP client dependency |
| `pydantic` | MIT | Data validation dependency |
| `av` / PyAV | BSD-style | Python bindings for FFmpeg libraries |

For a complete transitive dependency list, inspect `uv.lock` and the package metadata installed in the active environment.
