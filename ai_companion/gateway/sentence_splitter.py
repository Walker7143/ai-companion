"""
Sentence splitter — splits AI responses into natural sentences for gradual sending.

Designed to mimic human typing patterns: sentences are sent one at a time
with random delays between them.
"""

import random
import asyncio
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Ellipsis placeholder — must not appear in normal text
_ELLIPSIS_MARKER = "\x00ELLIPSIS\x00"
def get_delay_for_sentence(sentence: str) -> float:
    """
    Calculate human-like delay before sending a sentence.

    Delay depends on sentence length:
    - <= 5 characters: 0-1 seconds (quick response like typing a short reply)
    - > 5 characters: 1.5-3 seconds (longer thinking/writing time)

    Returns:
        Delay in seconds (float)
    """
    char_count = len(sentence.strip())
    if char_count <= 5:
        return random.uniform(0.0, 1.0)
    else:
        return random.uniform(1.5, 3.0)


class SentenceSplitter:
    """
    Split a text into sentences for gradual (逐句) sending.

    Sentence boundaries are detected at:
    - 。 ！ ？
    -换行符 \\n \\r

    Edge cases handled:
    - Ellipsis "……" is treated as a single unit, not two sentence breaks
    - Consecutive sentence-ending punctuations ("！！！", "？！", "!?") stay attached
    - Leading/trailing whitespace per sentence is stripped
    - Empty fragments are discarded
    """

    _END_PUNCTUATION = "。！？!?"
    _TRAILING_CLOSERS = "\"'”’）)]】》」』〉〕】"

    @classmethod
    def split(cls, text: str) -> List[str]:
        """
        Split *text* into a list of sentences.

        Returns:
            List of non-empty sentence strings, in order.
        """
        if not text:
            return []

        # Step 1: Protect ellipsis "……" → placeholder
        protected = text.replace("……", _ELLIPSIS_MARKER)

        # Step 2: Split by sentence boundaries
        # We split manually rather than regex.split() to preserve what we split on
        sentences, current = [], ""

        i = 0
        while i < len(protected):
            char = protected[i]

            # Check for sentence-ending punctuation. Keep a whole run like "？！"
            # or "!!?" attached to the same sentence instead of splitting inside it.
            if char in cls._END_PUNCTUATION:
                while i < len(protected) and protected[i] in cls._END_PUNCTUATION:
                    current += protected[i]
                    i += 1
                # Keep closing quotes/brackets attached to the same sentence:
                # e.g. `“好。”` / `"Really?"` / `（“好。”）`
                while i < len(protected) and protected[i] in cls._TRAILING_CLOSERS:
                    current += protected[i]
                    i += 1
                sentences.append(current)
                current = ""
                continue

            # Check for newline
            if char in "\n\r":
                # Treat newline as a sentence break
                if current.strip():
                    sentences.append(current)
                current = ""
                # Skip all consecutive whitespace/newlines
                while i < len(protected) and protected[i] in " \t\n\r":
                    i += 1
                continue

            # Check for ellipsis placeholder
            if protected[i:].startswith(_ELLIPSIS_MARKER):
                current += "……"  # Restore original
                i += len(_ELLIPSIS_MARKER)
                continue

            current += char
            i += 1

        # Append any remaining text
        if current.strip():
            sentences.append(current)

        # Step 3: Restore ellipsis placeholders (may appear mid-sentence)
        sentences = [s.replace(_ELLIPSIS_MARKER, "……") for s in sentences]

        # Step 4: Strip whitespace
        sentences = [s.strip() for s in sentences if s.strip()]

        return sentences


async def send_gradually(
    sender_fn,
    chat_id: str,
    content: str,
    reply_to: str = None,
    metadata: dict = None,
) -> Tuple[int, List[dict]]:
    """
    Send *content* as a series of gradually-delivered sentences.

    Args:
        sender_fn: Async callable(chat_id, text, reply_to, metadata) → SendResult
        chat_id: Target chat
        content: Full message text
        reply_to: Optional message ID to reply to
        metadata: Optional metadata dict

    Returns:
        (sent_count, list_of_SendResults)
    """
    sentences = SentenceSplitter.split(content)

    if not sentences:
        return 0, []

    results = []
    for i, sentence in enumerate(sentences):
        if not sentence.strip():
            continue

        try:
            result = await sender_fn(chat_id, sentence, reply_to=reply_to, metadata=metadata)
            results.append(result)

            # Log sending result
            if result.success:
                logger.debug(
                    "[GradualSend] Sent sentence %d/%d (%d chars) to %s",
                    i + 1, len(sentences), len(sentence), chat_id,
                )
            else:
                logger.warning(
                    "[GradualSend] Failed to send sentence %d/%d to %s: %s",
                    i + 1, len(sentences), chat_id, result.error,
                )

        except Exception as e:
            logger.error(
                "[GradualSend] Exception sending sentence %d/%d to %s: %s",
                i + 1, len(sentences), chat_id, e,
            )
            results.append({"success": False, "error": str(e)})

        # Sleep between sentences, except after the last one
        # Delay is based on sentence length: short sentences get shorter delay
        if i < len(sentences) - 1:
            delay = get_delay_for_sentence(sentence)
            await asyncio.sleep(delay)

    return len(sentences), results
