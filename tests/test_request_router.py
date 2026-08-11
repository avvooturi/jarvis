import unittest

from core.request_router import needs_tools
from core.spotify import SpotifyHandler


class TestRequestRouter(unittest.TestCase):
    def test_simple_question_does_not_need_tools(self):
        self.assertFalse(needs_tools('Who was the greatest basketball player?'))

    def test_device_action_needs_tools(self):
        self.assertTrue(needs_tools('Open my project on this device'))

    def test_spotify_access_question_is_answered_locally(self):
        response = SpotifyHandler().handle('Do you have access to my Spotify?')
        self.assertIn('not authorized', response)


if __name__ == '__main__':
    unittest.main()
