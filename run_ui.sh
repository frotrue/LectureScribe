#!/usr/bin/env bash
set -e

cd /mnt/c/Users/user/Desktop/projects/whisper-local

CUBLAS_DIR=$(find .venv -name "libcublas.so.12" -type f | head -n 1 | xargs dirname)
CUDNN_DIR=$(find .venv -name "libcudnn.so.9" -type f | head -n 1 | xargs dirname)

if [ -z "$CUBLAS_DIR" ]; then
  echo "libcublas.so.12를 찾지 못했습니다."
  echo "uv pip install nvidia-cublas-cu12 를 먼저 실행하세요."
  exit 1
fi

if [ -z "$CUDNN_DIR" ]; then
  echo "libcudnn.so.9를 찾지 못했습니다."
  echo "uv pip install nvidia-cudnn-cu12==9.* 를 먼저 실행하세요."
  exit 1
fi

export LD_LIBRARY_PATH="$CUBLAS_DIR:$CUDNN_DIR:$LD_LIBRARY_PATH"

echo "CUBLAS_DIR=$CUBLAS_DIR"
echo "CUDNN_DIR=$CUDNN_DIR"
echo "LD_LIBRARY_PATH=$LD_LIBRARY_PATH"

uv run python main.py
