"""Ticket-System: Panel mit Kategorien, privater Kanal, Uebernehmen/Schliessen, Transkript."""
import io
import re

import discord
from discord import app_commands
from discord.ext import commands

from .. import util


class PanelView(discord.ui.View):
    """Dauerhafte Ansicht mit dem Kategorie-Auswahlmenue."""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        select = discord.ui.Select(
            custom_id="zsit:ticket:select",
            placeholder="Kategorie wählen, um ein Ticket zu öffnen …",
            options=[
                discord.SelectOption(
                    label=c["label"], value=c["id"], description=c.get("beschreibung"), emoji=c.get("emoji")
                )
                for c in cog.tcfg["kategorien"]
            ],
        )
        select.callback = self.on_select
        self.select = select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        await self.cog.open_ticket(interaction, self.select.values[0])


class TicketView(discord.ui.View):
    """Dauerhafte Buttons im Ticket-Kanal."""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Übernehmen", emoji="🙋", style=discord.ButtonStyle.primary, custom_id="zsit:ticket:claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.claim_ticket(interaction)

    @discord.ui.button(label="Schließen", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="zsit:ticket:close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.ask_close(interaction)


class ConfirmClose(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=60)
        self.cog = cog

    @discord.ui.button(label="Ja, Ticket schließen", style=discord.ButtonStyle.danger)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.close_ticket(interaction)


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cfg = bot.cfg
        self.tcfg = bot.cfg["tickets"]
        self.db = bot.db

    async def cog_load(self):
        self.bot.add_view(PanelView(self))
        self.bot.add_view(TicketView(self))

    # ---------- Hilfen ----------
    def category_cfg(self, cat_id: str):
        for c in self.tcfg["kategorien"]:
            if c["id"] == cat_id:
                return c
        return None

    def is_ticket_staff(self, member: discord.Member, cat_id: str) -> bool:
        c = self.category_cfg(cat_id)
        return util.is_admin(member) or (c is not None and util.has_any_role(member, c["rollen"]))

    async def ticket_category(self, guild: discord.Guild) -> discord.CategoryChannel:
        name = self.tcfg["kategorie_name"]
        if str(name).isdigit():
            cat = guild.get_channel(int(name))
            if isinstance(cat, discord.CategoryChannel):
                return cat
        cat = discord.utils.get(guild.categories, name=name)
        if cat is None:
            cat = await guild.create_category(
                name,
                overwrites={
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True),
                },
                reason="Ticket-Kategorie automatisch angelegt",
            )
        return cat

    # ---------- Ablauf ----------
    async def open_ticket(self, interaction: discord.Interaction, cat_id: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild, user = interaction.guild, interaction.user
        try:  # Auswahl im Panel zuruecksetzen
            await interaction.message.edit(view=PanelView(self))
        except discord.HTTPException:
            pass

        c = self.category_cfg(cat_id)
        if c is None:
            return await interaction.followup.send("❌ Diese Kategorie gibt es nicht mehr.")

        existing = self.db.open_ticket_of(guild.id, user.id, cat_id)
        if existing:
            channel = guild.get_channel(existing["channel_id"] or 0)
            if channel:
                return await interaction.followup.send(
                    f"ℹ️ Du hast in dieser Kategorie bereits ein offenes Ticket: {channel.mention}"
                )
            self.db.close_ticket(existing["id"])  # Kanal wurde von Hand geloescht

        ticket_id = self.db.create_ticket(guild.id, user.id, cat_id)
        staff_roles = util.find_roles(guild, c["rollen"])
        access = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True
        )
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
                manage_channels=True, attach_files=True, embed_links=True,
            ),
            user: access,
        }
        for role in staff_roles:
            overwrites[role] = access
        safe = re.sub(r"[^a-z0-9]+", "-", user.name.lower()).strip("-")[:20] or "user"
        try:
            channel = await guild.create_text_channel(
                f"ticket-{ticket_id:04d}-{safe}",
                category=await self.ticket_category(guild),
                overwrites=overwrites,
                topic=f"Ticket #{ticket_id} | {c['label']} | von {user} ({user.id})",
                reason=f"Ticket #{ticket_id} von {user}",
            )
        except discord.Forbidden:
            self.db.close_ticket(ticket_id)
            return await interaction.followup.send(
                "❌ Mir fehlt die Berechtigung **Kanäle verwalten** (bzw. **Rollen verwalten** für Kanalrechte)."
            )
        self.db.set_ticket_channel(ticket_id, channel.id)

        embed = discord.Embed(
            title=f"{c.get('emoji', '🎫')} Ticket #{ticket_id} – {c['label']}",
            description=(
                f"Hallo {user.mention}, bitte schildere dein Anliegen so genau wie möglich.\n"
                "Ein zuständiges Teammitglied meldet sich so bald wie möglich."
            ),
            color=discord.Color.red(),
        )
        embed.set_footer(text="Mit „Schließen“ wird das Ticket archiviert und der Kanal gelöscht.")
        pings = " ".join(r.mention for r in staff_roles)
        await channel.send(
            content=f"{user.mention} {pings}".strip(),
            embed=embed,
            view=TicketView(self),
            allowed_mentions=discord.AllowedMentions(users=True, roles=True),
        )
        await interaction.followup.send(f"✅ Dein Ticket wurde erstellt: {channel.mention}")

    async def claim_ticket(self, interaction: discord.Interaction):
        t = self.db.ticket_by_channel(interaction.channel.id)
        if t is None:
            return await interaction.response.send_message("❌ Das ist kein offenes Ticket.", ephemeral=True)
        if not self.is_ticket_staff(interaction.user, t["category"]):
            return await interaction.response.send_message(
                "❌ Nur das zuständige Team kann Tickets übernehmen.", ephemeral=True
            )
        if t["claimed_by"]:
            return await interaction.response.send_message(
                f"ℹ️ Dieses Ticket wurde bereits von <@{t['claimed_by']}> übernommen.", ephemeral=True
            )
        self.db.claim_ticket(t["id"], interaction.user.id)
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"🙋 {interaction.user.mention} hat das Ticket übernommen.", color=discord.Color.blue()
            )
        )

    async def ask_close(self, interaction: discord.Interaction):
        t = self.db.ticket_by_channel(interaction.channel.id)
        if t is None:
            return await interaction.response.send_message("❌ Das ist kein offenes Ticket.", ephemeral=True)
        if interaction.user.id != t["user_id"] and not self.is_ticket_staff(interaction.user, t["category"]):
            return await interaction.response.send_message(
                "❌ Du darfst dieses Ticket nicht schließen.", ephemeral=True
            )
        await interaction.response.send_message(
            "Ticket wirklich schließen? Der Kanal wird gelöscht, ein Transkript wird gespeichert.",
            view=ConfirmClose(self),
            ephemeral=True,
        )

    async def close_ticket(self, interaction: discord.Interaction):
        channel = interaction.channel
        t = self.db.ticket_by_channel(channel.id)
        if t is None:
            return await interaction.response.send_message("❌ Das Ticket ist bereits geschlossen.", ephemeral=True)
        await interaction.response.send_message("🔒 Ticket wird geschlossen …", ephemeral=True)
        self.db.close_ticket(t["id"])

        lines = [f"Transkript Ticket #{t['id']} ({channel.name})", ""]
        count = 0
        async for m in channel.history(limit=None, oldest_first=True):
            text = m.content or ""
            for e in m.embeds:
                text += f" [Embed: {e.title or ''} {e.description or ''}]"
            for a in m.attachments:
                text += f" [Anhang: {a.url}]"
            lines.append(f"[{m.created_at:%d.%m.%Y %H:%M}] {m.author} ({m.author.id}): {text.strip()}")
            count += 1
        file = discord.File(io.BytesIO("\n".join(lines).encode("utf-8")), filename=f"ticket-{t['id']:04d}.txt")

        c = self.category_cfg(t["category"])
        embed = discord.Embed(
            title=f"🔒 Ticket #{t['id']} geschlossen", color=discord.Color.dark_grey(), timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Erstellt von", value=f"<@{t['user_id']}>")
        embed.add_field(name="Kategorie", value=c["label"] if c else t["category"])
        embed.add_field(name="Übernommen von", value=f"<@{t['claimed_by']}>" if t["claimed_by"] else "—")
        embed.add_field(name="Geschlossen von", value=interaction.user.mention)
        embed.add_field(name="Geöffnet", value=f"<t:{t['created_at']}:f>")
        embed.add_field(name="Nachrichten", value=str(count))
        logged = await util.log_to(interaction.guild, self.cfg["kanaele"]["ticket_log"], embed=embed, file=file)
        if not logged:
            await channel.send(
                "⚠️ Transkript konnte nicht gespeichert werden (Log-Kanal nicht gefunden). "
                "Der Kanal bleibt deshalb bestehen und kann von Hand gelöscht werden."
            )
            return
        try:
            await channel.delete(reason=f"Ticket #{t['id']} geschlossen von {interaction.user}")
        except discord.Forbidden:
            await channel.send("⚠️ Ich darf diesen Kanal nicht löschen (Berechtigung **Kanäle verwalten** fehlt).")

    # ---------- Befehle ----------
    @app_commands.command(name="ticket-panel", description="Sendet das Ticket-Panel in diesen Kanal.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def panel(self, interaction: discord.Interaction):
        if not util.is_admin(interaction.user):
            return await interaction.response.send_message(
                "❌ Nur Administratoren können das Panel senden.", ephemeral=True
            )
        lines = [f"{c.get('emoji', '🎫')} **{c['label']}** – {c.get('beschreibung', '')}" for c in self.tcfg["kategorien"]]
        embed = discord.Embed(
            title="🎫 Ticket-Support",
            description=(
                "Wähle unten die passende Kategorie, um ein Ticket zu öffnen. "
                "Es wird ein privater Kanal erstellt, den nur du und das zuständige Team sehen.\n\n"
                + "\n".join(lines)
            ),
            color=discord.Color.red(),
        )
        try:
            await interaction.channel.send(embed=embed, view=PanelView(self))
        except discord.Forbidden:
            return await interaction.response.send_message(
                "❌ Ich darf in diesem Kanal nicht schreiben.", ephemeral=True
            )
        await interaction.response.send_message("✅ Panel gesendet.", ephemeral=True)

    @app_commands.command(name="ticket-hinzufuegen", description="Fügt ein Mitglied zu diesem Ticket hinzu.")
    @app_commands.describe(mitglied="Wer Zugriff auf das Ticket bekommen soll")
    @app_commands.guild_only()
    async def add(self, interaction: discord.Interaction, mitglied: discord.Member):
        t = self.db.ticket_by_channel(interaction.channel.id)
        if t is None:
            return await interaction.response.send_message("❌ Das ist kein offenes Ticket.", ephemeral=True)
        if not self.is_ticket_staff(interaction.user, t["category"]):
            return await interaction.response.send_message(
                "❌ Nur das zuständige Team kann Mitglieder hinzufügen.", ephemeral=True
            )
        await interaction.channel.set_permissions(
            mitglied, view_channel=True, send_messages=True, read_message_history=True, attach_files=True
        )
        await interaction.response.send_message(f"✅ {mitglied.mention} wurde zum Ticket hinzugefügt.")
