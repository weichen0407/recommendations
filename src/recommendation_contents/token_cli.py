"""CLI helpers for managing local Eureka token cache."""

from __future__ import annotations

import argparse
import getpass
import json
import subprocess
import sys

from .config import AppSettings, apply_env_file_to_process
from .services.eureka_token import EurekaTokenManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage local Eureka token cache.")
    parser.add_argument("--env-file", default=".env", help="Path to dotenv file.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    save_parser = subparsers.add_parser("save-refresh", help="Save refresh token locally.")
    save_parser.add_argument("--refresh-token", default="", help="Refresh token to store.")
    save_parser.add_argument("--cookie", default="", help="Cookie header value to store.")
    save_parser.add_argument("--prompt-cookie", action="store_true", help="Prompt for cookie input.")
    save_parser.add_argument("--client-id", default="", help="Passport client_id.")
    save_parser.add_argument("--from-value", default="eureka", help="Refresh payload `from` value.")
    save_parser.add_argument("--response-type", default="TOKEN", help="Refresh payload response_type.")

    cookie_parser = subparsers.add_parser("save-cookie", help="Save or update refresh cookie locally.")
    cookie_parser.add_argument("--cookie", default="", help="Cookie header value to store.")
    cookie_parser.add_argument("--prompt-cookie", action="store_true", help="Prompt for cookie input.")

    import_parser = subparsers.add_parser(
        "import-curl",
        help="Import authorization, signature, and cookie from a browser curl command.",
    )
    import_parser.add_argument("--curl", default="", help="Raw curl command text.")
    import_parser.add_argument("--from-file", default="", help="Read curl command text from a file.")
    import_parser.add_argument(
        "--clipboard",
        action="store_true",
        help="Read curl command text from the macOS clipboard.",
    )

    subparsers.add_parser("status", help="Show redacted local token cache status.")
    subparsers.add_parser("refresh", help="Refresh access token immediately.")

    args = parser.parse_args()
    apply_env_file_to_process(args.env_file)
    settings = AppSettings.from_env_file(args.env_file)
    manager = EurekaTokenManager(settings.eureka)

    if args.command == "save-refresh":
        _save_refresh(args, manager)
    elif args.command == "save-cookie":
        _save_cookie(args, manager)
    elif args.command == "import-curl":
        _import_curl(args, manager)
    elif args.command == "status":
        _print_status(manager)
    elif args.command == "refresh":
        _refresh(manager)


def _save_refresh(args: argparse.Namespace, manager: EurekaTokenManager) -> None:
    refresh_token = args.refresh_token or getpass.getpass("Refresh token: ").strip()
    cookie = args.cookie
    if args.prompt_cookie:
        cookie = getpass.getpass("Cookie header value, optional: ").strip()

    path = manager.save_refresh_credentials(
        refresh_token=refresh_token,
        cookie=cookie,
        client_id=args.client_id,
        from_value=args.from_value,
        response_type=args.response_type,
    )
    print(json.dumps({"saved": True, "cache_path": str(path)}, ensure_ascii=False))


def _save_cookie(args: argparse.Namespace, manager: EurekaTokenManager) -> None:
    cookie = args.cookie
    if args.prompt_cookie or not cookie:
        cookie = getpass.getpass("Cookie header value: ").strip()

    path = manager.save_cookie(cookie=cookie)
    print(json.dumps({"saved": True, "cache_path": str(path)}, ensure_ascii=False))


def _import_curl(args: argparse.Namespace, manager: EurekaTokenManager) -> None:
    curl_text = _read_curl_text(args)
    result = manager.import_curl(curl_text)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _read_curl_text(args: argparse.Namespace) -> str:
    if args.curl:
        return args.curl
    if args.from_file:
        with open(args.from_file, encoding="utf-8") as file:
            return file.read()
    if args.clipboard:
        result = subprocess.run(["pbpaste"], check=True, capture_output=True, text=True)
        return result.stdout
    if not sys.stdin.isatty():
        return sys.stdin.read()

    print("Paste curl command, then press Ctrl-D:")
    return sys.stdin.read()


def _print_status(manager: EurekaTokenManager) -> None:
    record = manager.read_cached_record_redacted()
    check = manager.check_token()
    payload = {
        "cache_path": str(manager.cache_path() or ""),
        "has_access_token": record.get("has_access_token", False),
        "has_refresh_token": record.get("has_refresh_token", False),
        "has_cookie": record.get("has_cookie", False),
        "has_signature_id": record.get("has_signature_id", False),
        "expires_at": record.get("expires_at", ""),
        "token_status": check.status,
        "token_reason": check.reason,
        "refresh_available": check.refresh_available,
        "site_lang": record.get("site_lang", ""),
        "imported_from_url": record.get("imported_from_url", ""),
        "imported_at": record.get("imported_at", ""),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _refresh(manager: EurekaTokenManager) -> None:
    result = manager.refresh_access_token()
    payload = {
        "success": result.success,
        "status": result.status,
        "reason": result.reason,
        "cache_path": str(manager.cache_path() or ""),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
