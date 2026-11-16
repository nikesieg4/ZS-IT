"""Zentraler Service Informationstechnik – Discord-Bot der Berufsfeuerwehr."""
import logging
import os
import sys
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from zsit import config
from zsit.cogs.ranks import Ranks
from zsit.cogs.tickets import Tickets
from zsit.cogs.warns import Warns
from zsit.db import Database

BASE = Path(__file__).resolve().parent
log = logging.getLogger("zsit")


def load_env():
    """Liest .env, falls die Variablen nicht schon (z. B. von systemd) gesetzt sind."""
    env = BASE / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class ZSITBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # fuer Ticket-Transkripte
        super().__init__(command_prefix=commands.when_mentioned, intents=intents, help_command=None)
        self.cfg = config.load()
        self.db = Database(BASE / "data" / "bot.sqlite3")
        self.synced = False

    async def setup_hook(self):
        await self.add_cog(Tickets(self))
        await self.add_cog(Ranks(self))
        await self.add_cog(Warns(self))
        self.tree.on_error = self.on_tree_error

    async def sync_guild(self, guild: discord.Guild):
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        log.info("Befehle synchronisiert für %s", guild.name)

    async def on_ready(self):
        log.info("Angemeldet als %s (%s)", self.user, self.user.id)
        if not self.synced:
            self.synced = True
            for guild in self.guilds:
                await self.sync_guild(guild)

    async def on_guild_join(self, guild: discord.Guild):
        await self.sync_guild(guild)

    async def on_tree_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        log.exception("Fehler in /%s", interaction.command.name if interaction.command else "?", exc_info=error)
        msg = "❌ Es ist ein Fehler aufgetreten. Bitte melde das dem ZS-IT."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except discord.HTTPException:
            pass


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_env()
    token = os.environ.get("DISCORD_TOKEN", "").strip()
    if not token or token.startswith("hier-"):
        sys.exit("DISCORD_TOKEN fehlt. Bitte in der Datei .env eintragen.")
    try:
        ZSITBot().run(token, log_handler=None)
    except discord.LoginFailure:
        sys.exit("Der Bot-Token ist ungültig. Bitte in .env korrigieren.")
    except discord.PrivilegedIntentsRequired:
        sys.exit(
            "Bitte im Discord Developer Portal unter Bot -> Privileged Gateway Intents "
            "den Schalter 'Message Content Intent' aktivieren."
        )


if __name__ == "__main__":
    main()
