import datetime as dt
import json
import re
import sqlite3
import uuid
from pathlib import Path


RUBRIC = (
    'requirements', 'estimation', 'api design', 'data model', 'architecture',
    'scalability', 'reliability', 'tradeoffs', 'communication',
)


class MemoryStore:
    def __init__(self, path='data/jarvis_memory.db', enabled=True, retention_days=0,
                 redact_sensitive=True, export_dir='data/exports'):
        self.path = Path(path)
        self.persistence_enabled = bool(enabled)
        self.retention_days = max(0, int(retention_days))
        self.redact_sensitive = bool(redact_sensitive)
        self.export_dir = Path(export_dir)
        self._ephemeral = not self.persistence_enabled
        if self.persistence_enabled:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        database = self.path if self.persistence_enabled else ':memory:'
        self.connection = sqlite3.connect(database, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._create_schema()
        self.session_id = self.start_session()
        self.purge_expired()

    def _create_schema(self):
        self.connection.executescript('''
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, started_at TEXT NOT NULL, mode TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL, created_at TEXT NOT NULL,
                mode TEXT NOT NULL, personality TEXT NOT NULL,
                user_text TEXT NOT NULL, assistant_text TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS interviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT, ended_at TEXT NOT NULL, duration_seconds INTEGER NOT NULL,
                transcript_json TEXT NOT NULL, evaluation TEXT NOT NULL, scores_json TEXT NOT NULL
            );
        ''')
        self.connection.commit()

    def start_session(self, mode='assistant'):
        session_id = str(uuid.uuid4())
        self.connection.execute(
            'INSERT INTO sessions (id, started_at, mode) VALUES (?, ?, ?)',
            (session_id, dt.datetime.now().isoformat(), mode),
        )
        self.connection.commit()
        return session_id

    def add_conversation(self, user_text, assistant_text, mode, personality):
        if not self.persistence_enabled:
            return None
        user_text = self.sanitize(user_text)
        assistant_text = self.sanitize(assistant_text)
        self.connection.execute('''
            INSERT INTO conversations
            (session_id, created_at, mode, personality, user_text, assistant_text)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (self.session_id, dt.datetime.now().isoformat(), mode, personality, user_text, assistant_text))
        self.connection.commit()
        return self.connection.execute('SELECT last_insert_rowid()').fetchone()[0]

    def sanitize(self, text):
        text = str(text)
        if not self.redact_sensitive:
            return text
        patterns = (
            (r'(?i)\b(authorization\s*:\s*bearer\s+)[^\s,;]+', r'\1[REDACTED]'),
            (r'(?i)\b(api[_ -]?key|access[_ -]?token|secret|password|passwd)\s*[:=]\s*([^\s,;]+)', r'\1=[REDACTED]'),
            (r'\bsk-[A-Za-z0-9_-]{12,}\b', '[REDACTED_API_KEY]'),
            (r'\b\d{3}-\d{2}-\d{4}\b', '[REDACTED_SSN]'),
            (r'\b(?:\d[ -]*?){13,19}\b', '[REDACTED_PAYMENT_CARD]'),
        )
        for pattern, replacement in patterns:
            text = re.sub(pattern, replacement, text)
        return text

    def recent_conversations(self, limit=5, mode='assistant'):
        rows = self.connection.execute('''
            SELECT user_text, assistant_text FROM conversations
            WHERE mode = ? ORDER BY id DESC LIMIT ?
        ''', (mode, limit)).fetchall()
        return [(row['user_text'], row['assistant_text']) for row in reversed(rows)]

    @staticmethod
    def parse_scores(evaluation):
        scores = {}
        for category in RUBRIC:
            pattern = rf'(?i)\b{re.escape(category)}\b[^\n\d]{{0,30}}([1-5])\s*(?:/\s*5|out of 5)'
            match = re.search(pattern, evaluation)
            if match:
                scores[category] = int(match.group(1))
        return scores

    def add_interview(self, started_at, ended_at, duration_seconds, turns, evaluation):
        scores = self.parse_scores(evaluation)
        if not self.persistence_enabled:
            return scores
        safe_turns = [(self.sanitize(user), self.sanitize(assistant)) for user, assistant in turns]
        evaluation = self.sanitize(evaluation)
        self.connection.execute('''
            INSERT INTO interviews
            (started_at, ended_at, duration_seconds, transcript_json, evaluation, scores_json)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            started_at.isoformat() if started_at else None,
            ended_at.isoformat(), duration_seconds,
            json.dumps([{'candidate': u, 'interviewer': a} for u, a in safe_turns]),
            evaluation, json.dumps(scores),
        ))
        self.connection.commit()
        return scores

    def last_interview(self):
        return self.connection.execute('SELECT * FROM interviews ORDER BY id DESC LIMIT 1').fetchone()

    def interview_count(self):
        return self.connection.execute('SELECT COUNT(*) FROM interviews').fetchone()[0]

    def learning_profile(self):
        rows = self.connection.execute('SELECT scores_json FROM interviews ORDER BY id').fetchall()
        score_sets = [json.loads(row['scores_json']) for row in rows]
        if not score_sets:
            return 'No completed interview evaluations are available yet.'
        values = {category: [] for category in RUBRIC}
        for scores in score_sets:
            for category, score in scores.items():
                values[category].append(score)
        averages = {key: sum(items)/len(items) for key, items in values.items() if items}
        if not averages:
            return f'{len(rows)} interview(s) completed, but no structured rubric scores could be extracted.'
        ranked = sorted(averages.items(), key=lambda item: item[1], reverse=True)
        strengths = ', '.join(f'{name} ({score:.1f}/5)' for name, score in ranked[:3])
        focus = ', '.join(f'{name} ({score:.1f}/5)' for name, score in ranked[-3:])
        trends = []
        for category, items in values.items():
            if len(items) >= 2 and items[-1] != items[0]:
                direction = 'up' if items[-1] > items[0] else 'down'
                trends.append(f'{category} {direction} {abs(items[-1]-items[0])} point(s)')
        trend_text = '; '.join(trends[:3]) or 'Not enough score movement yet.'
        return f'Completed interviews: {len(rows)}. Strongest areas: {strengths}. Priority areas: {focus}. Trends: {trend_text}'

    def progress_summary(self):
        return self.learning_profile()

    def set_persistence(self, enabled):
        enabled = bool(enabled)
        if enabled and self._ephemeral:
            self.connection.close()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(self.path, check_same_thread=False)
            self.connection.row_factory = sqlite3.Row
            self._create_schema()
            self._ephemeral = False
            self.persistence_enabled = True
            self.session_id = self.start_session()
            self.purge_expired()
            return
        self.persistence_enabled = enabled

    def purge_expired(self, now=None):
        if self.retention_days <= 0 or not self.persistence_enabled:
            return {'conversations': 0, 'interviews': 0, 'sessions': 0}
        now = now or dt.datetime.now()
        cutoff = (now - dt.timedelta(days=self.retention_days)).isoformat()
        counts = {}
        cursor = self.connection.execute('DELETE FROM conversations WHERE created_at < ?', (cutoff,))
        counts['conversations'] = cursor.rowcount
        cursor = self.connection.execute('DELETE FROM interviews WHERE ended_at < ?', (cutoff,))
        counts['interviews'] = cursor.rowcount
        cursor = self.connection.execute('''
            DELETE FROM sessions WHERE started_at < ? AND id != ?
            AND id NOT IN (SELECT DISTINCT session_id FROM conversations)
        ''', (cutoff, self.session_id))
        counts['sessions'] = cursor.rowcount
        self.connection.commit()
        return counts

    def search_conversations(self, query, limit=10):
        query = query.strip()
        if not query:
            return []
        escaped = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        rows = self.connection.execute('''
            SELECT id, created_at, mode, personality, user_text, assistant_text
            FROM conversations
            WHERE user_text LIKE ? ESCAPE '\\' OR assistant_text LIKE ? ESCAPE '\\'
            ORDER BY id DESC LIMIT ?
        ''', (f'%{escaped}%', f'%{escaped}%', int(limit))).fetchall()
        return list(rows)

    def delete_conversation(self, conversation_id):
        cursor = self.connection.execute('DELETE FROM conversations WHERE id = ?', (int(conversation_id),))
        self.connection.commit()
        return cursor.rowcount > 0

    def export_memory(self):
        self.export_dir.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
        path = self.export_dir / f'jarvis_memory_{stamp}.json'
        conversations = [dict(row) for row in self.connection.execute(
            'SELECT id, session_id, created_at, mode, personality, user_text, assistant_text FROM conversations ORDER BY id'
        )]
        interviews = [dict(row) for row in self.connection.execute(
            'SELECT id, started_at, ended_at, duration_seconds, transcript_json, evaluation, scores_json FROM interviews ORDER BY id'
        )]
        payload = {
            'exported_at': dt.datetime.now().isoformat(),
            'conversations': conversations,
            'interviews': interviews,
        }
        path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        return path

    def privacy_summary(self):
        conversations = self.connection.execute('SELECT COUNT(*) FROM conversations').fetchone()[0]
        interviews = self.interview_count()
        retention = f'{self.retention_days} days' if self.retention_days else 'unlimited'
        persistence = 'on' if self.persistence_enabled else 'off for new records'
        redaction = 'on' if self.redact_sensitive else 'off'
        return (
            f'Memory persistence is {persistence}; retention is {retention}; sensitive-text redaction is '
            f'{redaction}. Stored records: {conversations} conversations and {interviews} interviews.'
        )

    def forget_last_session(self):
        row = self.connection.execute('SELECT id FROM sessions ORDER BY started_at DESC LIMIT 1 OFFSET 1').fetchone()
        if row is None:
            return False
        self.connection.execute('DELETE FROM conversations WHERE session_id = ?', (row['id'],))
        self.connection.execute('DELETE FROM sessions WHERE id = ?', (row['id'],))
        self.connection.commit()
        return True

    def forget_all(self):
        self.connection.execute('DELETE FROM conversations')
        self.connection.execute('DELETE FROM interviews')
        self.connection.execute('DELETE FROM sessions WHERE id != ?', (self.session_id,))
        self.connection.commit()

    def close(self):
        self.connection.close()
