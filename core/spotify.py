import os
import re
import webbrowser
from urllib.parse import quote


class SpotifyHandler:
    def can_handle(self, text: str) -> bool:
        return 'spotify' in text.lower()

    def handle(self, text: str):
        lowered = text.lower()
        if any(word in lowered for word in ('access', 'connect', 'login', 'log in', 'authorize')):
            return 'I can open Spotify searches on this device, but account-level playback control is not authorized yet. Spotify OAuth credentials are required for that.'
        match = re.search(r'\bplay\s+(.+?)[?.!]*$', text, re.IGNORECASE)
        if not match:
            return None
        query = re.sub(r'\s+(?:on|in)\s+spotify\s*$', '', match.group(1), flags=re.IGNORECASE).strip()
        try:
            if os.name == 'nt':
                os.startfile(f'spotify:search:{quote(query)}')
            else:
                webbrowser.open(f'https://open.spotify.com/search/{quote(query)}')
        except OSError:
            webbrowser.open(f'https://open.spotify.com/search/{quote(query)}')
        return f'I opened Spotify and searched for {query}. Direct playback will require Spotify account authorization.'
