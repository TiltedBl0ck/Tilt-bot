"""
Tilt-bot - Main entry point
Discord bot with moderation, utility, AI, and management features.
"""
from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Dependency preflight — runs before ANY third-party import.
# If a package is missing or the wrong version, the bot exits with a clear
# error message instead of throwing a cryptic ImportError later.
# Set AUTO_INSTALL_DEPS=1 in your .env / environment to auto-install instead.
# ─────────────────────────────────────────────────────────────────────────────
import os
import sys
import subprocess
from pathlib import Path

def _run_pip_install(req_path: Path) -> int:
    """Run pip install -r <req_path> using the current interpreter."""
    return subprocess.call(
        [sys.executable, "-m", "pip", "install", "-r", str(req_path)],
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

def check_requirements(req_file: str = "requirements.txt") -> None:
    """
    Parse requirements.txt, check every package against importlib.metadata,
    and either exit(1) with clear instructions or auto-install (if
    AUTO_INSTALL_DEPS=1 is set in the environment / .env).

    Supports:
      - Plain names           e.g. aiohttp
      - Version specifiers    e.g. aiohttp>=3.8.0
      - Extras                e.g. google-genai[aiohttp]>=1.0.0
      - Environment markers   e.g. pywin32>=305; sys_platform == "win32"
      - Comments / blank lines
    """
    from importlib import metadata as _meta

    req_path = Path(req_file)
    if not req_path.exists():
        print(f"[deps] ⚠  requirements file not found: {req_path.resolve()}", file=sys.stderr)
        return

    # Use packaging.requirements for robust parsing when available.
    try:
        from packaging.requirements import Requirement as _Req
        _has_packaging = True
    except ImportError:
        _has_packaging = False

    missing: list[str] = []
    incompatible: list[str] = []
    unparsed: list[str] = []

    for raw in req_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()

        # Skip blanks, comments, and pip options
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-r ", "--requirement", "--index", "--extra-index", "--find-links", "-e ")):
            unparsed.append(line)
            continue

        if _has_packaging:
            try:
                req = _Req(line)
            except Exception:
                unparsed.append(line)
                continue

            # Skip if environment marker doesn't apply
            if req.marker is not None and not req.marker.evaluate():
                continue

            try:
                installed = _meta.version(req.name)
            except _meta.PackageNotFoundError:
                missing.append(str(req))
                continue

            if req.specifier and installed not in req.specifier:
                incompatible.append(f"{req}  (installed: {installed})")

        else:
            # Minimal fallback: name-only check, no version comparison
            name = line.split(";")[0].strip()
            # Strip extras and specifiers
            import re as _re
            name = _re.split(r"[\[>=<!~\s]", name)[0].strip()
            if not name:
                unparsed.append(line)
                continue
            try:
                _meta.version(name)
            except _meta.PackageNotFoundError:
                missing.append(line)

    # ── All good ──
    if not missing and not incompatible:
        if unparsed:
            print(f"[deps] ✅ OK  ({len(unparsed)} line(s) skipped — pip options or -r includes)")
        else:
            print("[deps] ✅ All requirements satisfied.")
        return

    # ── Something's wrong — report it ──
    print("\n[deps] ❌ Dependency check failed:", file=sys.stderr)
    if missing:
        print("\n  Missing packages:", file=sys.stderr)
        for m in missing:
            print(f"    • {m}", file=sys.stderr)
    if incompatible:
        print("\n  Version mismatches:", file=sys.stderr)
        for b in incompatible:
            print(f"    • {b}", file=sys.stderr)

    auto = os.environ.get("AUTO_INSTALL_DEPS", "0").strip() == "1"
    if auto:
        print("\n[deps] AUTO_INSTALL_DEPS=1 — running pip install ...", file=sys.stderr)
        code = _run_pip_install(req_path)
        if code != 0:
            print("[deps] pip install failed. Fix manually and retry.", file=sys.stderr)
            raise SystemExit(code)
        print("[deps] ✅ Dependencies installed. Restarting...", file=sys.stderr)
        # Re-exec so new packages are importable in this process
        raise SystemExit(
            subprocess.call([sys.executable] + sys.argv)
        )

    print(f"\n[deps] Fix by running:", file=sys.stderr)
    print(f"  {sys.executable} -m pip install -r {req_path}", file=sys.stderr)
    print("  Or set AUTO_INSTALL_DEPS=1 to let the bot handle it.", file=sys.stderr)
    raise SystemExit(1)


# Load .env early so AUTO_INSTALL_DEPS can be read from it
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=False)
except ImportError:
    pass  # python-dotenv missing — checked below along with everything else

check_requirements("requirements.txt")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Normal imports — safe to do now that deps are verified.
# ─────────────────────────────────────────────────────────────────────────────
import asyncio
import json
import logging
from logging.handlers import RotatingFileHandler

import discord
from discord.ext import commands
from dotenv import load_dotenv

import cogs.utils.db as db_utils

# ── Logging Setup ──────────────────────────────────────────────────────────
# RotatingFileHandler prevents disk exhaustion on long-running bots.
Path("configs").mkdir(exist_ok=True)  # ensure log dir exists before opening

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s: %(message)s",
    handlers=[
        RotatingFileHandler(
            "configs/bot.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        ),
        logging.StreamHandler(),
    ],
)
logging.getLogger("discord.http").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Bot class
# ─────────────────────────────────────────────────────────────────────────────
class TiltBot(commands.Bot):
    """The main bot class."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(command_prefix="!", intents=intents)

        self.version = "N/A"
        config_path = Path(__file__).parent / "configs" / "config.json"
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self.version = json.load(f).get("bot", {}).get("version", "N/A")
        except FileNotFoundError:
            logger.warning("config.json not found — using default version.")
        except json.JSONDecodeError:
            logger.error("config.json is malformed. Skipping version load.")

    async def setup_hook(self) -> None:
        """Async setup — db init, cog loading, slash command sync."""
        logger.info("--- Setting up the bot ---")

        # Initialise database first
        try:
            await db_utils.init_db()
            logger.info("Database ready.")
        except Exception as exc:
            logger.critical(f"Database failed to initialise: {exc}", exc_info=True)
            await self.close()
            return

        # Load the main handler cog
        try:
            await self.load_extension("cogs.handler")
            logger.info("Handler cog loaded.")
        except commands.ExtensionError as exc:
            logger.critical(f"Could not load handler cog: {exc}", exc_info=True)
            await self.close()
            return

        # Sync slash commands
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} application command(s).")
        except Exception as exc:
            logger.error(f"Command sync failed: {exc}", exc_info=True)

    async def on_ready(self) -> None:
        """Bot is fully online."""
        if not self.user:
            return
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        activity = f"{len(self.guilds)} servers | /help"
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.watching, name=activity
            ),
        )

    async def close(self) -> None:
        """Clean shutdown — close DB pool before disconnecting."""
        await db_utils.close_pool()
        await super().close()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
async def main() -> None:
    """Load .env, validate token, start the bot."""
    load_dotenv(dotenv_path=Path(__file__).parent / ".env")

    token = os.getenv("BOT_TOKEN")
    if not token:
        logger.critical("BOT_TOKEN not found in .env — cannot start.")
        return

    bot = TiltBot()
    try:
        await bot.start(token)
    except Exception as exc:
        logger.critical(f"Fatal error during bot.start(): {exc}", exc_info=True)
    finally:
        if bot and not bot.is_closed():
            await bot.close()
        logging.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as exc:
        logger.critical(f"Critical top-level error: {exc}", exc_info=True)