"""Gemeinsame Hilfsfunktionen."""
import re
from typing import Optional

import discord


def find_role(guild: discord.Guild, ref) -> Optional[discord.Role]:
    """Rolle ueber ID oder exakten Namen finden."""
    ref = str(ref).strip()
    if ref.isdigit():
        return guild.get_role(int(ref))
    return discord.utils.get(guild.roles, name=ref)


def find_roles(guild: discord.Guild, refs) -> list:
    return [r for r in (find_role(guild, ref) for ref in refs) if r is not None]


def find_text_channel(guild: discord.Guild, ref) -> Optional[discord.TextChannel]:
    """Textkanal ueber ID oder Namen finden (Emoji-Praefix wie '📈︱' wird ignoriert)."""
    ref = str(ref).strip()
    if ref.isdigit():
        channel = guild.get_channel(int(ref))
        return channel if isinstance(channel, discord.TextChannel) else None
    for channel in guild.text_channels:
        if channel.name == ref:
            return channel
    for channel in guild.text_channels:
        if channel.name.endswith(ref):
            return channel
    return None


def is_admin(member: discord.Member) -> bool:
    return member.guild_permissions.administrator


def has_any_role(member: discord.Member, refs) -> bool:
    wanted = {r.id for r in find_roles(member.guild, refs)}
    return any(role.id in wanted for role in member.roles)


def is_staff(member: discord.Member, cfg: dict) -> bool:
    """Darf Rang- und Warn-Befehle benutzen."""
    return is_admin(member) or has_any_role(member, cfg["berechtigte_rollen"])


def kuerzel(role_name: str) -> str:
    """'OBM » [Oberbrandmeister]' -> 'OBM'"""
    return role_name.split("»")[0].strip()


def nickname_with_rank(display_name: str, rank_short: str) -> str:
    """Setzt '[Kuerzel] ' vor den Namen und entfernt ein altes Kuerzel."""
    base = re.sub(r"^\s*\[[^\]]*\]\s*", "", display_name).strip() or display_name
    prefix = f"[{rank_short}] "
    return prefix + base[: 32 - len(prefix)]


async def send_dm(member: discord.abc.User, embed: discord.Embed) -> bool:
    try:
        await member.send(embed=embed)
        return True
    except discord.HTTPException:
        return False


async def log_to(guild: discord.Guild, ref, **kwargs) -> bool:
    channel = find_text_channel(guild, ref)
    if channel is None:
        return False
    try:
        await channel.send(**kwargs)
        return True
    except discord.HTTPException:
        return False
