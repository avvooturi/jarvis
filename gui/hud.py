import datetime as dt
import math
import os
import queue
import random
from collections import deque

os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
import pygame

try:
    import psutil
except ImportError:
    psutil = None


BG = (2, 8, 13)
PANEL = (6, 20, 29)
CYAN = (36, 229, 255)
CYAN_DIM = (8, 121, 141)
CYAN_DARK = (7, 54, 66)
TEXT = (185, 247, 255)
MUTED = (75, 142, 153)
WARNING = (255, 105, 74)

STATE_LABELS = {
    'idle': 'JARVIS // ONLINE',
    'listening': 'LISTENING...',
    'transcribing': 'TRANSCRIBING...',
    'thinking': 'PROCESSING...',
    'speaking': 'RESPONDING...',
    'error': 'SYSTEM ALERT',
}


def _clamp(value, low=0.0, high=100.0):
    return max(low, min(high, value))


def _font(size, bold=False):
    return pygame.font.SysFont('consolas', max(8, int(size)), bold=bold)


def _text(surface, value, position, size=10, color=TEXT, anchor='topleft', bold=False):
    image = _font(size, bold).render(str(value), True, color)
    rect = image.get_rect()
    setattr(rect, anchor, (int(position[0]), int(position[1])))
    surface.blit(image, rect)
    return rect


def _ellipsize(value, max_chars):
    value = str(value).replace('\n', ' ')
    return value if len(value) <= max_chars else value[:max(1, max_chars-1)] + '…'


def _wrap_text(value, max_chars):
    lines = []
    for paragraph in str(value).split('\n'):
        words = paragraph.split()
        if not words:
            lines.append('')
            continue
        line = words[0]
        for word in words[1:]:
            if len(line) + len(word) + 1 <= max_chars:
                line += ' ' + word
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines or ['']


class CircularGauge:
    def __init__(self, label, unit='%', color=CYAN):
        self.label = label
        self.unit = unit
        self.color = color

    def draw(self, surface, x, y, radius, value):
        value = _clamp(value)
        box = pygame.Rect(x-radius, y-radius, radius*2, radius*2)
        pygame.draw.arc(surface, CYAN_DARK, box, math.radians(-135), math.radians(135), 3)
        extent = math.radians(270 * value / 100)
        pygame.draw.arc(surface, self.color, box, math.radians(135)-extent, math.radians(135), 3)
        _text(surface, f'{value:02.0f}{self.unit}', (x, y-2), 10, TEXT, 'center', True)
        _text(surface, self.label, (x, y+radius+12), 8, MUTED, 'center')


class VoiceWaveform:
    def __init__(self, rng):
        self.rng = rng
        self.values = [0.05] * 64

    def update(self, active, phase):
        target = 0.78 if active else 0.08
        for index in range(len(self.values)):
            wave = abs(math.sin(phase * 0.13 + index * 0.48))
            desired = (wave * 0.7 + self.rng.random() * 0.22) * target
            self.values[index] += (desired - self.values[index]) * 0.22

    def draw(self, surface, x1, y, x2, color=CYAN):
        pygame.draw.line(surface, CYAN_DARK, (x1, y), (x2, y))
        step = (x2-x1) / max(1, len(self.values)-1)
        points = [(x1+i*step, y-value*34) for i, value in enumerate(self.values)]
        if len(points) > 1:
            pygame.draw.aalines(surface, color, False, points)


class JarvisCore:
    @staticmethod
    def _arc(surface, color, cx, cy, radius, start, extent, width):
        rect = pygame.Rect(cx-radius, cy-radius, radius*2, radius*2)
        pygame.draw.arc(surface, color, rect, math.radians(start), math.radians(start+extent), width)

    def draw(self, surface, cx, cy, radius, phase, state):
        active = state != 'idle'
        color = WARNING if state == 'error' else CYAN
        glow = (127, 45, 36) if state == 'error' else CYAN_DIM
        pulse = 1 + (0.035 if active else 0.015) * math.sin(phase*0.14)
        radius = int(radius*pulse)

        glow_surface = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        pygame.draw.circle(glow_surface, (*glow, 20), (cx, cy), radius+24, 18)
        surface.blit(glow_surface, (0, 0))
        pygame.draw.circle(surface, glow, (cx, cy), radius+10, 3)
        pygame.draw.circle(surface, color, (cx, cy), radius, 2)

        for ring, (speed, scale) in enumerate(zip((0.42, -0.7, 1.05), (0.87, 0.72, 0.57))):
            r = int(radius*scale)
            offset = phase*speed*(2 if state == 'thinking' else 1)
            segments = 12+ring*4
            for index in range(segments):
                start = index*360/segments+offset
                extent = (360/segments)*(0.52 if ring != 1 else 0.34)
                self._arc(surface, color if index % 3 else CYAN_DIM, cx, cy, r, start, extent, max(1, 4-ring))

        for angle in range(0, 360, 6):
            rad = math.radians(angle+phase*0.08)
            outer, inner = radius*0.98, radius*0.91-(5 if angle % 30 == 0 else 0)
            pygame.draw.aaline(surface, color if angle % 30 == 0 else CYAN_DIM,
                               (cx+math.cos(rad)*inner, cy+math.sin(rad)*inner),
                               (cx+math.cos(rad)*outer, cy+math.sin(rad)*outer))

        inner = int(radius*0.36)
        pygame.draw.circle(surface, CYAN_DIM, (cx, cy), inner, 2)
        pygame.draw.circle(surface, (3, 21, 29), (cx, cy), max(1, inner-9))
        pygame.draw.circle(surface, color, (cx, cy), max(1, inner-9), 1)
        _text(surface, 'J.A.R.V.I.S.', (cx, cy-8), 19, TEXT, 'center', True)
        _text(surface, 'NEURAL CORE', (cx, cy+18), 8, MUTED, 'center')

        if state == 'thinking':
            for index in range(12):
                angle = phase*0.03+index*math.tau/12
                travel = radius*(0.25+((phase*0.008+index/12) % 0.65))
                pygame.draw.circle(surface, color, (int(cx+math.cos(angle)*travel), int(cy+math.sin(angle)*travel)), 2)


class HudPanel:
    @staticmethod
    def draw(surface, rect, title):
        layer = pygame.Surface(rect.size, pygame.SRCALPHA)
        layer.fill((*PANEL, 225))
        surface.blit(layer, rect)
        pygame.draw.rect(surface, CYAN_DARK, rect, 1)
        pygame.draw.line(surface, CYAN, rect.topleft, (rect.x+52, rect.y), 2)
        pygame.draw.line(surface, CYAN, rect.topleft, (rect.x, rect.y+24), 2)
        _text(surface, title, (rect.x+15, rect.y+18), 10, CYAN, 'midleft', True)
        _text(surface, '[ LIVE ]', (rect.right-13, rect.y+18), 7, MUTED, 'midright')


class HudWindow:
    """Thread-safe, state-reactive Pygame HUD for the voice pipeline."""

    def __init__(self, on_toggle_recording, on_submit_text, on_close, model, personality, hotkey='F8'):
        self.on_toggle_recording = on_toggle_recording
        self.on_submit_text = on_submit_text
        self.on_close = on_close
        self.model = model
        self.personality = personality.upper()
        self.hotkey = hotkey.upper()
        self.state = 'idle'
        self.last_command = 'Awaiting voice directive'
        self.current_task = 'Standing by'
        self.mode = 'ASSISTANT'
        self.progress = 'NO INTERVIEW DATA'
        self.transcript = deque(maxlen=6)
        self.events = queue.Queue()
        self.phase = 0
        self.rng = random.Random(42)
        self.core = JarvisCore()
        self.waveform = VoiceWaveform(self.rng)
        self.running = True
        self.fullscreen = False
        self.input_text = ''
        self.input_focused = False
        self.exchange_expanded = False

        pygame.init()
        pygame.display.set_caption('JARVIS // Tactical Intelligence Interface')
        info = pygame.display.Info()
        size = (max(1000, min(info.current_w, 1600)), max(650, min(info.current_h-70, 900)))
        self.screen = pygame.display.set_mode(size, pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        pygame.key.start_text_input()

    def run(self):
        while self.running:
            self._handle_input()
            self._drain_events()
            if not self.running:
                break
            self.phase += 1
            self.waveform.update(self.state in {'listening', 'speaking'}, self.phase)
            self._draw()
            pygame.display.flip()
            self.clock.tick(30)
        pygame.quit()

    def set_state(self, state, detail=None):
        self.events.put(('state', state, detail))

    def add_exchange(self, user_text, assistant_text):
        self.events.put(('exchange', user_text, assistant_text))

    def set_personality(self, personality):
        self.events.put(('personality', personality))

    def set_mode(self, mode):
        self.events.put(('mode', mode))

    def set_progress(self, progress):
        self.events.put(('progress', progress))

    def request_close(self):
        self.events.put(('close',))

    def _handle_input(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.on_close()
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if self.input_focused and event.key == pygame.K_RETURN:
                    self._submit_input()
                elif self.input_focused and event.key == pygame.K_BACKSPACE:
                    self.input_text = self.input_text[:-1]
                elif self.input_focused and event.key == pygame.K_ESCAPE:
                    self.input_text = ''
                    self.input_focused = False
                elif event.key == pygame.K_ESCAPE:
                    self.on_close()
                    self.running = False
                elif event.key == pygame.K_SPACE and not self.input_focused:
                    self.on_toggle_recording()
                elif event.key == pygame.K_F11:
                    self.fullscreen = not self.fullscreen
                    flags = pygame.FULLSCREEN if self.fullscreen else pygame.RESIZABLE
                    self.screen = pygame.display.set_mode((0, 0) if self.fullscreen else (1400, 820), flags)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                width, height = self.screen.get_size()
                input_rect = self._input_rect(width, height)
                exchange_rect = self._recent_exchange_rect(width, height)
                expand_rect = self._exchange_expand_rect(exchange_rect)
                if expand_rect.collidepoint(event.pos):
                    self.exchange_expanded = not self.exchange_expanded
                    self.input_focused = False
                    continue
                if input_rect.collidepoint(event.pos):
                    self.input_focused = True
                    continue
                self.input_focused = False
                cx, cy = width/2, 70+(height-240)*0.43
                if math.hypot(event.pos[0]-cx, event.pos[1]-cy) < min(width, height)*0.18:
                    self.on_toggle_recording()
            elif event.type == pygame.TEXTINPUT and self.input_focused:
                if len(self.input_text) < 2000:
                    self.input_text += event.text

    def _input_rect(self, width, height):
        return pygame.Rect(28, height-54, width-56, 36)

    def _recent_exchange_rect(self, width, height):
        if self.exchange_expanded:
            return pygame.Rect(28, 58, width-56, height-124)
        return pygame.Rect(28, height-180, width-56, 112)

    @staticmethod
    def _exchange_expand_rect(exchange_rect):
        return pygame.Rect(exchange_rect.right-94, exchange_rect.y+8, 78, 22)

    def _submit_input(self):
        text = self.input_text.strip()
        if not text:
            return
        if self.on_submit_text(text) is not False:
            self.input_text = ''

    def _drain_events(self):
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                return
            if event[0] == 'state':
                _, self.state, detail = event
                if detail:
                    self.current_task = detail
            elif event[0] == 'exchange':
                _, user_text, assistant_text = event
                self.last_command = user_text
                self.transcript.append(('USER', user_text))
                self.transcript.append(('JARVIS', assistant_text))
            elif event[0] == 'personality':
                self.personality = event[1].upper()
            elif event[0] == 'mode':
                self.mode = event[1]
            elif event[0] == 'progress':
                self.progress = event[1]
            elif event[0] == 'close':
                self.running = False

    def _telemetry(self):
        if psutil is None:
            return {'CPU': 0, 'RAM': 0, 'DISK': 0, 'NET': 0}
        net = psutil.net_io_counters()
        return {
            'CPU': psutil.cpu_percent(interval=None),
            'RAM': psutil.virtual_memory().percent,
            'DISK': psutil.disk_usage('.').percent,
            'NET': ((net.bytes_sent+net.bytes_recv)/(1024*1024)) % 100,
        }

    def _background(self, width, height):
        for x in range(0, width, 64):
            pygame.draw.line(self.screen, (3, 19, 26), (x, 42), (x, height))
        for y in range(42, height, 64):
            pygame.draw.line(self.screen, (3, 19, 26), (0, y), (width, y))
        scan_y = 42+(self.phase*2 % max(1, height-42))
        pygame.draw.line(self.screen, (8, 53, 65), (0, scan_y), (width, scan_y))
        for index in range(22):
            x = int((index*137+self.phase*(0.12+index % 3*0.07)) % width)
            y = int(55+(index*83) % max(1, height-80))
            pygame.draw.circle(self.screen, CYAN_DARK, (x, y), 1)

    def _draw(self):
        self.screen.fill(BG)
        width, height = self.screen.get_size()
        self._background(width, height)
        now = dt.datetime.now()

        pygame.draw.rect(self.screen, (4, 18, 26), (0, 0, width, 42))
        pygame.draw.line(self.screen, CYAN_DARK, (0, 41), (width, 41))
        _text(self.screen, 'JARVIS OS  //  MK IV', (24, 21), 12, CYAN, 'midleft', True)
        _text(self.screen, now.strftime('%H:%M:%S  //  %d %b %Y').upper(), (width/2, 21), 11, TEXT, 'center')
        mic_status = 'ONLINE' if self.state != 'error' else 'ALERT'
        _text(self.screen, f'HERMES: ONLINE    OPENROUTER: ONLINE    MIC: {mic_status}', (width-24, 21), 9, CYAN, 'midright')

        margin, panel_w = 28, max(225, int(width*0.215))
        top, bottom = 70, height-205
        left = pygame.Rect(margin, top, panel_w, bottom-top)
        right = pygame.Rect(width-margin-panel_w, top, panel_w, bottom-top)
        HudPanel.draw(self.screen, left, 'SYSTEM TELEMETRY')
        HudPanel.draw(self.screen, right, 'ACTIVE SESSION')

        telemetry = self._telemetry()
        gauge_radius = min(42, int(panel_w*0.16))
        positions = ((left.x+panel_w*.30, top+105), (left.x+panel_w*.70, top+105),
                     (left.x+panel_w*.30, top+235), (left.x+panel_w*.70, top+235))
        for (label, value), (gx, gy) in zip(telemetry.items(), positions):
            CircularGauge(label).draw(self.screen, int(gx), int(gy), gauge_radius, value)
        _text(self.screen, 'VOICE INPUT', (left.x+18, bottom-72), 8, MUTED)
        self.waveform.draw(self.screen, left.x+18, bottom-35, left.right-18)

        details = [('MODE', self.mode), ('MODEL', self.model.upper()),
                   ('AGENT', 'HERMES'), ('VOICE', 'WINDOWS // READY'),
                   ('STATUS', self.state.upper()), ('GROWTH', self.progress)]
        for index, (label, value) in enumerate(details):
            y = top+64+index*54
            _text(self.screen, label, (right.x+18, y), 8, MUTED)
            _text(self.screen, _ellipsize(value, max(16, panel_w//9)), (right.x+18, y+18), 9, TEXT, 'topleft', True)
            pygame.draw.line(self.screen, (10, 43, 52), (right.x+18, y+34), (right.right-18, y+34))

        available_w = width-2*(margin+panel_w)-40
        radius = int(min(height*.235, available_w*.31, 205))
        cx, cy = width//2, int(top+(bottom-top)*.43)
        self.core.draw(self.screen, cx, cy, radius, self.phase, self.state)
        state_color = WARNING if self.state == 'error' else CYAN
        _text(self.screen, STATE_LABELS.get(self.state, self.state.upper()), (cx, cy+radius+38), 13, state_color, 'center', True)
        _text(self.screen, f'PRESS {self.hotkey} OR CLICK CORE TO TOGGLE VOICE CAPTURE', (cx, cy+radius+60), 8, MUTED, 'center')

        transcript_rect = self._recent_exchange_rect(width, height)
        HudPanel.draw(self.screen, transcript_rect, 'NEURAL LINK // RECENT EXCHANGE')
        expand_rect = self._exchange_expand_rect(transcript_rect)
        pygame.draw.rect(self.screen, (5, 28, 38), expand_rect)
        pygame.draw.rect(self.screen, CYAN_DARK, expand_rect, 1)
        _text(self.screen, 'COLLAPSE' if self.exchange_expanded else 'EXPAND', expand_rect.center, 8, CYAN, 'center', True)
        if not self.transcript:
            _text(self.screen, 'SYSTEM // Voice channel ready. Awaiting directive.', (transcript_rect.x+18, transcript_rect.y+62), 9, MUTED, 'midleft')
        elif self.exchange_expanded:
            max_chars = max(60, (transcript_rect.width-145)//8)
            lines = []
            for speaker, value in self.transcript:
                wrapped = _wrap_text(value, max_chars)
                lines.append((f'{speaker} //', wrapped[0], speaker))
                lines.extend(('', line, speaker) for line in wrapped[1:])
                lines.append(('', '', speaker))
            visible_count = max(1, (transcript_rect.height-62)//22)
            for index, (label, value, speaker) in enumerate(lines[-visible_count:]):
                y = transcript_rect.y+48+index*22
                if label:
                    _text(self.screen, label, (transcript_rect.x+18, y), 9, CYAN if speaker == 'JARVIS' else TEXT, 'midleft', True)
                _text(self.screen, value, (transcript_rect.x+112, y), 9, MUTED if speaker == 'JARVIS' else TEXT, 'midleft')
        else:
            max_chars = max(60, width//9)
            for index, (speaker, value) in enumerate(list(self.transcript)[-3:]):
                y = transcript_rect.y+47+index*24
                _text(self.screen, f'{speaker} //', (transcript_rect.x+18, y), 9, CYAN if speaker == 'JARVIS' else TEXT, 'midleft', True)
                _text(self.screen, _ellipsize(value, max_chars), (transcript_rect.x+105, y), 9, MUTED if speaker == 'JARVIS' else TEXT, 'midleft')
        input_rect = self._input_rect(width, height)
        pygame.draw.rect(self.screen, (3, 15, 22), input_rect)
        pygame.draw.rect(self.screen, CYAN if self.input_focused else CYAN_DARK, input_rect, 1)
        prefix = 'COMMAND // '
        _text(self.screen, prefix, (input_rect.x+12, input_rect.centery), 9, CYAN, 'midleft', True)
        display = self.input_text if self.input_text else 'Type a command and press Enter...'
        color = TEXT if self.input_text else MUTED
        text_x = input_rect.x+108
        text_width = input_rect.width-132
        max_chars = max(20, text_width//8)
        visible_line = _ellipsize(display, max_chars)
        _text(self.screen, visible_line, (text_x, input_rect.centery), 9, color, 'midleft')
        if self.input_focused and (self.phase//15) % 2 == 0:
            cursor_x = min(input_rect.right-14, text_x+_font(9).size(visible_line)[0]+2)
            pygame.draw.line(self.screen, CYAN, (cursor_x, input_rect.y+9), (cursor_x, input_rect.y+25), 1)
