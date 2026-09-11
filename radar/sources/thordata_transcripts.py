"""Transcripciones vía Thordata (`youtube_transcript_by-id`). De pago.

Es la única fuente donde no hay alternativa gratis: transcripciones a escala
sin bloqueos. El resultado es un JSON con un enlace a un `.vtt` público, que se
descarga y se parsea con `radar.parsers.subtitle_segments`.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..config import Settings
from ..models import TranscriptDoc
from ..parsers import (
    subtitle_filename_parts,
    subtitle_segments,
    transcript_tasks_from_raw,
)
from ..spiders import transcript_request
from ..thordata import ThordataClient
from . import SourceError


class ThordataTranscriptSource:
    name = "thordata"

    def __init__(self, settings: Settings, client: ThordataClient | None = None, raw_dir=None):
        self.settings = settings
        self.raw_dir = Path(raw_dir) if raw_dir else settings.db_path.parent / "raw"
        self._client = client

    def fetch(self, video_id: str, lang: str | None = None) -> TranscriptDoc:
        owns_client = self._client is None
        client = self._client or ThordataClient(self.settings)
        try:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            task_id = client.launch(transcript_request(video_id, lang))
            result_path = self.raw_dir / f"{video_id}-transcript.json"
            client.poll_and_save(task_id, result_path)

            tasks = transcript_tasks_from_raw(
                json.loads(result_path.read_text(encoding="utf-8"))
            )
            matched = next(
                (task for task in tasks if task.video_id == video_id),
                tasks[0] if tasks else None,
            )
            if matched is None:
                raise SourceError(f"{video_id}: sin enlace de subtítulos")
            if matched.error:
                raise SourceError(
                    f"{video_id}: subtítulos con error {matched.error_code} {matched.error}".strip()
                )

            parts = subtitle_filename_parts(matched.download_url)
            subtitle_lang = parts[1] if parts else (lang or "en")
            subtitle_text = client.fetch_text(matched.download_url)
            subtitle_path = self.raw_dir / f"{video_id}_{subtitle_lang}.vtt"
            subtitle_path.write_text(subtitle_text, encoding="utf-8")

            segments = subtitle_segments(subtitle_text, video_id, subtitle_lang)
            return TranscriptDoc(
                video_id=video_id,
                lang=subtitle_lang,
                subtitle_type="auto_generated",
                segments=segments,
            )
        finally:
            if owns_client:
                client.close()
