import datetime as dt
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


if __name__ == '__main__':
    unittest.main()
