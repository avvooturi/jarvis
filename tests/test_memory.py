import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from core.memory import MemoryStore


class TestMemoryStore(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'memory.db'
        self.memory = MemoryStore(self.path)

    def tearDown(self):
        self.memory.close()
        self.temp.cleanup()

    def test_conversations_persist_across_instances(self):
        self.memory.add_conversation('What is sharding?', 'Horizontal partitioning.', 'assistant', 'jarvis')
        self.memory.close()
        self.memory = MemoryStore(self.path)
        self.assertEqual(self.memory.recent_conversations(), [('What is sharding?', 'Horizontal partitioning.')])

    def test_scores_create_learning_profile_and_trend(self):
        evaluation_one = 'Requirements: 2/5\nEstimation: 1/5\nArchitecture: 4/5\nScalability: 2/5'
        evaluation_two = 'Requirements: 4/5\nEstimation: 3/5\nArchitecture: 4/5\nScalability: 3/5'
        now = dt.datetime.now()
        self.memory.add_interview(now, now, 60, [], evaluation_one)
        self.memory.add_interview(now, now, 60, [], evaluation_two)
        profile = self.memory.learning_profile()
        self.assertIn('Completed interviews: 2', profile)
        self.assertIn('requirements up 2 point(s)', profile)

    def test_forget_all_requires_caller_confirmation_but_store_deletes(self):
        self.memory.add_conversation('secret', 'answer', 'assistant', 'jarvis')
        now = dt.datetime.now()
        self.memory.add_interview(now, now, 1, [], 'Communication: 3/5')
        self.memory.forget_all()
        self.assertEqual(self.memory.recent_conversations(), [])
        self.assertEqual(self.memory.interview_count(), 0)

    def test_sensitive_values_are_redacted_before_storage(self):
        self.memory.add_conversation(
            'password=hunter2 api_key=sk-abcdefghijklmnop',
            'Authorization: Bearer abcdef123456',
            'assistant',
            'jarvis',
        )
        user, assistant = self.memory.recent_conversations()[0]
        self.assertNotIn('hunter2', user)
        self.assertNotIn('sk-abcdefghijklmnop', user)
        self.assertNotIn('abcdef123456', assistant)
        self.assertIn('REDACTED', user)

    def test_disabled_memory_does_not_create_database(self):
        path = Path(self.temp.name) / 'private.db'
        private = MemoryStore(path, enabled=False)
        try:
            private.add_conversation('private', 'response', 'assistant', 'jarvis')
            self.assertFalse(path.exists())
            self.assertEqual(private.recent_conversations(), [])
        finally:
            private.close()

    def test_retention_removes_old_records(self):
        old = (dt.datetime.now() - dt.timedelta(days=40)).isoformat()
        self.memory.connection.execute('''
            INSERT INTO conversations
            (session_id, created_at, mode, personality, user_text, assistant_text)
            VALUES (?, ?, 'assistant', 'jarvis', 'old request', 'old response')
        ''', (self.memory.session_id, old))
        self.memory.connection.commit()
        self.memory.retention_days = 30
        removed = self.memory.purge_expired()
        self.assertEqual(removed['conversations'], 1)

    def test_search_delete_and_export(self):
        record_id = self.memory.add_conversation(
            'Explain consistent hashing', 'It distributes keys around a ring.', 'assistant', 'jarvis',
        )
        matches = self.memory.search_conversations('consistent hashing')
        self.assertEqual(matches[0]['id'], record_id)

        self.memory.export_dir = Path(self.temp.name) / 'exports'
        export_path = self.memory.export_memory()
        exported = json.loads(export_path.read_text(encoding='utf-8'))
        self.assertEqual(exported['conversations'][0]['id'], record_id)

        self.assertTrue(self.memory.delete_conversation(record_id))
        self.assertEqual(self.memory.search_conversations('consistent hashing'), [])

    def test_private_mode_stops_new_writes_and_can_be_reenabled(self):
        self.memory.set_persistence(False)
        self.memory.add_conversation('not saved', 'not saved', 'assistant', 'jarvis')
        self.assertEqual(self.memory.recent_conversations(), [])
        self.memory.set_persistence(True)
        self.memory.add_conversation('saved', 'saved', 'assistant', 'jarvis')
        self.assertEqual(self.memory.recent_conversations(), [('saved', 'saved')])


if __name__ == '__main__':
    unittest.main()
