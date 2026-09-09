"""Watch a logged-in browser session and sync Eureka auth headers."""

from __future__ import annotations

import argparse
import json
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import AppSettings, apply_env_file_to_process
from .services.eureka_token import EurekaTokenManager, ImportedCurlAuth, jwt_expires_at

DEFAULT_START_URL = "https://eureka.patsnap.com/"
DEFAULT_CAPTURE_URL_CONTAINS = "/api/eureka/query/conversational"
DEFAULT_COOKIE_URLS = (
    "https://eureka.patsnap.com",
    "https://eureka-service.patsnap.com",
    "https://passport.patsnap.com",
)

JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    apply_env_file_to_process(args.env_file)
    settings = AppSettings.from_env_file(args.env_file)
    manager = EurekaTokenManager(settings.eureka)
    run_browser_auth_watcher(args=args, manager=manager)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Keep Eureka authorization cache fresh from a logged-in browser session.",
    )
    parser.add_argument("--env-file", default=".env", help="Path to dotenv file.")
    parser.add_argument(
        "--profile",
        default=".browser/eureka",
        help="Persistent Playwright browser profile directory.",
    )
    parser.add_argument("--url", default=DEFAULT_START_URL, help="URL opened on startup.")
    parser.add_argument(
        "--capture-url-contains",
        default=DEFAULT_CAPTURE_URL_CONTAINS,
        help="Only import headers from requests whose URL contains this text.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=60.0,
        help="Seconds between storage/cookie scans.",
    )
    parser.add_argument(
        "--reload-interval",
        type=float,
        default=0.0,
        help="Seconds between page reloads. Disabled by default.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Exit after the first auth update is captured.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="Maximum seconds to wait in --once mode.",
    )
    parser.add_argument(
        "--browser-channel",
        default="chrome",
        help="Playwright browser channel. Use an empty value to use bundled Chromium.",
    )
    parser.add_argument(
        "--executable-path",
        default="",
        help="Explicit browser executable path, if browser-channel is not enough.",
    )
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode.")
    parser.add_argument(
        "--cookie-url",
        action="append",
        default=None,
        help="URL scope used when reading browser cookies. Can be passed multiple times.",
    )
    parser.add_argument(
        "--no-storage-scan",
        action="store_true",
        help="Disable localStorage/sessionStorage JWT scanning.",
    )
    parser.add_argument(
        "--no-derive-signature-from-cookie",
        action="store_true",
        help="Do not use visitor_id cookie as x-signature-id fallback during storage scans.",
    )
    parser.add_argument("--quiet", action="store_true", help="Only print errors.")
    return parser


def run_browser_auth_watcher(args: argparse.Namespace, manager: EurekaTokenManager) -> None:
    sync_playwright = _load_sync_playwright()
    profile_path = Path(args.profile).expanduser()
    profile_path.mkdir(parents=True, exist_ok=True)
    cookie_urls = tuple(args.cookie_url or DEFAULT_COOKIE_URLS)
    launched_context: Any = None

    if not args.quiet:
        _print_json(
            {
                "event": "eureka_auth_watcher_started",
                "profile": str(profile_path),
                "start_url": args.url,
                "capture_url_contains": args.capture_url_contains,
                "cache_path": str(manager.cache_path() or ""),
            }
        )
        _print_json(
            {
                "event": "manual_step",
                "message": (
                    "Log in in the opened browser, then run one Eureka search so the watcher "
                    "can capture the query/conversational request."
                ),
            }
        )

    try:
        with sync_playwright() as playwright:
            launched_context = _launch_persistent_context(playwright, args, profile_path)
            update_count = _watch_context(
                context=launched_context,
                manager=manager,
                args=args,
                cookie_urls=cookie_urls,
            )
    except KeyboardInterrupt:
        if not args.quiet:
            _print_json({"event": "eureka_auth_watcher_stopped", "reason": "keyboard_interrupt"})
        return
    finally:
        if launched_context is not None:
            try:
                launched_context.close()
            except Exception as exc:  # noqa: BLE001 - best-effort cleanup.
                if not args.quiet:
                    _print_json(
                        {
                            "event": "watcher_warning",
                            "source": "browser.close",
                            "error": str(exc),
                        }
                    )

    if args.once and update_count == 0:
        raise SystemExit(2)


def imported_auth_from_request(
    url: str,
    headers: Mapping[str, Any],
    fallback_cookie: str = "",
) -> ImportedCurlAuth | None:
    normalized_headers = {
        str(key).lower(): _string(value)
        for key, value in headers.items()
        if _string(key) and _string(value)
    }
    authorization = normalized_headers.get("authorization", "")
    signature_id = normalized_headers.get("x-signature-id", "")
    site_lang = normalized_headers.get("x-site-lang", "")
    cookie = normalized_headers.get("cookie", "") or fallback_cookie

    if not any((authorization, signature_id, site_lang, cookie)):
        return None

    return ImportedCurlAuth(
        authorization=authorization,
        signature_id=signature_id,
        site_lang=site_lang,
        cookie=cookie,
        source_url=url,
        expires_at=jwt_expires_at(authorization) if authorization else None,
    )


def imported_auth_from_storage_entries(
    entries: Sequence[Mapping[str, Any]],
    cookie_header: str = "",
    signature_id: str = "",
    site_lang: str = "CN",
    source_url: str = "browser-storage",
    min_expires_at: float = 0.0,
) -> ImportedCurlAuth | None:
    token, expires_at = extract_best_jwt_from_storage_entries(
        entries,
        min_expires_at=min_expires_at,
    )
    if not token:
        return None

    return ImportedCurlAuth(
        authorization=f"Bearer {token}",
        signature_id=signature_id,
        site_lang=site_lang,
        cookie=cookie_header,
        source_url=source_url,
        expires_at=expires_at,
    )


def extract_best_jwt_from_storage_entries(
    entries: Sequence[Mapping[str, Any]],
    min_expires_at: float = 0.0,
) -> tuple[str, float | None]:
    best_token = ""
    best_expires_at: float | None = None

    for entry in entries:
        for text in _entry_candidate_text(entry):
            for token in JWT_PATTERN.findall(text):
                expires_at = jwt_expires_at(token)
                if expires_at is None or expires_at <= min_expires_at:
                    continue
                if best_expires_at is None or expires_at > best_expires_at:
                    best_token = token
                    best_expires_at = expires_at

    return best_token, best_expires_at


def build_cookie_header(cookies: Sequence[Mapping[str, Any]]) -> str:
    pairs = []
    seen = set()
    for cookie in cookies:
        name = _string(cookie.get("name"))
        value = _string(cookie.get("value"))
        if not name:
            continue
        key = (name, value)
        if key in seen:
            continue
        seen.add(key)
        pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def signature_id_from_cookie_header(cookie_header: str) -> str:
    for part in cookie_header.split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name in {"visitor_id", "signature_id", "x-signature-id"}:
            value = value.strip()
            if value.startswith("pt_"):
                return value
    return ""


def should_save_auth_candidate(
    candidate: ImportedCurlAuth,
    snapshot: Mapping[str, str],
) -> bool:
    if not any((candidate.authorization, candidate.signature_id, candidate.site_lang, candidate.cookie)):
        return False

    current_authorization = snapshot.get("authorization", "")
    if _is_older_authorization(candidate.authorization, current_authorization, candidate.expires_at):
        return False

    return (
        bool(candidate.authorization and candidate.authorization != current_authorization)
        or bool(candidate.signature_id and candidate.signature_id != snapshot.get("signature_id", ""))
        or bool(candidate.site_lang and candidate.site_lang != snapshot.get("site_lang", ""))
        or bool(candidate.cookie and candidate.cookie != snapshot.get("cookie", ""))
    )


def _watch_context(
    context: Any,
    manager: EurekaTokenManager,
    args: argparse.Namespace,
    cookie_urls: Sequence[str],
) -> int:
    page = _first_page(context)
    latest_cookie = {"header": _read_cookie_header(context, cookie_urls)}
    update_count = 0
    deadline = time.monotonic() + args.timeout if args.once else None
    next_scan_at = 0.0
    next_reload_at = time.monotonic() + args.reload_interval if args.reload_interval > 0 else None

    def save_candidate(candidate: ImportedCurlAuth, source: str) -> bool:
        nonlocal update_count
        if not candidate.cookie and latest_cookie["header"]:
            candidate = replace(candidate, cookie=latest_cookie["header"])
        if not should_save_auth_candidate(candidate, manager.read_cached_auth_snapshot()):
            return False

        result = manager.import_auth(
            authorization=candidate.authorization,
            signature_id=candidate.signature_id,
            site_lang=candidate.site_lang,
            cookie=candidate.cookie,
            source_url=candidate.source_url,
            expires_at=candidate.expires_at,
        )
        update_count += 1
        if not args.quiet:
            _print_update(source=source, result=result)
        return True

    def handle_request(request: Any) -> None:
        try:
            url = request.url
            if args.capture_url_contains and args.capture_url_contains not in url:
                return
            candidate = imported_auth_from_request(url, _request_headers(request))
            if candidate is not None:
                save_candidate(candidate, source="browser-request")
        except Exception as exc:  # noqa: BLE001 - keep watcher alive.
            if not args.quiet:
                _print_json({"event": "watcher_warning", "source": "browser-request", "error": str(exc)})

    context.on("request", handle_request)
    _navigate_start_page(page, args.url, args.quiet)

    while True:
        now = time.monotonic()
        if not args.no_storage_scan and now >= next_scan_at:
            latest_cookie["header"] = _read_cookie_header(context, cookie_urls)
            _scan_storage_pages(
                context=context,
                manager=manager,
                args=args,
                cookie_header=latest_cookie["header"],
                save_candidate=save_candidate,
            )
            next_scan_at = now + max(1.0, args.interval)

        if next_reload_at is not None and now >= next_reload_at:
            _reload_open_pages(context, quiet=args.quiet)
            next_reload_at = now + max(1.0, args.reload_interval)

        if args.once and update_count > 0:
            return update_count
        if deadline is not None and time.monotonic() >= deadline:
            if not args.quiet:
                _print_json(
                    {
                        "event": "eureka_auth_watcher_timeout",
                        "message": "No matching Eureka auth update was captured before timeout.",
                    }
                )
            return update_count

        _browser_wait(context, min(1.0, max(0.1, next_scan_at - time.monotonic())))


def _scan_storage_pages(
    context: Any,
    manager: EurekaTokenManager,
    args: argparse.Namespace,
    cookie_header: str,
    save_candidate: Any,
) -> None:
    min_expires_at = time.time() + manager.settings.token_expiry_skew_seconds
    signature_id = (
        ""
        if args.no_derive_signature_from_cookie
        else signature_id_from_cookie_header(cookie_header)
    )

    for page in list(context.pages):
        if _page_is_closed(page):
            continue
        entries = _read_storage_entries(page)
        if not entries:
            continue
        candidate = imported_auth_from_storage_entries(
            entries,
            cookie_header=cookie_header,
            signature_id=signature_id,
            site_lang=manager.settings.site_lang,
            source_url=f"browser-storage:{page.url}",
            min_expires_at=min_expires_at,
        )
        if candidate is not None and save_candidate(candidate, source="browser-storage"):
            return


def _load_sync_playwright() -> Any:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "Playwright is not installed. Run `uv sync` first, or `uv add playwright` if the "
            "dependency was not installed yet."
        ) from exc
    return sync_playwright


def _launch_persistent_context(playwright: Any, args: argparse.Namespace, profile_path: Path) -> Any:
    launch_kwargs: dict[str, Any] = {"headless": args.headless}
    if args.executable_path:
        launch_kwargs["executable_path"] = args.executable_path
    elif args.browser_channel:
        launch_kwargs["channel"] = args.browser_channel

    try:
        return playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            **launch_kwargs,
        )
    except Exception as exc:
        message = (
            "Failed to start browser for eureka-auth-watcher. "
            "If Google Chrome is not installed, run `uv run playwright install chromium` and "
            "start with `--browser-channel ''`, or pass `--executable-path /path/to/browser`."
        )
        raise SystemExit(f"{message}\nReason: {exc}") from exc


def _request_headers(request: Any) -> Mapping[str, Any]:
    try:
        all_headers = request.all_headers()
        if isinstance(all_headers, Mapping):
            return all_headers
    except Exception:  # noqa: BLE001 - request.headers is a safe fallback.
        return _fallback_request_headers(request)

    return _fallback_request_headers(request)


def _fallback_request_headers(request: Any) -> Mapping[str, Any]:
    headers = getattr(request, "headers", {})
    return headers if isinstance(headers, Mapping) else {}


def _read_cookie_header(context: Any, cookie_urls: Sequence[str]) -> str:
    try:
        cookies = context.cookies(list(cookie_urls))
    except Exception:  # noqa: BLE001 - cookie sync is opportunistic.
        return ""
    return build_cookie_header(cookies if isinstance(cookies, list) else [])


def _read_storage_entries(page: Any) -> list[dict[str, str]]:
    try:
        result = page.evaluate(
            """
            () => {
              const entries = [];
              for (const storeName of ["localStorage", "sessionStorage"]) {
                try {
                  const store = window[storeName];
                  for (let index = 0; index < store.length; index += 1) {
                    const key = store.key(index);
                    entries.push({
                      store: storeName,
                      key: key || "",
                      value: key ? String(store.getItem(key) || "") : ""
                    });
                  }
                } catch (error) {
                  entries.push({store: storeName, key: "__error__", value: String(error)});
                }
              }
              return entries;
            }
            """
        )
    except Exception:  # noqa: BLE001 - some pages deny storage access.
        return []

    if not isinstance(result, list):
        return []
    return [
        {
            "store": _string(item.get("store")),
            "key": _string(item.get("key")),
            "value": _string(item.get("value")),
        }
        for item in result
        if isinstance(item, Mapping)
    ]


def _entry_candidate_text(entry: Mapping[str, Any]) -> list[str]:
    texts = []
    for key in ("key", "value"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            texts.append(value)
    return texts


def _first_page(context: Any) -> Any:
    pages = list(context.pages)
    return pages[0] if pages else context.new_page()


def _navigate_start_page(page: Any, url: str, quiet: bool) -> None:
    if not url:
        return
    try:
        page.goto(url, wait_until="domcontentloaded")
    except Exception as exc:  # noqa: BLE001 - keep browser available for manual navigation.
        if not quiet:
            _print_json({"event": "watcher_warning", "source": "page.goto", "error": str(exc)})


def _reload_open_pages(context: Any, quiet: bool) -> None:
    for page in list(context.pages):
        if _page_is_closed(page):
            continue
        try:
            page.reload(wait_until="domcontentloaded")
        except Exception as exc:  # noqa: BLE001 - page can still be used manually.
            if not quiet:
                _print_json({"event": "watcher_warning", "source": "page.reload", "error": str(exc)})


def _browser_wait(context: Any, seconds: float) -> None:
    page = _first_page(context)
    try:
        page.wait_for_timeout(int(max(0.1, seconds) * 1000))
    except Exception:  # noqa: BLE001 - fallback keeps the loop alive.
        time.sleep(max(0.1, seconds))


def _page_is_closed(page: Any) -> bool:
    try:
        return bool(page.is_closed())
    except Exception:  # noqa: BLE001
        return True


def _is_older_authorization(
    new_authorization: str,
    current_authorization: str,
    new_expires_at: float | None,
) -> bool:
    if not new_authorization or not current_authorization or new_authorization == current_authorization:
        return False

    current_expires_at = jwt_expires_at(current_authorization)
    if current_expires_at is None or new_expires_at is None:
        return False
    return new_expires_at + 1 < current_expires_at


def _print_update(source: str, result: Mapping[str, Any]) -> None:
    expires_at = result.get("expires_at", "")
    _print_json(
        {
            "event": "eureka_auth_updated",
            "source": source,
            "cache_path": result.get("cache_path", ""),
            "has_authorization": result.get("has_authorization", False),
            "has_signature_id": result.get("has_signature_id", False),
            "has_site_lang": result.get("has_site_lang", False),
            "has_cookie": result.get("has_cookie", False),
            "expires_at": expires_at,
            "expires_at_iso": _format_epoch_seconds(expires_at),
            "imported_from_url": result.get("imported_from_url", ""),
        }
    )


def _format_epoch_seconds(value: Any) -> str:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()


def _print_json(payload: Mapping[str, Any]) -> None:
    print(json.dumps(dict(payload), ensure_ascii=False), flush=True)


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


if __name__ == "__main__":
    main()
