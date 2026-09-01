import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from config import Config
from core.conversation import ConversationManager
from core.interview import InterviewSession


class TestInterviewMode(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = replace(
            Config.load(),
            memory_db_path=Path(self.temp.name) / 'memory.db',
            interview_reports_dir=Path(self.temp.name) / 'interviews',
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_natural_and_slash_commands(self):
        conversation = ConversationManager(self.config)
        self.assertEqual(conversation.handle_command('/interview')['action'], 'interview_start')
        conversation.interview.start()
        self.assertEqual(conversation.handle_command('give me a hint')['action'], 'interview_hint')
        self.assertEqual(conversation.handle_command('end the interview')['action'], 'interview_end')
        conversation.memory.close()

    def test_interview_prompt_is_isolated_from_normal_history(self):
        conversation = ConversationManager(self.config)
        conversation.add_turn('normal private topic', 'normal answer')
        conversation.interview.start()
        prompt = conversation.build_prompt('I would clarify scale.')
        self.assertIn('senior distributed-systems engineer', prompt)
        self.assertNotIn('normal private topic', prompt)
        conversation.memory.close()

    def test_report_is_saved_locally(self):
        with tempfile.TemporaryDirectory() as directory:
            session = InterviewSession(directory)
            session.start()
            session.add_turn('We need one million users.', 'What is the read/write ratio?')
            result = session.finish('Requirements: 4/5')
            report = result['report_path']
            self.assertTrue(report.exists())
            self.assertIn('Requirements: 4/5', report.read_text(encoding='utf-8'))
            self.assertTrue(Path(str(report).replace('.md', '.json')).exists())

    def test_private_interview_does_not_write_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            session = InterviewSession(directory)
            session.start()
            session.add_turn('private answer', 'private question')
            result = session.finish('Communication: 4/5', save=False)
            self.assertIsNone(result['report_path'])
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_report_content_can_be_sanitized(self):
        with tempfile.TemporaryDirectory() as directory:
            session = InterviewSession(directory)
            session.start()
            session.add_turn('password=hunter2', 'Continue')
            result = session.finish('API key sk-abcdefghijklmnop', sanitizer=lambda _: '[REDACTED]')
            contents = result['report_path'].read_text(encoding='utf-8')
            self.assertNotIn('hunter2', contents)
            self.assertNotIn('sk-abcdefghijklmnop', contents)


if __name__ == '__main__':
    unittest.main()
