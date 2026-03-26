from __future__ import annotations

import argparse
import sys
from pathlib import Path

from codex_adv.chat import InteractiveChat
from codex_adv.config import load_config
from codex_adv.learning import LearningStore
from codex_adv.router import Router


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex-adv")
    parser.add_argument(
        "--config",
        default=None,
        help="Path to router TOML config. Defaults to ./.codex-adv/router.toml",
    )

    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Create local config directory.")
    init_parser.add_argument(
        "--force", action="store_true", help="Overwrite existing config if present."
    )

    run_parser = subparsers.add_parser("run", help="Route and execute a prompt.")
    run_parser.add_argument("prompt", nargs="+", help="Prompt to send through the router.")

    chat_parser = subparsers.add_parser("chat", help="Start an interactive chat session.")
    chat_parser.add_argument(
        "--new",
        action="store_true",
        help="Start a new session instead of resuming the latest one.",
    )

    subparsers.add_parser("stats", help="Show historical routing summary.")
    return parser


def command_init(config_path: str | None, force: bool) -> int:
    target = Path(config_path or ".codex-adv/router.toml")
    target.parent.mkdir(parents=True, exist_ok=True)
    example = Path("config/router.example.toml")

    if target.exists() and not force:
        print(f"Config already exists at {target}")
        return 0

    target.write_text(example.read_text())
    print(f"Created config at {target}")
    return 0


def command_run(config_path: str | None, prompt_parts: list[str]) -> int:
    prompt = " ".join(prompt_parts).strip()
    config = load_config(config_path)
    store = LearningStore(config.database.path)
    router = Router(config, store)
    response = router.run(prompt)

    print(response.output)
    print(
        f"\n[model: {response.final_model} | initial: {response.initial_model} "
        f"| fallback: {str(response.fallback_used).lower()} "
        f"| task: {response.classification.task_type} "
        f"| complexity: {response.classification.complexity_score}]",
        file=sys.stderr,
    )
    if not response.success:
        print(f"[failure: {response.failure_reason}]", file=sys.stderr)
        return 1
    return 0


def command_chat(config_path: str | None, new_session: bool) -> int:
    config = load_config(config_path)
    store = LearningStore(config.database.path)
    router = Router(config, store)
    chat = InteractiveChat(router, store)
    return chat.start(resume_latest=not new_session)


def command_stats(config_path: str | None) -> int:
    config = load_config(config_path)
    store = LearningStore(config.database.path)
    rows = store.summary()

    if not rows:
        print("No routing history yet.")
        return 0

    print("model\ttask_type\ttotal\tsuccess_rate\tavg_latency\tfallbacks")
    for row in rows:
        print(
            f"{row['chosen_model']}\t{row['task_type']}\t{row['total_requests']}\t"
            f"{row['success_rate']}\t{row['avg_latency']}\t{row['fallbacks']}"
        )
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        raise SystemExit(command_chat(args.config, new_session=False))
    if args.command == "init":
        raise SystemExit(command_init(args.config, args.force))
    if args.command == "run":
        raise SystemExit(command_run(args.config, args.prompt))
    if args.command == "chat":
        raise SystemExit(command_chat(args.config, args.new))
    if args.command == "stats":
        raise SystemExit(command_stats(args.config))

    raise SystemExit(2)


if __name__ == "__main__":
    main()
