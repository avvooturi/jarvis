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

## Configuring Whisper

The default model is `small.en`, with `cpu` and `int8` compute. Change these values in `.env`:

- `WHISPER_MODEL`
- `WHISPER_DEVICE`
- `WHISPER_COMPUTE_TYPE`

For better accuracy and speed, choose a model that fits your local hardware.

## Configuring TTS

By default the assistant uses `pyttsx3` on Windows.
You can optionally set a preferred `TTS_VOICE` and `TTS_RATE` in `.env`.

## Running the Assistant

1. Start the assistant:

```powershell
python main.py
```

2. Press and hold the configured hotkey (default `F8`) to record.
3. Release the hotkey to stop recording and send the transcription to Hermes.
4. The assistant speaks Hermes' response out loud.

If `keyboard` cannot capture the hotkey, use the fallback text mode by running the script again. Then type `/record` and press Enter to start/stop audio input.

## Switching Personalities

Use voice commands during a session:

- `/jarvis` - switch to the Jarvis personality
- `/eve` - switch to the Eve personality
- `/mute` - disable spoken output
- `/unmute` - re-enable spoken output
- `/quit` - exit cleanly

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
