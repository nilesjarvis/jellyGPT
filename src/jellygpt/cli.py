from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from .config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="jellygpt")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="Run the jellyGPT API")
    sub.add_parser("generate", help="Generate recommendation caches")
    sub.add_parser("benchmark", help="Run recommendation benchmark")
    sub.add_parser("doctor", help="Check configuration and data access")

    profile = sub.add_parser("profile", help="Manage the long-term Markdown taste profile")
    profile_sub = profile.add_subparsers(dest="profile_command", required=True)
    profile_update = profile_sub.add_parser("update", help="Run one taste-profile update")
    profile_update.add_argument("--user-id")
    profile_update.add_argument("--since", help="Only consider watch events after this DB timestamp")
    profile_update.add_argument("--profile-path")
    profile_update.add_argument("--dry-run", action="store_true")
    profile_update.add_argument("--require-ollama", action="store_true")
    profile_sub.add_parser("show", help="Print the current taste-profile path and content if present")

    worker = sub.add_parser("worker", help="Run background workers")
    worker_sub = worker.add_subparsers(dest="worker_command", required=True)
    worker_sub.add_parser("profile-loop", help="Periodically update the Markdown taste profile")

    args = parser.parse_args()

    if args.command == "serve":
        settings = get_settings()
        uvicorn.run("jellygpt.api:app", host=settings.host, port=settings.port)
    elif args.command == "generate":
        print("generate: not implemented yet")
    elif args.command == "benchmark":
        print("benchmark: not implemented yet")
    elif args.command == "doctor":
        print("doctor: not implemented yet")
    elif args.command == "profile":
        settings = get_settings()
        if args.profile_command == "update":
            from .profile.update import update_taste_profile

            result = update_taste_profile(
                settings,
                user_id=args.user_id,
                since=args.since,
                profile_path=Path(args.profile_path) if args.profile_path else None,
                require_ollama=args.require_ollama or None,
                dry_run=args.dry_run,
            )
            print(
                "profile update:",
                f"updated={result.updated}",
                f"events_seen={result.events_seen}",
                f"chunks_processed={result.chunks_processed}",
                f"used_ollama={result.used_ollama}",
                f"profile={result.profile_path}",
            )
            if result.warning:
                print(f"warning={result.warning}")
            if args.dry_run and result.dry_run_markdown:
                print("\n--- dry-run profile markdown ---\n")
                print(result.dry_run_markdown)
        elif args.profile_command == "show":
            path = Path(settings.taste_profile_path)
            print(f"profile={path}")
            if path.exists():
                print(path.read_text(encoding="utf-8"))
            else:
                print("profile does not exist yet")
    elif args.command == "worker":
        if args.worker_command == "profile-loop":
            from .profile.worker import run_profile_loop

            run_profile_loop(get_settings())


if __name__ == "__main__":
    main()
