# Jarvis Voice Assistant

A simple Windows desktop voice assistant prototype that uses local audio capture, `faster-whisper` speech-to-text, Hermes Agent in WSL for reasoning, and local TTS for spoken responses.

## Architecture

- `main.py` - application entrypoint and hotkey/recording loop.
- `config.py` - loads environment-based configuration.
- `core/audio.py` - microphone recording and temporary WAV file handling.
- `core/stt.py` - speech recognition wrapper using `faster-whisper`.
- `core/hermes_client.py` - bridge to Hermes Agent running in WSL via CLI.
- `core/tts.py` - abstracted text-to-speech interface using `pyttsx3`.
- `core/conversation.py` - conversation context, personalities, and command handling.
- `gui/hud.py` - animated Pygame JARVIS HUD, telemetry, waveform, and transcript display.
- `personalities/` - YAML personality prompts for Jarvis and Eve.

## Prerequisites

- Windows PC with a working microphone and speakers.
- Python 3.10+ installed on Windows.
- WSL2 installed with a Linux distro named `Ubuntu` by default.
- Hermes Agent installed and configured in WSL (existing installation is required).
- OpenRouter configured inside Hermes.

## Installation

1. Clone or create the project in `c:\Users\avvoo\OneDrive\Desktop\programming\jarvis`.
2. Install Python dependencies:

```powershell
cd C:\Users\avvoo\OneDrive\Desktop\programming\jarvis
python -m pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and customize values if needed.

## Configuring Hermes

This project assumes Hermes is already installed in WSL and configured with OpenRouter.
The assistant invokes Hermes via:

```powershell
wsl -d Ubuntu bash -lc 'hermes chat -q "..." -Q --source tool --ignore-rules --accept-hooks --provider openrouter -m openrouter/auto'
```

If your WSL distro name is different, update `HERMES_WSL_DISTRO` in `.env`.
If your Hermes command is installed somewhere else inside WSL, update `HERMES_COMMAND`.

For predictable latency, Jarvis uses a fixed Hermes model, a 60-second timeout,
and a small tool-turn budget. Configure these with `HERMES_MODEL`,
`HERMES_TIMEOUT`, and `HERMES_MAX_TURNS`.

### Optional fast conversation route

Set `OPENROUTER_API_KEY` in `.env` to send ordinary conversational questions
directly to the low-latency `FAST_MODEL`. Requests that appear to require files,
applications, or other tools continue to use Hermes. If the key is absent or the
fast request fails, Jarvis automatically falls back to Hermes.

## Configuring Whisper

The default model is `small.en`, with `cpu` and `int8` compute. Change these values in `.env`:

- `WHISPER_MODEL`
- `WHISPER_DEVICE`
- `WHISPER_COMPUTE_TYPE`
- `WHISPER_BEAM_SIZE` (`1` is fastest)
- `WHISPER_VAD_FILTER` (ignores silence)

For better accuracy and speed, choose a model that fits your local hardware.

## Configuring TTS

By default the assistant uses `pyttsx3` on Windows.
You can optionally set a preferred `TTS_VOICE` and `TTS_RATE` in `.env`.
Responses longer than `TTS_FAST_WORD_THRESHOLD` words use `TTS_FAST_RATE`,
allowing long answers to play faster without rushing short conversational replies.


## Spotify

Jarvis handles Spotify access questions locally instead of sending them through
the general agent. A request such as "play X on Spotify" opens that search in the
Spotify desktop app. Direct playback and account-level control require a future
Spotify OAuth integration.

## Running the Assistant

1. Start the assistant:

```powershell
python main.py
```

2. Press the configured hotkey (default `F8`) once to start recording.
3. Press it again to stop recording and send the transcription to Hermes.
4. The assistant speaks Hermes' response out loud.

The desktop HUD opens automatically and reacts to each pipeline stage: listening,
transcribing, thinking, speaking, idle, and error. You can also click the central
core or press Space while the HUD is focused to toggle recording. Press F11 for
full-screen mode and Escape to close Jarvis.

Click the `COMMAND //` field at the bottom of the HUD to type requests or slash
commands, then press Enter. Typed and spoken input share conversation history,
interview mode, agent routing, transcript display, and voice output.

If `keyboard` cannot capture the hotkey, use the fallback text mode by running the script again. Then type `/record` and press Enter to start/stop audio input.

## Switching Personalities

Use voice commands during a session:

- `/jarvis` - switch to the Jarvis personality
- `/eve` - switch to the Eve personality
- `/mute` - disable spoken output
- `/unmute` - re-enable spoken output
- `/quit` - exit cleanly

## System Design Interview Mode

Say `/interview` or "start a system design interview" to begin a stateful mock
interview. Jarvis presents a problem, asks one focused question at a time, and
challenges requirements, estimates, APIs, data models, architecture, scalability,
reliability, and tradeoffs without revealing the solution.

- `/hint` or "give me a hint" provides one small nudge.
- `/endinterview` or "end the interview" generates the final rubric and exits interview mode.

Each completed evaluation and transcript is saved locally as Markdown and JSON
under `interview_sessions/`. That directory is ignored by Git.

## Troubleshooting Windows Microphone/Audio

- Ensure Windows microphone permissions are enabled for Python.
- If the hotkey does not work, run the app as administrator or use the fallback `/record` mode.
- If audio playback fails, verify your default speaker device is configured correctly.
- For `faster-whisper` issues, ensure the chosen model is downloaded and compatible with `onnxruntime`.

## What Works in V1

- Push-to-talk recording via hotkey or fallback command mode.
- Local speech-to-text using `faster-whisper`.
- Hermes Agent integration via WSL CLI.
- Text response spoken through local speakers.
- Short conversational context and simple personality switching.
- Command handling for `/jarvis`, `/eve`, `/mute`, `/unmute`, and `/quit`.

## Recommended V2

- Add a lightweight GUI or tray icon.
- Add wake-word detection.
- Add a proper Hermes session manager to preserve context more robustly.
- Add safe tool architecture for non-destructive system actions.
- Add a local TTS provider plugin interface for Piper or other voice engines.
- Add a more reliable audio buffer/recording state machine.
- Add Windows automation tools behind explicit confirmation.
