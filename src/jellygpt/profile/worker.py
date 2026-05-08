from __future__ import annotations

import time

from jellygpt.config import Settings
from .update import update_taste_profile


def run_profile_loop(settings: Settings) -> None:
    while True:
        try:
            result = update_taste_profile(settings)
            print(
                "profile-loop:",
                f"updated={result.updated}",
                f"events={result.events_seen}",
                f"chunks={result.chunks_processed}",
                f"used_ollama={result.used_ollama}",
                f"warning={result.warning}",
                flush=True,
            )
        except Exception as exc:
            print(f"profile-loop error: {exc}", flush=True)
        time.sleep(settings.profile_refresh_interval_seconds)
