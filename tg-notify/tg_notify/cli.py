import argparse
import json
import sys

from tg_notify.notify.sender import Notify
from tg_notify.core.exceptions import TgkitError


def parse_button_spec(spec_json: str) -> list[list[tuple[str, str]]]:
    """Parse a --buttons JSON value into rows of (label, callback_data).

    Accepts a flat list ``[[label, data], ...]`` (each pair is its own row) or
    nested rows ``[[[label, data], ...], ...]``. Raises ValueError on bad input.
    """
    try:
        data = json.loads(spec_json)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"invalid --buttons JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError("--buttons must be a JSON list")
    rows: list[list[tuple[str, str]]] = []
    for item in data:
        if item and isinstance(item[0], str):  # flat [label, data] → single-button row
            rows.append([(str(item[0]), str(item[1]))])
        else:
            rows.append([(str(b[0]), str(b[1])) for b in item])
    return rows


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--chat-id", type=int, help="Override target chat id")
    parser.add_argument(
        "--config-path",
        help="JSON config file used to resolve chat_id (default: config.json)",
    )
    parser.add_argument("--caption", help="Optional caption for photos")


def _add_app_args(parser: argparse.ArgumentParser) -> None:
    app_group = parser.add_mutually_exclusive_group()
    app_group.add_argument("--app", help="Application name for open -a (e.g. Safari)")
    app_group.add_argument("--app-path", help="Path to a .app bundle")
    app_group.add_argument("--bundle-id", help="Bundle id for open -b")
    parser.add_argument(
        "--process",
        help="System Events process name when it differs from --app (e.g. Code for VS Code)",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=2.0,
        help="Seconds to wait for the app window after launch (default: 2.0)",
    )
    parser.add_argument(
        "--window-index",
        type=int,
        default=1,
        help="1-based window index to capture (default: 1)",
    )
    parser.add_argument(
        "--no-shadow",
        action="store_true",
        help="Capture app window without drop shadow",
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tgkit", description="Send Telegram notifications")
    subparsers = parser.add_subparsers(dest="command", required=True)

    send_parser = subparsers.add_parser("send", help="Send a text message, photo, or file")
    send_parser.add_argument("message", nargs="?", help="Text message (shorthand for --text)")
    send_parser.add_argument("--text", help="Text message body")
    send_parser.add_argument("--photo", help="Path to an image (inline preview)")
    send_parser.add_argument("--file", help="Path to a file to send as document")
    send_parser.add_argument(
        "--parse-mode",
        choices=["HTML", "MarkdownV2", "Markdown"],
        help="Render text with Telegram formatting (HTML / MarkdownV2 / Markdown)",
    )
    send_parser.add_argument(
        "--buttons",
        help='Inline keyboard as JSON, e.g. [["1. Yes","sel:72:1:1"],["2. No","sel:72:1:2"]]',
    )
    _add_common_args(send_parser)

    shot_parser = subparsers.add_parser("screenshot", help="Capture screen and send (macOS)")
    shot_parser.add_argument(
        "--mode",
        choices=["full", "interactive", "window"],
        default="full",
        help="full=entire screen, interactive=drag to select, window=click a window",
    )
    shot_parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep the temporary screenshot file after sending",
    )
    _add_common_args(shot_parser)
    _add_app_args(shot_parser)

    args = parser.parse_args(argv)
    notifier = Notify(config_path=getattr(args, "config_path", None))

    try:
        if args.command == "send":
            if not args.text and not args.file and not args.message and not args.photo:
                send_parser.error("Provide a message, --text, --photo, and/or --file")

            text_body = args.text or args.message
            if text_body:
                extra = {"parse_mode": args.parse_mode} if args.parse_mode else {}
                if getattr(args, "buttons", None):
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

                    rows = parse_button_spec(args.buttons)
                    extra["reply_markup"] = InlineKeyboardMarkup(
                        [
                            [InlineKeyboardButton(lbl, callback_data=data) for lbl, data in row]
                            for row in rows
                        ]
                    )
                result = notifier.text(text_body, chat_id=args.chat_id, **extra)
                print(f"sent text to chat_id={result.chat_id} message_id={result.message_id}")
            if args.photo:
                result = notifier.photo(
                    args.photo,
                    chat_id=args.chat_id,
                    caption=args.caption,
                )
                print(f"sent photo to chat_id={result.chat_id} message_id={result.message_id}")
            if args.file:
                result = notifier.file(args.file, chat_id=args.chat_id)
                print(f"sent file to chat_id={result.chat_id} message_id={result.message_id}")

        elif args.command == "screenshot":
            if args.app or args.app_path or args.bundle_id:
                result = notifier.app_screenshot(
                    app=args.app,
                    app_path=args.app_path,
                    bundle_id=args.bundle_id,
                    process_name=args.process,
                    wait_seconds=args.wait,
                    window_index=args.window_index,
                    no_shadow=args.no_shadow,
                    chat_id=args.chat_id,
                    caption=args.caption,
                    delete_after_send=not args.keep,
                )
            else:
                result = notifier.screenshot(
                    chat_id=args.chat_id,
                    caption=args.caption,
                    mode=args.mode,
                    delete_after_send=not args.keep,
                )
            print(f"sent screenshot to chat_id={result.chat_id} message_id={result.message_id}")
        else:
            parser.error(f"Unsupported command: {args.command}")

    except TgkitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
