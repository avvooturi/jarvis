import unittest

from core.state import AssistantState, AssistantStateMachine, RequestCancelled


class TestAssistantStateMachine(unittest.TestCase):
    def test_normal_voice_lifecycle(self):
        machine = AssistantStateMachine()
        for state in (
            AssistantState.RECORDING,
            AssistantState.TRANSCRIBING,
            AssistantState.ROUTING,
            AssistantState.THINKING,
            AssistantState.SPEAKING,
            AssistantState.IDLE,
        ):
            machine.transition(state)
        self.assertEqual(machine.state, AssistantState.IDLE)

    def test_cancel_sets_event_and_requires_completion(self):
        machine = AssistantStateMachine()
        machine.transition(AssistantState.ROUTING)
        self.assertTrue(machine.cancel())
        self.assertEqual(machine.state, AssistantState.CANCELLING)
        with self.assertRaises(RequestCancelled):
            machine.checkpoint()
        machine.transition(AssistantState.IDLE)

    def test_new_request_gets_fresh_cancel_event(self):
        machine = AssistantStateMachine()
        machine.transition(AssistantState.ROUTING)
        old_event = machine.cancel_event
        machine.cancel()
        machine.transition(AssistantState.IDLE)
        machine.transition(AssistantState.ROUTING)
        self.assertIsNot(machine.cancel_event, old_event)
        self.assertFalse(machine.cancel_event.is_set())

    def test_invalid_transition_is_rejected(self):
        machine = AssistantStateMachine()
        with self.assertRaises(RuntimeError):
            machine.transition(AssistantState.SPEAKING)

    def test_awaiting_permission_accepts_a_new_confirm_command(self):
        machine = AssistantStateMachine()
        machine.transition(AssistantState.ROUTING)
        machine.transition(AssistantState.AWAITING_PERMISSION)
        self.assertFalse(machine.busy)
        machine.transition(AssistantState.ROUTING)
        self.assertEqual(machine.state, AssistantState.ROUTING)


if __name__ == '__main__':
    unittest.main()
