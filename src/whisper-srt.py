#!/usr/bin/env python3
"""whisper-srt <media> <lang|auto> <out.srt> [prompt] — subtítulos con faster-whisper (CUDA si hay GPU)."""
import os, sys

from faster_whisper import WhisperModel

media, lang, out = sys.argv[1:4]
prompt = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else None
model_name = os.environ.get('WHISPER_MODEL', 'large-v3-turbo')
cache = os.environ.get('WHISPER_CACHE', '/workspace/models/whisper')
try:
    model = WhisperModel(model_name, device='cuda', compute_type='float16', download_root=cache)
except Exception as e:  # no GPU or no CUDA libs: fall back so the command still works
    print(f'whisper-srt: sin CUDA ({e}); usando CPU int8', file=sys.stderr)
    model = WhisperModel(model_name, device='cpu', compute_type='int8', download_root=cache)

segments, _ = model.transcribe(media, language=None if lang == 'auto' else lang, initial_prompt=prompt, vad_filter=True)

def ts(t):
    ms = int(round(t * 1000))
    return f'{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}'

with open(out, 'w', encoding='utf-8') as f:
    for i, s in enumerate(segments, 1):
        f.write(f'{i}\n{ts(s.start)} --> {ts(s.end)}\n{s.text.strip()}\n\n')
