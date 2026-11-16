"""Rang-System: /rank, /uprank, /downrank mit freier Rollenwahl."""
import discord
from discord import app_commands
from discord.ext import commands

from .. import util


class Ranks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cfg = bot.cfg

    # ---------- Hilfen ----------
    def rank_roles(self, guild: discord.Guild) -> list:
        """Rangrollen des Servers in der Reihenfolge der Konfiguration (niedrig -> hoch)."""
        return util.find_roles(guild, self.cfg["rang_rollen"])

    def rank_index(self, member: discord.Member, ranks: list) -> int:
        """Index des hoechsten Rangs des Mitglieds, -1 ohne Rang."""
        ids = {r.id for r in member.roles}
        best = -1
        for i, role in enumerate(ranks):
            if role.id in ids:
                best = i
        return best

    async def rank_autocomplete(self, interaction: discord.Interaction, current: str):
        names = [r.name for r in reversed(self.rank_roles(interaction.guild))]
        hits = [n for n in names if current.lower() in n.lower()]
        return [app_commands.Choice(name=n, value=n) for n in hits[:25]]

    async def change(self, interaction, member: discord.Member, rang: str, grund: str, mode: str):
        guild = interaction.guild
        actor = interaction.user
        if not util.is_staff(actor, self.cfg):
            return await interaction.response.send_message(
                "❌ Du hast keine Berechtigung für Rangänderungen.", ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)

        ranks = self.rank_roles(guild)
        target = discord.utils.get(ranks, name=rang)
        if target is None:
            return await interaction.followup.send(
                "❌ Diesen Rang kenne ich nicht. Bitte einen Rang aus der Vorschlagsliste wählen."
            )
        if member.bot:
            return await interaction.followup.send("❌ Bots haben keinen Rang.")
        if member.id == actor.id and not util.is_admin(actor):
            return await interaction.followup.send("❌ Du kannst deinen eigenen Rang nicht ändern.")

        target_idx = ranks.index(target)
        old_idx = self.rank_index(member, ranks)
        old = ranks[old_idx] if old_idx >= 0 else None

        if old_idx == target_idx:
            return await interaction.followup.send(f"ℹ️ {member.mention} hat diesen Rang bereits.")
        if mode == "up" and target_idx < old_idx:
            return await interaction.followup.send(
                "❌ Der gewählte Rang liegt unter dem aktuellen Rang. Nutze dafür `/downrank`."
            )
        if mode == "down" and target_idx > old_idx:
            return await interaction.followup.send(
                "❌ Der gewählte Rang liegt über dem aktuellen Rang. Nutze dafür `/uprank`."
            )

        if self.cfg.get("hierarchie_pruefung", True) and not util.is_admin(actor):
            actor_idx = self.rank_index(actor, ranks)
            if old_idx >= actor_idx or target_idx >= actor_idx:
                return await interaction.followup.send(
                    "❌ Du kannst nur Mitglieder unter deinem eigenen Rang ändern "
                    "und nur Ränge unter deinem eigenen vergeben."
                )

        me = guild.me
        blocked = [r for r in ranks if r >= me.top_role and (r == target or r in member.roles)]
        if blocked:
            return await interaction.followup.send(
                f"❌ Meine Bot-Rolle steht unter **{blocked[0].name}**. Bitte ziehe die Rolle "
                f"**{me.top_role.name}** in den Servereinstellungen über alle Rangrollen."
            )

        direction = "Beförderung" if target_idx > old_idx else "Degradierung"
        if old is None:
            direction = "Einstufung"
        reason = f"{direction} durch {actor} – {grund}"[:500]
        try:
            remove = [r for r in ranks if r in member.roles and r != target]
            if remove:
                await member.remove_roles(*remove, reason=reason)
            await member.add_roles(target, reason=reason)
        except discord.Forbidden:
            return await interaction.followup.send(
                "❌ Mir fehlt die Berechtigung **Rollen verwalten** oder meine Rolle steht zu tief."
            )

        # Nickname "[Kuerzel] Name"
        nick_note = ""
        new_nick = util.nickname_with_rank(member.display_name, util.kuerzel(target.name))
        if new_nick != member.display_name:
            try:
                await member.edit(nick=new_nick, reason=reason)
            except discord.Forbidden:
                nick_note = "\n⚠️ Nickname konnte nicht geändert werden (Server-Inhaber oder Rolle über dem Bot)."

        color = discord.Color.green() if target_idx > old_idx else discord.Color.red()
        embed = discord.Embed(title=f"↕️ {direction}", color=color, timestamp=discord.utils.utcnow())
        embed.add_field(name="Mitglied", value=f"{member.mention} (`{member.id}`)", inline=False)
        embed.add_field(name="Alter Rang", value=old.mention if old else "—")
        embed.add_field(name="Neuer Rang", value=target.mention)
        embed.add_field(name="Grund", value=grund, inline=False)
        embed.add_field(name="Durchgeführt von", value=actor.mention, inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        logged = await util.log_to(guild, self.cfg["kanaele"]["rang_log"], embed=embed)

        dm = discord.Embed(
            title=f"{direction} – {guild.name}",
            description=(
                f"Dein Rang wurde geändert.\n\n"
                f"**Alter Rang:** {old.name if old else '—'}\n"
                f"**Neuer Rang:** {target.name}\n"
                f"**Grund:** {grund}\n"
                f"**Durchgeführt von:** {actor.display_name}"
            ),
            color=color,
        )
        dm_ok = await util.send_dm(member, dm)

        msg = f"✅ {member.mention}: {old.name if old else '—'} → **{target.name}**{nick_note}"
        if not logged:
            msg += "\n⚠️ Log-Kanal `rang-log` nicht gefunden oder keine Schreibrechte."
        if not dm_ok:
            msg += "\nℹ️ DM konnte nicht zugestellt werden (DMs geschlossen)."
        await interaction.followup.send(msg)

    # ---------- Befehle ----------
    @app_commands.command(name="uprank", description="Befördert ein Mitglied auf einen höheren Rang.")
    @app_commands.describe(mitglied="Wer befördert wird", rang="Neuer Rang", grund="Grund der Beförderung")
    @app_commands.autocomplete(rang=rank_autocomplete)
    @app_commands.guild_only()
    async def uprank(self, interaction: discord.Interaction, mitglied: discord.Member, rang: str, grund: str):
        await self.change(interaction, mitglied, rang, grund, "up")

    @app_commands.command(name="downrank", description="Degradiert ein Mitglied auf einen niedrigeren Rang.")
    @app_commands.describe(mitglied="Wer degradiert wird", rang="Neuer Rang", grund="Grund der Degradierung")
    @app_commands.autocomplete(rang=rank_autocomplete)
    @app_commands.guild_only()
    async def downrank(self, interaction: discord.Interaction, mitglied: discord.Member, rang: str, grund: str):
        await self.change(interaction, mitglied, rang, grund, "down")

    @app_commands.command(name="rank", description="Setzt den Rang eines Mitglieds direkt (z. B. Einstellung).")
    @app_commands.describe(mitglied="Wessen Rang gesetzt wird", rang="Neuer Rang", grund="Grund")
    @app_commands.autocomplete(rang=rank_autocomplete)
    @app_commands.guild_only()
    async def rank(self, interaction: discord.Interaction, mitglied: discord.Member, rang: str, grund: str):
        await self.change(interaction, mitglied, rang, grund, "set")
