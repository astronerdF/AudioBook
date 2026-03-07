"""
Lightweight TTS server for Chrome Reader extension.
Uses Kokoro TTS for fast text-to-speech with word-level timing estimates.
"""

import asyncio
import base64
import io
import json
import logging
import os
import re
import time
from typing import Optional

import torch
import torchaudio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tts-server")

app = FastAPI(title="Chrome Reader TTS Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

VOICES = [
    {"id": "af_heart", "name": "Heart", "gender": "female", "accent": "american"},
    {"id": "af_bella", "name": "Bella", "gender": "female", "accent": "american"},
    {"id": "am_fenrir", "name": "Fenrir", "gender": "male", "accent": "american"},
    {"id": "bf_emma", "name": "Emma", "gender": "female", "accent": "british"},
    {"id": "bm_fable", "name": "Fable", "gender": "male", "accent": "british"},
]

SAMPLE_RATE = 24000


class TTSEngine:
    def __init__(self):
        self.pipe = None
        self.device = os.environ.get("KOKORO_DEVICE", "cuda:0" if torch.cuda.is_available() else "cpu")
        self.lock = asyncio.Lock()
        self._loaded = False

    def load(self):
        if self._loaded:
            return
        from kokoro import KPipeline
        logger.info(f"Loading Kokoro model on {self.device}...")
        start = time.time()
        self.pipe = KPipeline(repo_id="hexgrad/Kokoro-82M", lang_code="a", device=self.device)
        self._loaded = True
        logger.info(f"Model loaded in {time.time() - start:.1f}s")

    @property
    def is_loaded(self):
        return self._loaded

    def synthesize(self, text: str, voice: str = "af_heart") -> tuple[torch.Tensor, int]:
        """Synthesize text, return (audio_tensor, sample_rate)."""
        chunks = []
        for _gs, _ps, audio in self.pipe(text, voice=voice):
            if audio is not None:
                chunks.append(audio)
        if not chunks:
            raise ValueError("No audio produced")
        full = torch.cat([c.unsqueeze(0) if c.dim() == 1 else c for c in chunks], dim=-1)
        if full.dim() == 1:
            full = full.unsqueeze(0)
        return full, SAMPLE_RATE


engine = TTSEngine()


def tensor_to_wav_b64(tensor: torch.Tensor, sr: int) -> str:
    buf = io.BytesIO()
    torchaudio.save(buf, tensor.cpu(), sr, format="wav")
    return base64.b64encode(buf.getvalue()).decode()


def estimate_word_timings(text: str, duration_ms: float) -> list[dict]:
    """Heuristic word timing based on character-length proportional distribution."""
    pattern = re.compile(r"[\w]+(?:['\u2019\-][\w]+)*|[^\s\w]")
    matches = list(pattern.finditer(text))
    if not matches:
        return []

    weights = []
    for m in matches:
        w = m.group()
        weight = max(3, len(w))
        if re.match(r"[.!?]$", w):
            weight += 4  # pause after sentence-ending punctuation
        elif re.match(r"[,;:]$", w):
            weight += 2  # short pause after comma etc.
        weights.append(weight)

    total_weight = sum(weights)
    words = []
    cursor_ms = 0.0
    for m, weight in zip(matches, weights):
        word_dur = (weight / total_weight) * duration_ms
        words.append({
            "word": m.group(),
            "start_ms": round(cursor_ms),
            "end_ms": round(cursor_ms + word_dur),
            "char_start": m.start(),
            "char_end": m.end(),
        })
        cursor_ms += word_dur
    return words


def split_sentences(text: str) -> list[str]:
    """Split text into sentences using regex heuristics."""
    text = text.strip()
    if not text:
        return []
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z"\u201C])', text)
    result = []
    for p in parts:
        p = p.strip()
        if p:
            if result and len(result[-1]) < 20 and not re.search(r'[.!?]$', result[-1]):
                result[-1] += " " + p
            else:
                result.append(p)
    return result if result else [text]


class SynthesizeRequest(BaseModel):
    text: str
    voice: str = "af_heart"


class BatchRequest(BaseModel):
    text: str
    voice: str = "af_heart"


@app.on_event("startup")
async def startup():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, engine.load)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model_loaded": engine.is_loaded,
        "device": engine.device,
    }


@app.get("/voices")
async def voices():
    return {"voices": VOICES}


@app.post("/synthesize")
async def synthesize(req: SynthesizeRequest):
    if not engine.is_loaded:
        raise HTTPException(503, "Model not loaded yet")
    if not req.text.strip():
        raise HTTPException(400, "Empty text")

    voice_ids = [v["id"] for v in VOICES]
    voice = req.voice if req.voice in voice_ids else "af_heart"

    async with engine.lock:
        try:
            tensor, sr = await asyncio.get_event_loop().run_in_executor(
                None, engine.synthesize, req.text.strip(), voice
            )
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            raise HTTPException(500, f"Synthesis error: {e}")

    duration_ms = (tensor.shape[-1] / sr) * 1000
    audio_b64 = await asyncio.get_event_loop().run_in_executor(
        None, tensor_to_wav_b64, tensor, sr
    )
    words = estimate_word_timings(req.text.strip(), duration_ms)

    return {
        "audio_b64": audio_b64,
        "words": words,
        "duration_ms": round(duration_ms),
        "sample_rate": sr,
    }


@app.post("/synthesize/stream")
async def synthesize_stream(req: BatchRequest):
    if not engine.is_loaded:
        raise HTTPException(503, "Model not loaded yet")
    if not req.text.strip():
        raise HTTPException(400, "Empty text")

    voice_ids = [v["id"] for v in VOICES]
    voice = req.voice if req.voice in voice_ids else "af_heart"
    sentences = split_sentences(req.text.strip())

    async def event_stream():
        loop = asyncio.get_event_loop()
        for i, sentence in enumerate(sentences):
            async with engine.lock:
                try:
                    tensor, sr = await loop.run_in_executor(
                        None, engine.synthesize, sentence, voice
                    )
                except Exception as e:
                    logger.error(f"Sentence {i} failed: {e}")
                    data = json.dumps({"index": i, "error": str(e), "text": sentence})
                    yield f"data: {data}\n\n"
                    continue

            duration_ms = (tensor.shape[-1] / sr) * 1000
            audio_b64 = await loop.run_in_executor(None, tensor_to_wav_b64, tensor, sr)
            words = estimate_word_timings(sentence, duration_ms)

            data = json.dumps({
                "index": i,
                "text": sentence,
                "audio_b64": audio_b64,
                "words": words,
                "duration_ms": round(duration_ms),
            })
            yield f"data: {data}\n\n"

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8008))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
