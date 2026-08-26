# Jarvis Voice Assistant

Jarvis is a Windows desktop voice assistant with a real-time heads-up display. It listens through the microphone, transcribes speech locally, decides how a request should be handled, gets a response from an AI model, displays the exchange, and reads the answer aloud.

The project is a practical personal-assistant prototype. It combines a responsive local interface with Hermes Agent in WSL for requests that may require tools, an optional low-latency OpenRouter route for ordinary conversation, persistent local memory, and a dedicated system-design interview coach.

## What Jarvis Does

A normal voice request follows this pipeline:

1. Press the configured hotkey (default `F8`) or click the HUD core to begin recording.
2. Press or click again to stop.
3. Jarvis saves the captured microphone audio to a temporary WAV file.
4. `faster-whisper` transcribes the recording locally.
5. Jarvis checks for built-in commands and locally handled Spotify requests.
6. The request router chooses either the optional fast conversation model or Hermes Agent.
7. The response is added to conversation history and shown in the HUD.
8. `pyttsx3` speaks the answer through Windows text-to-speech.
9. The temporary recording is removed after transcription.

Typed requests skip recording and transcription but otherwise use the same command, routing, memory, display, and speech pipeline.

### Voice and text input

- Global push-to-talk using `F8` by default.
- Clickable animated HUD core and `Space` as in-window recording controls.
- A `COMMAND //` field for typed prompts and slash commands.
- Local English speech recognition through `faster-whisper`.
- Voice activity detection to reduce silence in transcriptions.
- A background request worker so the graphical interface stays responsive.
- Busy-state protection that prevents overlapping recordings and requests.

### Spoken responses

Jarvis uses `pyttsx3` and the Windows speech engine, so speech synthesis is local. A preferred installed voice can be selected by name. Short answers use the normal configured speaking rate; answers above a configurable word threshold use a faster rate.

Use `/mute` to keep receiving answers in the HUD without hearing them, and `/unmute` to restore speech.

### Intelligent request routing

Jarvis has two AI response paths:

- **Fast conversation route:** If `OPENROUTER_API_KEY` is configured, ordinary questions are sent directly to the model in `FAST_MODEL`. This route uses recent conversation context and is optimized for short spoken answers.
- **Hermes Agent route:** Requests that appear to involve files, applications, websites, device actions, execution, installation, downloads, email, or scheduling are sent to Hermes in WSL with a larger tool-turn budget. Hermes is also the fallback when the fast route is disabled or fails.

The router is intentionally lightweight and keyword based. It helps choose a path; it is not a security boundary or a complete intent classifier. Hermes' actual abilities depend on the tools, permissions, provider, and configuration available inside your WSL installation.

Without an OpenRouter API key in the Windows `.env`, all non-local AI requests go through Hermes.

### Persistent memory

Jarvis saves conversations and interview results to a local SQLite database at `data/jarvis_memory.db` by default. On startup it restores the five most recent normal assistant exchanges as conversational context.

Stored conversation records include the session, timestamp, operating mode, active personality, user text, and assistant response. Completed interview records also include the transcript, duration, evaluation, and any rubric scores extracted from the evaluation. Jarvis uses those scores to summarize strengths, priority areas, and changes over time.

Memory management commands are described in [Commands](#commands). `/forgetall` requires a separate confirmation command before permanent deletion.

### System-design interview coach

Interview mode turns Jarvis into a concise senior distributed-systems interviewer. It selects a realistic design problem and expects the candidate to lead. The interviewer progresses through:

- Requirements and scope.
- Capacity and traffic estimation.
- APIs and data modeling.
- High-level architecture.
- Scalability and reliability.
- Bottlenecks, deep dives, and tradeoffs.
- Communication and justification of decisions.

Jarvis asks one focused question at a time and avoids revealing a complete solution. `/hint` provides a small nudge based on the current discussion. Normal assistant history is kept separate from the active interview transcript.

When `/endinterview` is used, Jarvis generates a Markdown evaluation with 1–5 scores across nine categories: requirements, estimation, API design, data model, architecture, scalability, reliability, tradeoffs, and communication. It saves a readable Markdown report, a structured JSON report, and the evaluation and extracted scores in SQLite.

Reports are written to `interview_sessions/`. Previous performance is summarized into a compact learning profile that can inform later interviews.

### Personalities

The default Jarvis personality is calm, concise, and professional. The included Eve personality is more casual, friendly, and energetic. Personality definitions are YAML files in `personalities/`, making their prompts easy to adjust. Personality affects ordinary responses; interview mode uses its own interviewer prompt.

### Spotify handling

Requests such as “play Daft Punk on Spotify” are handled locally. Jarvis opens a Spotify search using the desktop-app URI on Windows, falling back to a browser search if necessary.

This is search launching, not authenticated playback control. Jarvis cannot currently control an account, choose a device, manage playlists, or guarantee that playback starts. Those capabilities require Spotify OAuth and an API integration.

### Heads-up display

The Pygame HUD provides visual feedback for idle, listening, transcribing, thinking, speaking, and error states. It also displays system telemetry, an animated waveform and central core, the current model, personality and mode, recent exchanges, and the interview learning profile. The recent-exchange panel can be expanded for additional history.

Press `F11` to toggle full-screen mode and `Escape` to close Jarvis.

## Architecture

```text
Microphone / typed command
          |
          v
  Audio capture + local Whisper STT
          |
          v
  Commands / Spotify local handler
          |
          v
     Request router
       /        \
Fast OpenRouter  Hermes Agent in WSL
       \        /
          v
 Conversation memory + HUD + local TTS
```

### Project structure

| Path | Responsibility |
| --- | --- |
| `main.py` | Application entry point, HUD lifecycle, hotkey handling, background queue, orchestration, and response delivery. |
| `config.py` | Loads `.env` values into application configuration. |
| `core/audio.py` | Captures mono microphone audio and manages temporary WAV recordings. |
| `core/stt.py` | Wraps `faster-whisper` transcription. |
| `core/request_router.py` | Detects requests likely to need Hermes tools. |
| `core/fast_client.py` | Sends low-latency conversational requests directly to OpenRouter. |
| `core/hermes_client.py` | Invokes the Hermes CLI inside a configured WSL distribution. |
| `core/conversation.py` | Builds prompts, restores context, switches personalities, and recognizes commands. |
| `core/memory.py` | Stores sessions, conversations, interviews, evaluations, and scores in SQLite. |
| `core/interview.py` | Manages interview state and writes Markdown/JSON reports. |
| `core/spotify.py` | Opens local Spotify searches. |
| `core/tts.py` | Queues local Windows speech synthesis on a dedicated thread. |
| `gui/hud.py` | Renders and operates the animated Pygame interface. |
| `personalities/` | Contains YAML personality prompts. |
| `tests/` | Unit tests for routing, Hermes, interviews, memory, and TTS. |

## Requirements

- Windows 10 or 11 with a working microphone and speakers.
- Python 3.10 or newer on Windows.
- WSL2 with a Linux distribution (`Ubuntu` by default).
- Hermes Agent installed and configured inside WSL.
- A model provider configured for Hermes (OpenRouter by default).
- Internet access for AI model requests and the initial Whisper model download.

Speech recognition and synthesis run locally after their required components are available. AI reasoning is remote through the provider configured for Hermes or OpenRouter; prompts sent to those routes are therefore not fully local.

## Installation

Open PowerShell and run:

```powershell
cd C:\Users\avvoo\OneDrive\Desktop\programming\jarvis
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

If `.env` already exists, do not overwrite it. Edit the existing file instead. The first use of a `faster-whisper` model may download model files and take longer than later startups.

## Configuring Hermes

Jarvis calls Hermes through WSL in the equivalent form:

```powershell
wsl -d Ubuntu bash -lc 'hermes chat -q "..." -Q --provider openrouter -m openai/gpt-5.4-mini --max-turns 6 ...'
```

Hermes itself must already be authenticated and functional inside WSL. Change `HERMES_WSL_DISTRO` if the distribution is not named `Ubuntu`, and change `HERMES_COMMAND` if the executable uses another command or path. `HERMES_EXTRA_FLAGS` is appended to the command, so review it carefully before changing it.

## Configuration Reference

Values in `.env` override the application defaults.

| Variable | Default | Purpose |
| --- | --- | --- |
| `HERMES_WSL_DISTRO` | `Ubuntu` | WSL distribution containing Hermes. |
| `HERMES_COMMAND` | `hermes` | Hermes command inside WSL. |
| `HERMES_PROVIDER` | `openrouter` | Provider passed to Hermes. |
| `HERMES_MODEL` | `openrouter/auto` in code | Hermes model. `.env.example` selects `openai/gpt-5.4-mini`. |
| `HERMES_SESSION_NAME` | `jarvis_voice_assistant` | Reserved session label in the current configuration. |
| `HERMES_EXTRA_FLAGS` | `--ignore-rules --accept-hooks --source tool` | Additional Hermes CLI flags. |
| `HERMES_TIMEOUT` | `60` | Maximum seconds for a Hermes request. |
| `HERMES_MAX_TURNS` | `6` | Turn budget for tool requests. Ordinary Hermes chat uses one turn. |
| `OPENROUTER_API_KEY` | empty | Enables the optional direct fast route. |
| `FAST_MODEL` | `openai/gpt-5.4-nano` | Direct conversational model. |
| `FAST_TIMEOUT` | `30` | Maximum seconds for a fast-route request. |
| `WHISPER_MODEL` | `base.en` | `faster-whisper` model name or path. |
| `WHISPER_DEVICE` | `cpu` | Whisper device, commonly `cpu` or `cuda`. |
| `WHISPER_COMPUTE_TYPE` | `int8` | Whisper compute precision. |
| `WHISPER_BEAM_SIZE` | `1` | Transcription beam size; larger values trade speed for accuracy. |
| `WHISPER_VAD_FILTER` | `true` | Enables silence filtering. |
| `AUDIO_SAMPLE_RATE` | `16000` | Microphone sample rate in Hz. |
| `TTS_ENGINE` | `pyttsx3` | Speech engine; currently the only supported value. |
| `TTS_VOICE` | empty | Substring of an installed Windows voice name. |
| `TTS_RATE` | `190` | Speaking rate for shorter responses. |
| `TTS_FAST_RATE` | `230` | Speaking rate for longer responses. |
| `TTS_FAST_WORD_THRESHOLD` | `50` | Word count above which the faster rate is used. |
| `HOTKEY` | `f8` | Global push-to-talk toggle. |
| `DEFAULT_PERSONALITY` | `jarvis` | Personality loaded at startup. |
| `PERSONALITIES_DIR` | `personalities` | Directory containing personality YAML files. |
| `MEMORY_DB_PATH` | `data/jarvis_memory.db` | SQLite memory database location. |

## Running Jarvis

From the project directory:

```powershell
python main.py
```

Then press `F8`, speak, and press `F8` again; click the central HUD core; use `Space` while the HUD is focused; or type into `COMMAND //` and press `Enter`.

Jarvis processes one request at a time. Input submitted while recording or processing is ignored.

## Commands

Commands can be typed. Several interview and memory commands also recognize natural-language equivalents.

| Command | Effect |
| --- | --- |
| `/jarvis` | Switch to the concise, professional Jarvis personality. |
| `/eve` | Switch to the friendly, energetic Eve personality. |
| `/mute` | Stop spoken output while retaining displayed responses. |
| `/unmute` | Resume spoken output. |
| `/interview` | Start a system-design interview. |
| `/hint` | Request one small hint during an active interview. |
| `/endinterview` | End the interview, evaluate it, and save reports. |
| `/memory` | Count recent normal turns and summarize learning data. |
| `/progress` | Show strengths, priorities, and score trends. |
| `/lastinterview` | Display the latest saved interview evaluation. |
| `/forgetlast` | Delete the previous saved application session, retaining the current one. |
| `/forgetall` | Begin deletion of all saved conversations and interview progress. |
| `/confirmforgetall` | Confirm a pending `/forgetall` operation. |
| `/quit` | Close Jarvis cleanly. |

## Data and Privacy

Jarvis creates or may create:

- `data/jarvis_memory.db` for conversation and interview memory.
- `interview_sessions/*.md` and `*.json` for completed interview reports.
- `temp_recording_*.wav` while a captured request is waiting for transcription.

Temporary WAV files are normally deleted immediately after the transcription attempt. A crash or forced shutdown can leave one behind; it can be deleted manually when Jarvis is not running.

Microphone transcription uses local Whisper, and speech output uses the local Windows voice engine. Prompt text and recent context are sent to Hermes' configured provider or directly to OpenRouter when the optional fast route is enabled. Do not use the assistant for sensitive material unless that data flow matches your privacy requirements.

## Testing

Run the tests from the project directory:

```powershell
python -m unittest discover -s tests -v
```

Most tests isolate or mock external components, but `tests/test_hermes_client.py` exercises the configured Hermes connection and requires a working WSL/Hermes setup.

## Troubleshooting

### The global hotkey does not work

- Click the HUD core or use `Space` while it is focused.
- Check whether another program has claimed the key.
- Try another `HOTKEY` value in `.env`.
- Windows may require elevated privileges for global keyboard hooks in some environments.

### The microphone cannot start or records no audio

- Enable Windows microphone access for desktop applications.
- Confirm that the correct input device is the Windows default.
- Close software that may have exclusive control of the microphone.
- Check the terminal log for microphone or audio-frame errors.

### Transcription fails or is slow

- The first run may still be downloading the Whisper model.
- Confirm that `WHISPER_DEVICE` and `WHISPER_COMPUTE_TYPE` are compatible.
- Use `cpu` with `int8` for the broadest compatibility.
- Larger models may improve accuracy but increase memory use and latency.
- Keep `WHISPER_BEAM_SIZE=1` for the lowest latency.

### Hermes connection fails

- Confirm the distribution name with `wsl -l -v`.
- Open that distribution and verify that `hermes` runs.
- Confirm Hermes' provider credentials and selected model.
- Review the `HERMES_*` values in `.env`.
- Increase `HERMES_TIMEOUT` if valid requests exceed 60 seconds.

### The fast route is not used

- Set `OPENROUTER_API_KEY` before starting Jarvis.
- Requests containing action or tool-related keywords intentionally go to Hermes.
- If the direct request errors, Jarvis automatically falls back to Hermes.

### Jarvis displays an answer but does not speak

- Use `/unmute` in case output was muted.
- Confirm the default Windows output device and volume.
- Leave `TTS_VOICE` empty to use the system default.
- If selecting a voice, use part of its installed display name.
- Only `pyttsx3` is currently supported as `TTS_ENGINE`.

### Spotify opens a search but does not play

This is expected. The current integration launches a search only and does not have Spotify account authorization or playback control.

## Current Limitations

- There is no wake-word detection; recording must be toggled manually.
- Speech recognition is configured for English by default.
- The keyword-based request classifier can misroute ambiguous prompts.
- Fast-route and Hermes responses rely on external AI providers.
- Spotify support opens searches but does not control playback.
- Hermes tool access and safety depend on its separate installation and configuration.
- Only two personalities and one TTS backend are included.
- Jarvis handles one request at a time and cannot be interrupted while speaking.

## Possible Next Steps

- Add wake-word detection and a more robust recording state machine.
- Replace keyword routing with structured intent classification.
- Add explicit confirmations and permissions for system automation.
- Implement Spotify OAuth for authenticated playback control.
- Support additional local TTS engines such as Piper.
- Add configurable conversation retention and export controls.
- Improve interruption, cancellation, and request queue behavior.
