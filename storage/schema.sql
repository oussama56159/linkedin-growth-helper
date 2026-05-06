-- LinkedIn Growth System Database Schema

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_url TEXT UNIQUE NOT NULL,
    author_name TEXT,
    author_profile_url TEXT,
    content TEXT,
    likes_count INTEGER DEFAULT 0,
    comments_count INTEGER DEFAULT 0,
    reposts_count INTEGER DEFAULT 0,
    relevance_score REAL DEFAULT 0.0,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    post_age_hours REAL,
    hashtags TEXT,  -- JSON array
    is_spam INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_url TEXT UNIQUE NOT NULL,
    full_name TEXT,
    headline TEXT,
    industry TEXT,
    location TEXT,
    connections_count INTEGER,
    relevance_score REAL DEFAULT 0.0,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    mutual_connections INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suggestion_type TEXT NOT NULL,  -- 'like', 'comment', 'repost', 'connect'
    target_url TEXT NOT NULL,       -- post or profile URL
    target_summary TEXT,
    reason TEXT,
    comment_draft TEXT,             -- only for comment suggestions
    relevance_score REAL DEFAULT 0.0,
    status TEXT DEFAULT 'pending',  -- 'pending', 'approved', 'rejected', 'executed', 'failed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notified_at TIMESTAMP,
    decided_at TIMESTAMP,
    executed_at TIMESTAMP,
    telegram_message_id INTEGER
);

CREATE TABLE IF NOT EXISTS actions_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT NOT NULL,
    target_url TEXT NOT NULL,
    status TEXT NOT NULL,           -- 'success', 'failed', 'skipped'
    error_message TEXT,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    suggestion_id INTEGER,
    FOREIGN KEY (suggestion_id) REFERENCES suggestions(id)
);

CREATE TABLE IF NOT EXISTS daily_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,             -- YYYY-MM-DD
    likes_count INTEGER DEFAULT 0,
    comments_count INTEGER DEFAULT 0,
    reposts_count INTEGER DEFAULT 0,
    connections_count INTEGER DEFAULT 0,
    UNIQUE(date)
);

CREATE TABLE IF NOT EXISTS seen_content (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT UNIQUE NOT NULL,  -- MD5 of post URL or profile URL
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_suggestions_status ON suggestions(status);
CREATE INDEX IF NOT EXISTS idx_suggestions_type ON suggestions(suggestion_type);
CREATE INDEX IF NOT EXISTS idx_actions_date ON actions_log(executed_at);
CREATE INDEX IF NOT EXISTS idx_posts_score ON posts(relevance_score DESC);
