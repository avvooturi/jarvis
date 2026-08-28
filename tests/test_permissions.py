import unittest

from core.permissions import PermissionManager, RiskLevel


class TestPermissionManager(unittest.TestCase):
    def test_read_only_tool_request_is_allowed_in_balanced_mode(self):
        manager = PermissionManager()
        assessment = manager.assess('Find and read the project README file')
        self.assertEqual(assessment.risk, RiskLevel.READ_ONLY)
        self.assertFalse(assessment.requires_confirmation)

    def test_file_change_requires_confirmation(self):
        manager = PermissionManager()
        assessment = manager.assess('Rename the file to report.txt')
        self.assertEqual(assessment.risk, RiskLevel.REVERSIBLE)
        self.assertTrue(assessment.requires_confirmation)

    def test_destructive_action_has_highest_priority(self):
        manager = PermissionManager()
        assessment = manager.assess('Upload the backup and then delete the original file')
        self.assertEqual(assessment.risk, RiskLevel.DESTRUCTIVE)

    def test_confirmation_is_one_time(self):
        manager = PermissionManager()
        assessment = manager.assess('Install the package')
        pending = manager.request('Install the package', assessment)
        status, confirmed = manager.handle_command('/confirm')
        self.assertEqual(status, 'confirmed')
        self.assertEqual(confirmed, pending)
        self.assertIsNone(manager.pending)

    def test_expired_confirmation_cannot_execute(self):
        now = [10.0]
        manager = PermissionManager(timeout_seconds=5, clock=lambda: now[0])
        assessment = manager.assess('Delete the file')
        manager.request('Delete the file', assessment)
        now[0] = 16.0
        status, pending = manager.handle_command('/confirm')
        self.assertEqual(status, 'confirmed')
        self.assertIsNone(pending)

    def test_strict_mode_confirms_read_only_tools(self):
        manager = PermissionManager(mode='strict')
        self.assertTrue(manager.assess('Read the file').requires_confirmation)

    def test_natural_yes_is_not_a_command_without_pending_action(self):
        manager = PermissionManager()
        self.assertEqual(manager.handle_command('yes'), (None, None))

    def test_natural_yes_confirms_when_action_is_pending(self):
        manager = PermissionManager()
        assessment = manager.assess('Open the browser')
        manager.request('Open the browser', assessment)
        status, pending = manager.handle_command('yes')
        self.assertEqual(status, 'confirmed')
        self.assertEqual(pending.text, 'Open the browser')


if __name__ == '__main__':
    unittest.main()
