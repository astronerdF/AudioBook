import torch
import torchaudio
from kokoro import KPipeline

class KokoroTTS:
    def __init__(self, repo_id='hexgrad/Kokoro-82M', lang_code="a", device="cuda"):
        self.pipe = KPipeline(repo_id=repo_id, lang_code=lang_code, device=device)

    def synthesize(self, text, voice="af_heart", language=None, output_file="output.wav"):
        audio_data = []
        # run Kokoro
        generator = self.pipe(text, voice=voice)
        for gs, ps, audio in generator:
            audio_data.append(audio.unsqueeze(0))

        if not audio_data:
            return

        full_audio_tensor = torch.cat(audio_data, dim=1)
        torchaudio.save(output_file, full_audio_tensor.cpu(), 24000)
