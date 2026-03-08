"""Main macOS menu bar application.

Data sources:
  1. Claude CLI credentials (Keychain) — plan tier detection
  2. Claude CLI stats-cache.json — local usage history
  3. claude.ai session cookie — live rate limit percentages
"""

import threading
from datetime import datetime

import rumps

from .auth import (
    delete_session_key,
    detect_tier_from_cli,
    extract_chrome_session_key,
    get_cli_credentials,
    get_cli_username,
    get_session_cookie_instructions,
    get_session_key,
    has_cli_credentials,
    open_claude_login,
    open_claude_settings,
    save_session_key,
    validate_session,
)
from .config import APP_NAME, AUTO_REFRESH_INTERVAL, TIERS
from .usage import (
    build_bar,
    fetch_claude_ai_usage,
    format_tokens,
    get_cli_stats,
    get_reset_countdown,
    shorten_model_name,
)


def _noop(_):
    """No-op callback to keep menu items enabled (readable text)."""
    pass


class ClaudeUsageApp(rumps.App):
    def __init__(self):
        super().__init__(APP_NAME, title="\u2728", quit_button=None)
        self.tier = "pro"
        self.username = None
        self.org_id = None
        self.live_usage = None      # From claude.ai API
        self.cli_stats = None       # From stats-cache.json
        self.last_refresh = None
        self.is_refreshing = False
        self.has_session = False

        self._detect_on_launch()
        self._build_menu()

        self.timer = rumps.Timer(self._auto_refresh, AUTO_REFRESH_INTERVAL)
        self.timer.start()

    # --- Startup ---

    def _detect_on_launch(self):
        """Detect CLI credentials and existing session on launch."""
        # Detect tier from CLI
        tier = detect_tier_from_cli()
        if tier:
            self.tier = tier

        self.username = get_cli_username()

        # Check for existing session key
        session_key = get_session_key()
        if session_key:
            result = validate_session(session_key)
            if result:
                self.org_id = result["org_id"]
                self.has_session = True

        # Try auto-extracting from Chrome if no session
        if not self.has_session:
            chrome_key = extract_chrome_session_key()
            if chrome_key:
                result = validate_session(chrome_key)
                if result:
                    save_session_key(chrome_key)
                    self.org_id = result["org_id"]
                    self.has_session = True

        # Load CLI stats (always available if CLI installed)
        self.cli_stats = get_cli_stats()

        # Kick off live data fetch
        if self.has_session:
            self._refresh_data()
        elif self.cli_stats:
            self._update_title_icon()

    # --- Menu ---

    def _build_menu(self):
        self.menu.clear()

        tier_info = TIERS.get(self.tier, TIERS["pro"])
        resets = get_reset_countdown()

        # Header
        if self.username:
            header = f"{self.username} - {tier_info['name']} ({tier_info['price']})"
        else:
            header = f"{tier_info['name']} ({tier_info['price']})"
        if has_cli_credentials():
            header += "  \u2713"  # checkmark

        self.menu.add(rumps.MenuItem(header, callback=_noop))
        self.menu.add(rumps.separator)

        # ---- Live usage (from claude.ai session) ----
        if self.live_usage:
            self.menu.add(rumps.MenuItem("  Your usage limits", callback=_noop))
            self.menu.add(rumps.separator)

            for key in ("session", "weekly_all", "weekly_sonnet"):
                bucket = self.live_usage[key]
                pct = bucket["percent"]
                reset = bucket["reset_at"]
                label = bucket["label"]

                self.menu.add(rumps.MenuItem(f"  {label}", callback=_noop))
                self.menu.add(rumps.MenuItem(
                    f"    {build_bar(pct)}  {pct}% used",
                    callback=_noop,
                ))
                if reset:
                    self.menu.add(rumps.MenuItem(f"    Resets {reset}", callback=_noop))
                self.menu.add(rumps.separator)

            # Extra usage info
            eu = self.live_usage.get("extra_usage")
            if eu and eu.get("enabled"):
                limit_str = f"${eu['monthly_limit']}" if eu["monthly_limit"] else "unlimited"
                self.menu.add(rumps.MenuItem(
                    f"  Extra usage: ${eu['used_credits']:.2f} / {limit_str}",
                    callback=_noop,
                ))
                self.menu.add(rumps.separator)

        elif self.has_session:
            self.menu.add(rumps.MenuItem("  Loading live usage...", callback=_noop))
            self.menu.add(rumps.separator)

        else:
            # No session — show resets based on time
            self.menu.add(rumps.MenuItem("  Usage limits (connect for live data)", callback=_noop))
            self.menu.add(rumps.separator)
            self.menu.add(rumps.MenuItem(f"    Daily resets in:  {resets['daily']}", callback=_noop))
            self.menu.add(rumps.MenuItem(f"    Weekly resets in: {resets['weekly']}", callback=_noop))
            self.menu.add(rumps.separator)

        # ---- CLI Stats (always available if CLI installed) ----
        if self.cli_stats:
            self.menu.add(rumps.MenuItem("  Claude Code activity", callback=_noop))
            self.menu.add(rumps.separator)

            stats = self.cli_stats
            self.menu.add(rumps.MenuItem(
                f"    Today:  {stats['today_messages']} msgs, "
                f"{stats['today_sessions']} sessions, "
                f"{stats['today_tools']} tools",
                callback=_noop,
            ))
            self.menu.add(rumps.MenuItem(
                f"    Week:   {stats['week_messages']} msgs, "
                f"{stats['week_sessions']} sessions",
                callback=_noop,
            ))

            # Token usage by model (today)
            if stats["today_tokens_by_model"]:
                self.menu.add(rumps.separator)
                self.menu.add(rumps.MenuItem("    Tokens today by model:", callback=_noop))
                for model, count in sorted(
                    stats["today_tokens_by_model"].items(),
                    key=lambda x: -x[1],
                ):
                    name = shorten_model_name(model)
                    self.menu.add(rumps.MenuItem(
                        f"      {name}: {format_tokens(count)}",
                        callback=_noop,
                    ))

            # Token usage by model (week)
            if stats["week_tokens_by_model"]:
                self.menu.add(rumps.separator)
                self.menu.add(rumps.MenuItem("    Tokens this week by model:", callback=_noop))
                for model, count in sorted(
                    stats["week_tokens_by_model"].items(),
                    key=lambda x: -x[1],
                ):
                    name = shorten_model_name(model)
                    self.menu.add(rumps.MenuItem(
                        f"      {name}: {format_tokens(count)}",
                        callback=_noop,
                    ))

            self.menu.add(rumps.separator)
            self.menu.add(rumps.MenuItem(
                f"    All time: {stats['total_messages']} msgs, "
                f"{stats['total_sessions']} sessions",
                callback=_noop,
            ))

        self.menu.add(rumps.separator)

        # ---- Timestamp ----
        if self.last_refresh:
            ts = self.last_refresh.strftime("%H:%M:%S")
            self.menu.add(rumps.MenuItem(f"Last updated: {ts}", callback=_noop))
        self.menu.add(rumps.separator)

        # ---- Actions ----
        refresh_label = "Refreshing..." if self.is_refreshing else "Refresh Now"
        self.menu.add(rumps.MenuItem(refresh_label, callback=self._on_refresh))
        self.menu.add(rumps.MenuItem("Open claude.ai/settings/usage", callback=self._on_open_settings))

        # Tier selector
        tier_menu = rumps.MenuItem("Tier")
        for key, info in TIERS.items():
            check = "\u2713 " if key == self.tier else "   "
            tier_menu.add(rumps.MenuItem(
                f"{check}{info['name']} ({info['price']})",
                callback=self._make_tier_callback(key),
            ))
        self.menu.add(tier_menu)

        self.menu.add(rumps.separator)

        # Session management
        if self.has_session:
            self.menu.add(rumps.MenuItem("Disconnect Session", callback=self._on_disconnect))
        else:
            self.menu.add(rumps.MenuItem(
                "Connect claude.ai Session...",
                callback=self._on_connect_session,
            ))

        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("Quit", callback=self._on_quit))

    # --- Data refresh ---

    def _refresh_data(self):
        if self.is_refreshing:
            return
        self.is_refreshing = True
        self._build_menu()

        def _fetch():
            try:
                # Refresh CLI stats
                self.cli_stats = get_cli_stats()

                # Fetch live usage if we have a session
                if self.has_session:
                    session_key = get_session_key()
                    if session_key and self.org_id:
                        live = fetch_claude_ai_usage(session_key, self.org_id)
                        if live and live.get("expired"):
                            # Session expired — disconnect automatically
                            delete_session_key()
                            self.has_session = False
                            self.org_id = None
                            self.live_usage = None
                        elif live:
                            self.live_usage = live

                self.last_refresh = datetime.now()
                self._update_title_icon()
            finally:
                self.is_refreshing = False
                self._build_menu()

        threading.Thread(target=_fetch, daemon=True).start()

    def _update_title_icon(self):
        if self.live_usage:
            pct = self.live_usage["session"]["percent"]
        elif self.cli_stats and self.cli_stats["today_messages"] > 0:
            # Rough estimate: assume ~100 msgs/day for Pro, scale by tier
            tier_daily = {"free": 25, "pro": 100, "max_5x": 500, "max_20x": 2000}
            limit = tier_daily.get(self.tier, 100)
            pct = min(int(self.cli_stats["today_messages"] / limit * 100), 100)
        else:
            self.title = "\u2728"
            return

        if pct > 80:
            self.title = "\U0001F7E0"   # Orange
        elif pct > 50:
            self.title = "\U0001F7E1"   # Yellow
        else:
            self.title = "\U0001F7E2"   # Green

    def _auto_refresh(self, _):
        self._refresh_data()

    # --- Callbacks ---

    def _on_refresh(self, _):
        self._refresh_data()

    def _make_tier_callback(self, tier_key):
        def callback(_):
            self.tier = tier_key
            self._build_menu()
            self._update_title_icon()
        return callback

    def _on_open_settings(self, _):
        open_claude_settings()

    def _on_connect_session(self, _):
        # First try auto-extract from Chrome
        chrome_key = extract_chrome_session_key()
        if chrome_key:
            result = validate_session(chrome_key)
            if result:
                save_session_key(chrome_key)
                self.org_id = result["org_id"]
                self.has_session = True
                rumps.notification(
                    APP_NAME,
                    "Connected automatically!",
                    "Session extracted from Chrome cookies.",
                )
                self._build_menu()
                self._refresh_data()
                return

        # Manual flow
        instructions = get_session_cookie_instructions()
        window = rumps.Window(
            message=instructions,
            title="Connect claude.ai Session",
            default_text="",
            ok="Connect",
            cancel="Cancel",
            dimensions=(380, 24),
        )
        response = window.run()
        if not response.clicked or not response.text.strip():
            return

        session_key = response.text.strip().strip("'\"")
        result = validate_session(session_key)
        if result:
            save_session_key(session_key)
            self.org_id = result["org_id"]
            self.has_session = True
            rumps.notification(APP_NAME, "Connected!", f"Org: {result.get('name', result['org_id'][:12])}")
            self._build_menu()
            self._refresh_data()
        else:
            rumps.notification(
                APP_NAME,
                "Connection failed",
                "Invalid or expired session cookie. Try again.",
            )

    def _on_disconnect(self, _):
        delete_session_key()
        self.has_session = False
        self.org_id = None
        self.live_usage = None
        self.title = "\u2728"
        self._build_menu()

    def _on_quit(self, _):
        rumps.quit_application()


def _set_process_name():
    """Set the macOS process name so notifications show 'Claude Usage Monitor' instead of 'Python'."""
    try:
        from Foundation import NSBundle
        bundle = NSBundle.mainBundle()
        info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
        if info:
            info["CFBundleName"] = APP_NAME
    except ImportError:
        pass


def main():
    _set_process_name()
    ClaudeUsageApp().run()
