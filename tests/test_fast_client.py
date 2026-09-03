import json
import unittest
from unittest.mock import patch

from core.fast_client import FastChatClient


class FakeStreamResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    def iter_lines(self):
        for content in ('Hello', ' world.'):
            payload = json.dumps({'choices': [{'delta': {'content': content}}]})
            yield f'data: {payload}'
        yield 'data: [DONE]'


class FakeClient:
    def __init__(self, **kwargs):
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def stream(self, *args, **kwargs):
        self.request_json = kwargs['json']
        return FakeStreamResponse()

    def close(self):
        self.closed = True


class TestFastChatClient(unittest.TestCase):
    def test_sse_deltas_are_forwarded_and_combined(self):
        deltas = []
        with patch('core.fast_client.httpx.Client', FakeClient):
            result = FastChatClient('key', 'model').send(
                'system', [], 'hello', on_delta=deltas.append,
            )
        self.assertEqual(deltas, ['Hello', ' world.'])
        self.assertEqual(result, 'Hello world.')


if __name__ == '__main__':
    unittest.main()
