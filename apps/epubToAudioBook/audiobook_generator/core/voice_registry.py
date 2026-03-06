"""
Character Voice Registry for Dramatized Audiobooks

Maps characters to voice profiles (preset voices or cloned voice references).
Persists per book so that character voices remain consistent across chapters
and across generation sessions (e.g., regenerating a single chapter).
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class VoiceProfile:
    """A voice identity for a character or the narrator."""
    voice_id: str  # Unique identifier for this voice
    display_name: str  # Human-readable name (e.g., "Jon Snow")
    # For preset voices
    preset_voice: Optional[str] = None  # Model voice name (e.g., "af_heart")
    # For cloned voices
    reference_audio: Optional[str] = None  # Path to reference audio file
    reference_text: Optional[str] = None  # Transcript of reference audio
    # Voice characteristics
    gender: Optional[str] = None  # "male", "female", "neutral"
    age: Optional[str] = None  # "young", "middle", "old"
    tone: Optional[str] = None  # Default emotional tone
    description: Optional[str] = None  # Free-form voice description

    def to_dict(self) -> dict:
        return {
            "voice_id": self.voice_id,
            "display_name": self.display_name,
            "preset_voice": self.preset_voice,
            "reference_audio": self.reference_audio,
            "reference_text": self.reference_text,
            "gender": self.gender,
            "age": self.age,
            "tone": self.tone,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "VoiceProfile":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# Default narrator voice profiles for different TTS backends
DEFAULT_NARRATOR_PROFILES = {
    "kokoro": VoiceProfile(
        voice_id="narrator",
        display_name="Narrator",
        preset_voice="af_heart",
        gender="female",
        description="Default Kokoro narrator voice",
    ),
    "vibevoice": VoiceProfile(
        voice_id="narrator",
        display_name="Narrator",
        preset_voice=None,  # Will use reference audio
        gender="male",
        description="Default VibeVoice narrator voice",
    ),
}


class VoiceRegistry:
    """Manages character-to-voice mappings for a book.

    The registry is persisted as a JSON file in the book's output directory
    so that voice assignments are stable across generation runs.
    """

    REGISTRY_FILENAME = "voice_registry.json"

    def __init__(self, output_dir: str, tts_backend: str = "vibevoice"):
        self.output_dir = output_dir
        self.tts_backend = tts_backend
        self._profiles: Dict[str, VoiceProfile] = {}
        self._character_map: Dict[str, str] = {}  # character_name -> voice_id
        self._load()

    def _registry_path(self) -> str:
        return os.path.join(self.output_dir, self.REGISTRY_FILENAME)

    def _load(self):
        """Load registry from disk if it exists."""
        path = self._registry_path()
        if not os.path.exists(path):
            logger.info("No existing voice registry at %s, starting fresh.", path)
            self._ensure_narrator()
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for profile_data in data.get("profiles", []):
                profile = VoiceProfile.from_dict(profile_data)
                self._profiles[profile.voice_id] = profile

            self._character_map = data.get("character_map", {})
            logger.info(
                "Loaded voice registry: %d profiles, %d character mappings",
                len(self._profiles),
                len(self._character_map),
            )
        except Exception:
            logger.exception("Failed to load voice registry, starting fresh.")
            self._profiles.clear()
            self._character_map.clear()
            self._ensure_narrator()

    def _ensure_narrator(self):
        """Ensure there's always a narrator voice profile."""
        if "narrator" not in self._profiles:
            default = DEFAULT_NARRATOR_PROFILES.get(self.tts_backend)
            if default:
                self._profiles["narrator"] = default
            else:
                self._profiles["narrator"] = VoiceProfile(
                    voice_id="narrator",
                    display_name="Narrator",
                    description="Default narrator voice",
                )

    def save(self):
        """Persist registry to disk."""
        os.makedirs(self.output_dir, exist_ok=True)
        data = {
            "tts_backend": self.tts_backend,
            "profiles": [p.to_dict() for p in self._profiles.values()],
            "character_map": self._character_map,
        }
        path = self._registry_path()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("Voice registry saved to %s", path)

    def get_narrator_profile(self) -> VoiceProfile:
        """Get the narrator voice profile."""
        return self._profiles["narrator"]

    def set_narrator_profile(self, profile: VoiceProfile):
        """Set a custom narrator voice profile."""
        profile.voice_id = "narrator"
        self._profiles["narrator"] = profile

    def get_voice_for_character(self, character_name: str) -> Optional[VoiceProfile]:
        """Get the voice profile assigned to a character, if any."""
        voice_id = self._character_map.get(character_name)
        if voice_id:
            return self._profiles.get(voice_id)
        return None

    def assign_voice(self, character_name: str, profile: VoiceProfile):
        """Assign a voice profile to a character."""
        self._profiles[profile.voice_id] = profile
        self._character_map[character_name] = profile.voice_id
        logger.info("Assigned voice '%s' to character '%s'", profile.voice_id, character_name)

    def auto_assign_voices(
        self,
        characters: List[str],
        available_voices: List[VoiceProfile],
    ):
        """Auto-assign voice profiles to characters that don't have one yet.

        Uses round-robin assignment from available voice profiles.
        Characters already mapped are skipped.
        """
        unassigned = [c for c in characters if c not in self._character_map]
        if not unassigned:
            return

        if not available_voices:
            logger.warning("No available voices for auto-assignment.")
            return

        for i, character in enumerate(unassigned):
            voice = available_voices[i % len(available_voices)]
            # Create a character-specific copy of the profile
            char_profile = VoiceProfile(
                voice_id=f"char_{character.lower().replace(' ', '_')}",
                display_name=character,
                preset_voice=voice.preset_voice,
                reference_audio=voice.reference_audio,
                reference_text=voice.reference_text,
                gender=voice.gender,
                age=voice.age,
                tone=voice.tone,
                description=f"Voice for {character} (auto-assigned from {voice.display_name})",
            )
            self.assign_voice(character, char_profile)

        logger.info("Auto-assigned voices for %d characters.", len(unassigned))

    def get_all_characters(self) -> Dict[str, str]:
        """Return character_name -> voice_id mapping."""
        return dict(self._character_map)

    def get_all_profiles(self) -> Dict[str, VoiceProfile]:
        """Return all voice profiles."""
        return dict(self._profiles)

    def remove_character(self, character_name: str):
        """Remove a character's voice assignment."""
        voice_id = self._character_map.pop(character_name, None)
        if voice_id and voice_id != "narrator":
            # Only remove profile if no other character uses it
            if voice_id not in self._character_map.values():
                self._profiles.pop(voice_id, None)
