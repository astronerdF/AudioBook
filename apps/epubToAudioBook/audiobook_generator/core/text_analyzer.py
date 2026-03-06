"""
Text Analyzer for Dramatized Audiobooks

Parses chapter text into structured segments:
- Narration (narrator voice)
- Dialogue (character-attributed speech with emotion hints)
- Thought (internal monologue)

Each segment carries metadata for multi-voice TTS synthesis.
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

logger = logging.getLogger(__name__)


class SegmentType(Enum):
    NARRATION = "narration"
    DIALOGUE = "dialogue"
    THOUGHT = "thought"


@dataclass
class TextSegment:
    type: SegmentType
    text: str
    character: Optional[str] = None
    emotion: Optional[str] = None
    # Position in the original chapter text
    char_start: int = 0
    char_end: int = 0

    def to_dict(self):
        return {
            "type": self.type.value,
            "text": self.text,
            "character": self.character,
            "emotion": self.emotion,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }


# Regex patterns for dialogue detection
# Matches: "dialogue" said Character  /  "dialogue," Character said  /  Character said, "dialogue"
# Supports both straight and curly quotes
DIALOGUE_PATTERN = re.compile(
    r'["\u201c]([^"\u201d]+)["\u201d]',
    re.UNICODE,
)

# Attribution patterns that appear near dialogue
# e.g., "said Jon", "whispered Tyrion", "Jon said", "Tyrion shouted"
SPEECH_VERBS = (
    r"said|says|asked|replied|answered|whispered|shouted|yelled|exclaimed|"
    r"murmured|muttered|cried|called|declared|demanded|insisted|suggested|"
    r"stammered|stuttered|growled|snarled|hissed|snapped|barked|roared|"
    r"pleaded|begged|warned|announced|continued|added|agreed|argued|"
    r"breathed|chuckled|giggled|laughed|screamed|shrieked|sighed|sobbed|"
    r"spoke|stated|told|urged|wailed|wondered|groaned|grumbled|rasped"
)

# "said Character" or "Character said" patterns
ATTRIBUTION_AFTER = re.compile(
    rf',?\s*(?:{SPEECH_VERBS})\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
    re.UNICODE,
)
ATTRIBUTION_BEFORE = re.compile(
    rf'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:{SPEECH_VERBS})',
    re.UNICODE,
)

# Emotion hints from speech verbs
EMOTION_MAP = {
    "whispered": "whisper",
    "shouted": "excited",
    "yelled": "excited",
    "exclaimed": "excited",
    "murmured": "soft",
    "muttered": "annoyed",
    "cried": "sad",
    "growled": "angry",
    "snarled": "angry",
    "hissed": "angry",
    "snapped": "angry",
    "barked": "angry",
    "roared": "angry",
    "pleaded": "pleading",
    "begged": "pleading",
    "warned": "serious",
    "laughed": "amused",
    "chuckled": "amused",
    "giggled": "amused",
    "screamed": "terrified",
    "shrieked": "terrified",
    "sighed": "sad",
    "sobbed": "sad",
    "wailed": "sad",
    "groaned": "pained",
    "rasped": "strained",
}

# Thought patterns (italicized internal monologue, often marked in books)
THOUGHT_PATTERN = re.compile(
    r'(?:^|\s)(?:he|she|they)\s+thought[,.]?\s*["\u201c]([^"\u201d]+)["\u201d]',
    re.UNICODE | re.IGNORECASE,
)


class TextAnalyzer:
    """Analyzes chapter text and splits it into attributed segments."""

    def __init__(self, known_characters: Optional[List[str]] = None):
        self.known_characters = set(known_characters or [])
        self._character_frequency = {}

    def analyze_chapter(self, text: str) -> List[TextSegment]:
        """Parse a chapter into a list of TextSegments with character attribution."""
        segments = []
        last_end = 0
        last_speaker = None

        for match in DIALOGUE_PATTERN.finditer(text):
            dialogue_text = match.group(1).strip()
            full_start = match.start()
            full_end = match.end()

            # Add narration segment for text before this dialogue
            if full_start > last_end:
                narration = text[last_end:full_start].strip()
                if narration:
                    segments.append(TextSegment(
                        type=SegmentType.NARRATION,
                        text=narration,
                        char_start=last_end,
                        char_end=full_start,
                    ))

            # Try to find character attribution in surrounding context
            context_window = 150
            context_after = text[full_end:full_end + context_window]
            context_before = text[max(0, full_start - context_window):full_start]

            character, emotion = self._extract_attribution(
                context_before, context_after, last_speaker
            )

            if character:
                last_speaker = character
                self._track_character(character)

            segments.append(TextSegment(
                type=SegmentType.DIALOGUE,
                text=dialogue_text,
                character=character,
                emotion=emotion,
                char_start=full_start,
                char_end=full_end,
            ))

            last_end = full_end

        # Add remaining narration
        if last_end < len(text):
            remaining = text[last_end:].strip()
            if remaining:
                segments.append(TextSegment(
                    type=SegmentType.NARRATION,
                    text=remaining,
                    char_start=last_end,
                    char_end=len(text),
                ))

        # If no dialogue found, entire text is narration
        if not segments:
            segments.append(TextSegment(
                type=SegmentType.NARRATION,
                text=text,
                char_start=0,
                char_end=len(text),
            ))

        logger.info(
            "Analyzed chapter: %d segments (%d dialogue, %d narration)",
            len(segments),
            sum(1 for s in segments if s.type == SegmentType.DIALOGUE),
            sum(1 for s in segments if s.type == SegmentType.NARRATION),
        )

        return segments

    def _extract_attribution(
        self,
        context_before: str,
        context_after: str,
        last_speaker: Optional[str],
    ) -> tuple:
        """Extract character name and emotion from dialogue context."""
        character = None
        emotion = None

        # Check context after dialogue first ("said Jon")
        after_match = ATTRIBUTION_AFTER.search(context_after)
        if after_match:
            character = after_match.group(1).strip()
            # Extract emotion from the speech verb
            verb_match = re.search(SPEECH_VERBS, context_after[:after_match.end()])
            if verb_match:
                emotion = EMOTION_MAP.get(verb_match.group().lower())

        # Check context before dialogue ("Jon said,")
        if not character:
            before_match = ATTRIBUTION_BEFORE.search(context_before)
            if before_match:
                character = before_match.group(1).strip()
                verb_match = re.search(SPEECH_VERBS, context_before[before_match.start():])
                if verb_match:
                    emotion = EMOTION_MAP.get(verb_match.group().lower())

        # Validate against known characters if we have them
        if character and self.known_characters:
            if not self._is_known_character(character):
                # Still accept it - could be a new character
                self.known_characters.add(character)

        return character, emotion

    def _is_known_character(self, name: str) -> bool:
        """Check if name matches a known character (supports first-name matching)."""
        if name in self.known_characters:
            return True
        # Check first-name match
        for known in self.known_characters:
            if name == known.split()[0] or known == name.split()[0]:
                return True
        return False

    def _track_character(self, character: str):
        """Track character frequency for statistics."""
        self._character_frequency[character] = (
            self._character_frequency.get(character, 0) + 1
        )

    def get_character_stats(self) -> dict:
        """Return character dialogue frequency stats."""
        return dict(
            sorted(
                self._character_frequency.items(),
                key=lambda x: x[1],
                reverse=True,
            )
        )

    def get_discovered_characters(self) -> List[str]:
        """Return all characters discovered during analysis."""
        return sorted(self._character_frequency.keys())


def analyze_book_chapters(
    chapters: List[tuple],
    known_characters: Optional[List[str]] = None,
) -> List[List[TextSegment]]:
    """Analyze all chapters in a book and return structured segments.

    Args:
        chapters: List of (title, text) tuples from the book parser.
        known_characters: Optional pre-seeded character list.

    Returns:
        List of segment lists, one per chapter.
    """
    analyzer = TextAnalyzer(known_characters)
    all_segments = []

    for title, text in chapters:
        logger.info("Analyzing chapter: %s", title)
        segments = analyzer.analyze_chapter(text)
        all_segments.append(segments)

    stats = analyzer.get_character_stats()
    if stats:
        logger.info(
            "Characters found across book: %s",
            ", ".join(f"{name}({count})" for name, count in stats.items()),
        )

    return all_segments
