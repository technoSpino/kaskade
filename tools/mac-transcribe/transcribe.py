# #29: transcribe one clip with mlx Whisper large-v3-turbo over the whole file, no prompt, word timestamps.
# (v1 cut the audio into ~30 s chunks prompted with an ARD glossary: names came out right, but Whisper
# repeated the prompt as speech and dropped words at chunk edges. Names are respelled from ARD on the
# server instead.) Output: {model, version, language, segments: [{start, end, text, no_speech_prob,
# avg_logprob, words: [{w, s, e, p}]}]}, times in seconds of the clip.
# usage: python transcribe.py <audio> <out.json>
import json, sys, time
import mlx_whisper

src, out = sys.argv[1], sys.argv[2]
t0 = time.time()
r = mlx_whisper.transcribe(
    src,
    path_or_hf_repo="mlx-community/whisper-large-v3-turbo",
    language="de",
    word_timestamps=True,
    condition_on_previous_text=False,
    hallucination_silence_threshold=2.0,
)
segs = [{"start": s["start"], "end": s["end"], "text": s["text"].strip(),
         "no_speech_prob": round(s.get("no_speech_prob", 0), 3), "avg_logprob": round(s.get("avg_logprob", 0), 3),
         "words": [{"w": w["word"].strip(), "s": round(w["start"], 2), "e": round(w["end"], 2), "p": round(w.get("probability", 0), 3)}
                   for w in s.get("words", [])]}
        for s in r["segments"]]
json.dump({"model": "whisper-large-v3-turbo (mlx), whole file, no prompt", "version": 2, "language": "de", "segments": segs},
          open(out, "w"), ensure_ascii=False)
print(f"{src}: {len(segs)} segments in {time.time() - t0:.0f}s", file=sys.stderr)
