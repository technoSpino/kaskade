#!/bin/sh
# #29: transcribe Kaskade clips on Matt's Mac (Apple silicon, mlx Whisper large-v3-turbo) and upload
# the word-timed JSON to the server's ~/kaskade-data/transcripts/. The server has no GPU and too little RAM.
#   one-time: uv tool install mlx-whisper
#   usage:    tools/mac-transcribe/run.sh 2 3 4      (media ids; skips ids whose transcript exists)
# Transcripts are third-party content: never commit them (TASK.md rule 1).
set -u
cd "$(dirname "$0")"
PY=$(uv tool dir)/mlx-whisper/bin/python
H=kaskade@100.64.43.3
W=${TMPDIR:-/tmp}/kaskade-transcribe
mkdir -p "$W"
ssh $H 'mkdir -p ~/kaskade-data/transcripts'
for id in "$@"; do
  f=$(ssh $H "sqlite3 ~/kaskade-data/kaskade.db 'select media_file from media where id=$id'")
  [ -n "$f" ] || { echo "no media $id"; continue; }
  stem=${f%.*}
  ssh $H "test -s ~/kaskade-data/transcripts/$stem.whisper.json" && { echo "skip $id $stem (exists)"; continue; }
  ssh $H "nice -n 19 ffmpeg -v error -threads 1 -i ~/kaskade-data/media/$f -vn -ac 1 -ar 16000 -c:a libopus -b:a 48k -f ogg -" > "$W/$stem.ogg" \
    || { echo "audio failed $id"; continue; }
  "$PY" transcribe.py "$W/$stem.ogg" "$W/$stem.whisper.json" || { echo "asr failed $id"; continue; }
  scp -q "$W/$stem.whisper.json" "$H:kaskade-data/transcripts/" && echo "done $id $stem"
done
