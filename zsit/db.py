"""Kleine SQLite-Datenbank fuer Verwarnungen und Tickets."""
import sqlite3
import time
from pathlib import Path


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(path)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(
            """
            CREATE TABLE IF NOT EXISTS warns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                mod_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                removed_by INTEGER,
                removed_reason TEXT
            );
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                claimed_by INTEGER,
                is_open INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL
            );
            """
        )
        self.con.commit()

    # ---------- Verwarnungen ----------
    def add_warn(self, guild_id, user_id, mod_id, reason, days) -> int:
        now = int(time.time())
        cur = self.con.execute(
            "INSERT INTO warns (guild_id, user_id, mod_id, reason, created_at, expires_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, user_id, mod_id, reason, now, now + days * 86400),
        )
        self.con.commit()
        return cur.lastrowid

    def active_warns(self, guild_id, user_id) -> list:
        return self.con.execute(
            "SELECT * FROM warns WHERE guild_id=? AND user_id=? AND active=1 ORDER BY id",
            (guild_id, user_id),
        ).fetchall()

    def inactive_count(self, guild_id, user_id) -> int:
        return self.con.execute(
            "SELECT COUNT(*) FROM warns WHERE guild_id=? AND user_id=? AND active=0",
            (guild_id, user_id),
        ).fetchone()[0]

    def get_warn(self, guild_id, warn_id):
        return self.con.execute(
            "SELECT * FROM warns WHERE guild_id=? AND id=?", (guild_id, warn_id)
        ).fetchone()

    def remove_warn(self, warn_id, by, reason):
        self.con.execute(
            "UPDATE warns SET active=0, removed_by=?, removed_reason=? WHERE id=?",
            (by, reason, warn_id),
        )
        self.con.commit()

    def pop_expired(self) -> list:
        rows = self.con.execute(
            "SELECT * FROM warns WHERE active=1 AND expires_at<=?", (int(time.time()),)
        ).fetchall()
        if rows:
            self.con.executemany(
                "UPDATE warns SET active=0, removed_reason='abgelaufen' WHERE id=?",
                [(r["id"],) for r in rows],
            )
            self.con.commit()
        return rows

    # ---------- Tickets ----------
    def create_ticket(self, guild_id, user_id, category) -> int:
        cur = self.con.execute(
            "INSERT INTO tickets (guild_id, user_id, category, created_at) VALUES (?, ?, ?, ?)",
            (guild_id, user_id, category, int(time.time())),
        )
        self.con.commit()
        return cur.lastrowid

    def set_ticket_channel(self, ticket_id, channel_id):
        self.con.execute("UPDATE tickets SET channel_id=? WHERE id=?", (channel_id, ticket_id))
        self.con.commit()

    def open_ticket_of(self, guild_id, user_id, category):
        return self.con.execute(
            "SELECT * FROM tickets WHERE guild_id=? AND user_id=? AND category=? AND is_open=1",
            (guild_id, user_id, category),
        ).fetchone()

    def ticket_by_channel(self, channel_id):
        return self.con.execute(
            "SELECT * FROM tickets WHERE channel_id=? AND is_open=1", (channel_id,)
        ).fetchone()

    def claim_ticket(self, ticket_id, user_id):
        self.con.execute("UPDATE tickets SET claimed_by=? WHERE id=?", (user_id, ticket_id))
        self.con.commit()

    def close_ticket(self, ticket_id):
        self.con.execute("UPDATE tickets SET is_open=0 WHERE id=?", (ticket_id,))
        self.con.commit()
