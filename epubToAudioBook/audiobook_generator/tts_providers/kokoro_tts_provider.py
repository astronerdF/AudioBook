import logging
import os
import tempfile
from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.tts_providers.base_tts_provider import BaseTTSProvider
from audiobook_generator.utils.utils import split_text, set_audio_tags, pydub_merge_audio_segments

logger = logging.getLogger(__name__)

class KokoroTTSProvider(BaseTTSProvider):
    def __init__(self, config):
        super().__init__(config)
        # kokoro tts specific initialization
        self.device = self.config.device
        self.tts_model = None

    def validate_config(self):
        pass

    def get_tts_model(self):
        if self.tts_model is None:
            from kokoro_tts import KokoroTTS
            self.tts_model = KokoroTTS(repo_id='hexgrad/Kokoro-82M', device=self.device)
        return self.tts_model

    def get_break_string(self):
        return ""

    def get_output_file_extension(self):
        return "wav"

    def text_to_speech(self, text: str, output_file: str, audio_tags: AudioTags):
        max_chars = 3000  # Adjust as needed
        text_chunks = split_text(text, max_chars, self.config.language)
        
        temp_files = []
        with tempfile.TemporaryDirectory() as temp_dir:
            for i, chunk in enumerate(text_chunks):
                chunk_id = f"chapter-{audio_tags.idx}_{audio_tags.title}_chunk_{i}_of_{len(text_chunks)}"
                logger.info(f"Processing {chunk_id}, length={len(chunk)}")
                
                temp_file = os.path.join(temp_dir, f"{i}.wav")
                self._synthesize_speech(chunk, temp_file)
                temp_files.append(temp_file)

            pydub_merge_audio_segments(temp_files, output_file, self.get_output_file_extension())

        set_audio_tags(output_file, audio_tags)

    def _synthesize_speech(self, text: str, output_file: str):
        self.get_tts_model().synthesize(
            text=text,
            output_file=output_file,
            voice=self.config.voice_name,
            language="en",
        )

    def estimate_cost(self, total_chars):
        return 0.0

    def __str__(self) -> str:
        return f"KokoroTTSProvider(device={self.device})"