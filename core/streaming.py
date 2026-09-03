import re


class SentenceBuffer:
    """Collect model deltas and release complete speakable sentences."""

    _BOUNDARY = re.compile(r'^(.+?[.!?](?:["\'\)\]]?)(?:\s+|$))', re.DOTALL)

    def __init__(self):
        self.text = ''

    def add(self, delta):
        self.text += delta
        sentences = []
        while True:
            match = self._BOUNDARY.match(self.text)
            if match is None:
                break
            sentence = match.group(1).strip()
            self.text = self.text[match.end():]
            if sentence:
                sentences.append(sentence)
        return sentences

    def flush(self):
        remainder = self.text.strip()
        self.text = ''
        return remainder
