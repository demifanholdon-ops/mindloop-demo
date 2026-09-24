#!/bin/zsh
set -e
cd "$(dirname "$0")"
export MINDLOOP_TRANSPORT=s3
exec ./run_demo.command
