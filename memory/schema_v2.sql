-- JingJing memory schema v2
-- Layered memory: core (shared persona) / group / member, scoped by platform+bot.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS spaces (
    platform_id TEXT NOT NULL,
    bot_id      TEXT NOT NULL,
    group_id    TEXT NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1,
    note        TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (platform_id, bot_id, group_id)
);

CREATE TABLE IF NOT EXISTS consents (
    platform_id TEXT NOT NULL,
    bot_id      TEXT NOT NULL,
    group_id    TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    consent     INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (platform_id, bot_id, group_id, user_id)
);

CREATE TABLE IF NOT EXISTS memories (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id    TEXT NOT NULL DEFAULT '*',
    bot_id         TEXT NOT NULL DEFAULT '*',
    scope          TEXT NOT NULL,              -- core | group | member
    group_id       TEXT NOT NULL DEFAULT '',
    user_id        TEXT NOT NULL DEFAULT '',
    category       TEXT NOT NULL,
    content        TEXT NOT NULL,
    confidence     REAL NOT NULL DEFAULT 1.0,
    importance     INTEGER NOT NULL DEFAULT 2, -- 1 low .. 3 high
    status         TEXT NOT NULL DEFAULT 'active', -- candidate | active | archived | deleted
    source_ref     TEXT NOT NULL DEFAULT '',
    origin_memory_id INTEGER,
    evidence_count INTEGER NOT NULL DEFAULT 1,
    last_seen_at   TEXT NOT NULL DEFAULT '',
    superseded_by  INTEGER,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_memories_identity
    ON memories (platform_id, bot_id, scope, group_id, user_id, category, content);

CREATE INDEX IF NOT EXISTS ix_memories_recall
    ON memories (scope, platform_id, group_id, user_id, status);

CREATE TABLE IF NOT EXISTS memory_revisions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id   INTEGER NOT NULL,
    action      TEXT NOT NULL,        -- create | edit | archive | restore | delete
    actor       TEXT NOT NULL DEFAULT 'owner',
    before_json TEXT NOT NULL DEFAULT '{}',
    after_json  TEXT NOT NULL DEFAULT '{}',
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS promotions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    source_memory_id INTEGER NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending', -- pending | approved | rejected
    note             TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL,
    decided_at       TEXT,
    created_memory_id INTEGER
);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- v2.3: how well the bot knows one member, and the short-lived mood of a group.
CREATE TABLE IF NOT EXISTS relations (
    platform_id        TEXT NOT NULL,
    bot_id            TEXT NOT NULL,
    group_id          TEXT NOT NULL,
    user_id           TEXT NOT NULL,
    nickname          TEXT NOT NULL DEFAULT '',
    interactions      INTEGER NOT NULL DEFAULT 0,
    familiarity       INTEGER NOT NULL DEFAULT 0,
    stage             TEXT NOT NULL DEFAULT 'new',
    last_interaction_at TEXT NOT NULL DEFAULT '',
    last_day          TEXT NOT NULL DEFAULT '',
    day_gain          INTEGER NOT NULL DEFAULT 0,
    updated_at        TEXT NOT NULL,
    PRIMARY KEY (platform_id, bot_id, group_id, user_id)
);

CREATE TABLE IF NOT EXISTS moods (
    group_id    TEXT PRIMARY KEY,
    mood        TEXT NOT NULL,
    reason      TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL
);

-- v2.4: how a particular group responds to the bot. Counting only, no inference.
CREATE TABLE IF NOT EXISTS group_style (
    group_id   TEXT PRIMARY KEY,
    replies    INTEGER NOT NULL DEFAULT 0,
    continued  INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);