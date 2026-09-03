import unittest

from core.streaming import SentenceBuffer


class TestSentenceBuffer(unittest.TestCase):
    def test_releases_only_complete_sentences_across_deltas(self):
        buffer = SentenceBuffer()
        self.assertEqual(buffer.add('Hello wor'), [])
        self.assertEqual(buffer.add('ld. How are'), ['Hello world.'])
        self.assertEqual(buffer.add(' you? Fine'), ['How are you?'])
        self.assertEqual(buffer.flush(), 'Fine')

    def test_supports_closing_quote_after_punctuation(self):
        buffer = SentenceBuffer()
        self.assertEqual(buffer.add('Jarvis said, "Ready." Next '), ['Jarvis said, "Ready."'])
        self.assertEqual(buffer.flush(), 'Next')


if __name__ == '__main__':
    unittest.main()
