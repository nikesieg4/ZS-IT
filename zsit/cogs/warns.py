"""Warn-System: /warn, /warns, /unwarn, Warn-Rollen, Ablauf, Aussendienstsperre."""
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .. import util

log = logging.getLogger("zsit.warns")


class Warns(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cfg = bot.cfg
        self.wcfg = bot.cfg["warns"]
        self.db = bot.db

    async def cog_load(self):
        self.expire_loop.start()

    async def cog_unload(self):
        self.expire_loop.cancel()

    # ---------- Hilfen ----------
    async def warn_roles(self, guild: discord.Guild) -> list:
        """Liefert die Warn-Rollen und legt fehlende an."""
        roles = []
        for name in self.wcfg["warn_rollen"]:
            role = util.find_role(guild, name)
            if role is None and not str(name).isdigit():
                role = await guild.create_role(
                    name=name, color=discord.Color.orange(), reason="Warn-Rolle automatisch angelegt"
                )
            if role is not None:
                roles.append(role)
        return roles

    async def sync_roles(self, member: discord.Member, count: int) -> str:
        """Setzt genau die Warn-Rolle, die zur Anzahl aktiver Warns passt."""
        try:
            roles = await self.warn_roles(member.guild)
            wanted = roles[min(count, len(roles)) - 1] if count > 0 and roles else None
            remove = [r for r in roles if r in member.roles and r != wanted]
            if remove:
                await member.remove_roles(*remove, reason="Warn-Stand aktualisiert")
            if wanted and wanted not in member.roles:
                await member.add_roles(wanted, reason="Warn-Stand aktualisiert")
            return ""
        except discord.Forbidden:
            return "\n⚠️ Warn-Rollen konnten nicht gesetzt werden (Berechtigung **Rollen verwalten** / Rollenposition prüfen)."

    async def get_member(self, guild: discord.Guild, user_id: int):
        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except discord.HTTPException:
                return None
        return member

    def check(self, interaction) -> bool:
        return util.is_staff(interaction.user, self.cfg)

    # ---------- Befehle ----------
    @app_commands.command(name="warn", description="Verwarnt ein Mitglied.")
    @app_commands.describe(mitglied="Wer verwarnt wird", grund="Grund der Verwarnung")
    @app_commands.guild_only()
    async def warn(self, interaction: discord.Interaction, mitglied: discord.Member, grund: str):
        if not self.check(interaction):
            return await interaction.response.send_message(
                "❌ Du hast keine Berechtigung für Verwarnungen.", ephemeral=True
            )
        if mitglied.bot or mitglied.id == interaction.user.id:
            return await interaction.response.send_message(
                "❌ Du kannst weder Bots noch dich selbst verwarnen.", ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        days = self.wcfg["ablauf_tage"]
        warn_id = self.db.add_warn(guild.id, mitglied.id, interaction.user.id, grund, days)
        active = self.db.active_warns(guild.id, mitglied.id)
        count = len(active)
        expires = active[-1]["expires_at"]
        note = await self.sync_roles(mitglied, count)

        embed = discord.Embed(
            title=f"⚠️ Verwarnung #{warn_id}", color=discord.Color.orange(), timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Mitglied", value=f"{mitglied.mention} (`{mitglied.id}`)", inline=False)
        embed.add_field(name="Grund", value=grund, inline=False)
        embed.add_field(name="Aktive Verwarnungen", value=str(count))
        embed.add_field(name="Läuft ab", value=f"<t:{expires}:R>")
        embed.add_field(name="Verwarnt von", value=interaction.user.mention, inline=False)
        embed.set_thumbnail(url=mitglied.display_avatar.url)
        logged = await util.log_to(guild, self.cfg["kanaele"]["warn_log"], embed=embed)

        # Automatische Konsequenz
        threshold = self.wcfg["schwelle"]
        if count >= threshold:
            sperre = util.find_role(guild, self.wcfg["sperr_rolle"])
            if sperre is None:
                note += f"\n⚠️ Rolle `{self.wcfg['sperr_rolle']}` nicht gefunden – keine Sperre vergeben."
            elif sperre not in mitglied.roles:
                try:
                    await mitglied.add_roles(sperre, reason=f"{count} aktive Verwarnungen")
                    alert = discord.Embed(
                        title="🚫 Außendienstsperre verhängt",
                        description=(
                            f"{mitglied.mention} hat **{count} aktive Verwarnungen** und wurde automatisch "
                            f"mit {sperre.mention} belegt.\nDie Sperre wird **nicht** automatisch aufgehoben."
                        ),
                        color=discord.Color.red(),
                        timestamp=discord.utils.utcnow(),
                    )
                    await util.log_to(guild, self.cfg["kanaele"]["warn_log"], embed=alert)
                    note += f"\n🚫 {sperre.name} wurde automatisch vergeben."
                except discord.Forbidden:
                    note += f"\n⚠️ {sperre.name} konnte nicht vergeben werden (Rollenposition prüfen)."

        dm = discord.Embed(
            title=f"Verwarnung – {guild.name}",
            description=(
                f"Du wurdest verwarnt.\n\n**Grund:** {grund}\n"
                f"**Aktive Verwarnungen:** {count}/{threshold}\n"
                f"**Läuft ab:** <t:{expires}:F>\n"
                f"**Verwarnt von:** {interaction.user.display_name}"
            ),
            color=discord.Color.orange(),
        )
        dm_ok = await util.send_dm(mitglied, dm)

        msg = f"✅ {mitglied.mention} wurde verwarnt (#{warn_id}, {count} aktiv).{note}"
        if not logged:
            msg += "\n⚠️ Log-Kanal `moderation` nicht gefunden oder keine Schreibrechte."
        if not dm_ok:
            msg += "\nℹ️ DM konnte nicht zugestellt werden."
        await interaction.followup.send(msg)

    @app_commands.command(name="warns", description="Zeigt die Verwarnungen eines Mitglieds.")
    @app_commands.describe(mitglied="Wessen Verwarnungen angezeigt werden")
    @app_commands.guild_only()
    async def warns(self, interaction: discord.Interaction, mitglied: discord.Member):
        if not self.check(interaction) and mitglied.id != interaction.user.id:
            return await interaction.response.send_message(
                "❌ Du darfst nur deine eigenen Verwarnungen ansehen.", ephemeral=True
            )
        active = self.db.active_warns(interaction.guild.id, mitglied.id)
        old = self.db.inactive_count(interaction.guild.id, mitglied.id)
        embed = discord.Embed(
            title=f"Verwarnungen von {mitglied.display_name}",
            color=discord.Color.orange() if active else discord.Color.green(),
        )
        if not active:
            embed.description = "Keine aktiven Verwarnungen."
        for w in active[:20]:
            embed.add_field(
                name=f"#{w['id']} – läuft ab <t:{w['expires_at']}:R>",
                value=f"{w['reason'][:900]}\nvon <@{w['mod_id']}> am <t:{w['created_at']}:d>",
                inline=False,
            )
        embed.set_footer(text=f"Abgelaufene/aufgehobene Verwarnungen: {old}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="unwarn", description="Hebt eine Verwarnung auf.")
    @app_commands.describe(warn_id="Nummer der Verwarnung (siehe /warns)", grund="Grund der Aufhebung")
    @app_commands.guild_only()
    async def unwarn(self, interaction: discord.Interaction, warn_id: int, grund: str):
        if not self.check(interaction):
            return await interaction.response.send_message(
                "❌ Du hast keine Berechtigung für Verwarnungen.", ephemeral=True
            )
        guild = interaction.guild
        w = self.db.get_warn(guild.id, warn_id)
        if w is None or not w["active"]:
            return await interaction.response.send_message(
                "❌ Keine aktive Verwarnung mit dieser Nummer gefunden.", ephemeral=True
            )
        if w["user_id"] == interaction.user.id and not util.is_admin(interaction.user):
            return await interaction.response.send_message(
                "❌ Du kannst deine eigene Verwarnung nicht aufheben.", ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)
        self.db.remove_warn(warn_id, interaction.user.id, grund)
        count = len(self.db.active_warns(guild.id, w["user_id"]))
        member = await self.get_member(guild, w["user_id"])
        note = await self.sync_roles(member, count) if member else ""

        embed = discord.Embed(
            title=f"✅ Verwarnung #{warn_id} aufgehoben", color=discord.Color.green(), timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Mitglied", value=f"<@{w['user_id']}>", inline=False)
        embed.add_field(name="Ursprünglicher Grund", value=w["reason"][:1000], inline=False)
        embed.add_field(name="Grund der Aufhebung", value=grund, inline=False)
        embed.add_field(name="Aktive Verwarnungen", value=str(count))
        embed.add_field(name="Aufgehoben von", value=interaction.user.mention)
        await util.log_to(guild, self.cfg["kanaele"]["warn_log"], embed=embed)
        await interaction.followup.send(
            f"✅ Verwarnung #{warn_id} aufgehoben ({count} aktiv). "
            f"Eine bestehende Außendienstsperre bleibt bestehen und muss manuell entfernt werden.{note}"
        )

    # ---------- Ablauf ----------
    @tasks.loop(minutes=10)
    async def expire_loop(self):
        try:
            for w in self.db.pop_expired():
                guild = self.bot.get_guild(w["guild_id"])
                if guild is None:
                    continue
                count = len(self.db.active_warns(guild.id, w["user_id"]))
                member = await self.get_member(guild, w["user_id"])
                if member:
                    await self.sync_roles(member, count)
                embed = discord.Embed(
                    title=f"⌛ Verwarnung #{w['id']} abgelaufen",
                    description=f"<@{w['user_id']}> – noch **{count}** aktive Verwarnung(en).\n**Grund war:** {w['reason'][:1000]}",
                    color=discord.Color.light_grey(),
                    timestamp=discord.utils.utcnow(),
                )
                await util.log_to(guild, self.cfg["kanaele"]["warn_log"], embed=embed)
        except Exception:
            log.exception("Fehler beim Ablauf von Verwarnungen")

    @expire_loop.before_loop
    async def before_expire(self):
        await self.bot.wait_until_ready()
