import datetime as dt
import json
from pathlib import Path


INTERVIEW_PROMPT = """You are a senior distributed-systems engineer conducting a system-design interview.
The candidate must lead the design. Ask exactly one focused question at a time and do not reveal a complete solution.
Progress naturally through requirements, estimation, API/data model, high-level architecture, deep dives,
scalability, reliability, and tradeoffs. Challenge unsupported assumptions and introduce realistic constraints.
Only give a small hint when requested. Keep each spoken response concise, normally one or two sentences.
Do not score the candidate until the interview ends."""

EVALUATION_PROMPT = """The system-design interview has ended. Evaluate the candidate using only the transcript below.
Score each category from 1 to 5: requirements, estimation, API design, data model, architecture, scalability,
reliability, tradeoffs, and communication. Give concise evidence, strengths, missed concepts, and the three
highest-priority improvements. Be candid and do not invent evidence. Format the result as readable Markdown."""


class InterviewSession:
    def __init__(self, reports_dir='interview_sessions'):
        self.reports_dir = Path(reports_dir)
        self.active = False
        self.started_at = None
        self.turns = []

    def start(self):
        self.active = True
        self.started_at = dt.datetime.now()
        self.turns = []

    def add_turn(self, user_text, assistant_text):
        if self.active:
            self.turns.append((user_text, assistant_text))

    def evaluation_prompt(self):
        transcript = '\n\n'.join(
            f'Candidate: {user}\nInterviewer: {assistant}'
            for user, assistant in self.turns
        )
        return f'{EVALUATION_PROMPT}\n\nINTERVIEW TRANSCRIPT:\n{transcript or "No substantive answers were recorded."}'

    def finish(self, evaluation, save=True, sanitizer=None):
        ended_at = dt.datetime.now()
        stamp = (self.started_at or ended_at).strftime('%Y%m%d_%H%M%S')
        markdown_path = self.reports_dir / f'interview_{stamp}.md'
        json_path = self.reports_dir / f'interview_{stamp}.json'
        duration = int((ended_at - (self.started_at or ended_at)).total_seconds())
        safe = sanitizer or (lambda value: value)
        safe_turns = [(safe(user), safe(assistant)) for user, assistant in self.turns]
        safe_evaluation = safe(evaluation)
        transcript = '\n\n'.join(f'**Candidate:** {u}\n\n**Interviewer:** {a}' for u, a in safe_turns)
        if save:
            self.reports_dir.mkdir(parents=True, exist_ok=True)
            markdown_path.write_text(
                f'# System Design Interview\n\nDuration: {duration} seconds\n\n## Transcript\n\n{transcript}\n\n## Evaluation\n\n{safe_evaluation}\n',
                encoding='utf-8',
            )
            json_path.write_text(json.dumps({
                'started_at': self.started_at.isoformat() if self.started_at else None,
                'ended_at': ended_at.isoformat(),
                'duration_seconds': duration,
                'turns': [{'candidate': u, 'interviewer': a} for u, a in safe_turns],
                'evaluation': safe_evaluation,
            }, indent=2), encoding='utf-8')
        result = {
            'started_at': self.started_at,
            'ended_at': ended_at,
            'duration_seconds': duration,
            'turns': safe_turns,
            'evaluation': safe_evaluation,
            'report_path': markdown_path if save else None,
        }
        self.active = False
        self.started_at = None
        self.turns = []
        return result

    def purge_reports(self, retention_days, now=None):
        if retention_days <= 0 or not self.reports_dir.exists():
            return 0
        now = now or dt.datetime.now()
        cutoff = now.timestamp() - retention_days * 86400
        removed = 0
        for pattern in ('interview_*.md', 'interview_*.json'):
            for path in self.reports_dir.glob(pattern):
                try:
                    if path.stat().st_mtime < cutoff:
                        path.unlink()
                        removed += 1
                except OSError:
                    continue
        return removed
