import tempfile
import unittest
from pathlib import Path

from config import Config
from core.conversation import ConversationManager
from core.interview import InterviewSession


class TestInterviewMode(unittest.TestCase):
    def test_natural_and_slash_commands(self):
        conversation = ConversationManager(Config.load())
        self.assertEqual(conversation.handle_command('/interview')['action'], 'interview_start')
        conversation.interview.start()
        self.assertEqual(conversation.handle_command('give me a hint')['action'], 'interview_hint')
        self.assertEqual(conversation.handle_command('end the interview')['action'], 'interview_end')

    def test_interview_prompt_is_isolated_from_normal_history(self):
        conversation = ConversationManager(Config.load())
        conversation.add_turn('normal private topic', 'normal answer')
        conversation.interview.start()
        prompt = conversation.build_prompt('I would clarify scale.')
        self.assertIn('senior distributed-systems engineer', prompt)
        self.assertNotIn('normal private topic', prompt)

    def test_report_is_saved_locally(self):
        with tempfile.TemporaryDirectory() as directory:
            session = InterviewSession(directory)
            session.start()
            session.add_turn('We need one million users.', 'What is the read/write ratio?')
            report = session.finish('Requirements: 4/5')
            self.assertTrue(report.exists())
            self.assertIn('Requirements: 4/5', report.read_text(encoding='utf-8'))
            self.assertTrue(Path(str(report).replace('.md', '.json')).exists())


if __name__ == '__main__':
    unittest.main()
