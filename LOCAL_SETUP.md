# Local Setup

## Environment

Python 3.12 and dependencies are managed by uv. FFmpeg and FFprobe must be on PATH.

```bash
uv sync --locked
uv run --locked python run_dataset_story.py --help
```

## Planning

The ignored `.env` selects Qwen3.5-Plus using your own local credentials.
Thinking is disabled at the LLM request boundary; prompts and pipeline stages
are unchanged. Both text planning and the visual judge use this shared model.
The output target is 720x1280, with 900x1600 shot keyframes. Asset reference sheets
retain the upstream square format.

```bash
uv run --locked python run_dataset_story.py our_dataset/BetterCallSaul2
```

This command calls the paid LLM.
Outputs are written under `data/runs/dataset/`.

## Media Adapter

The ignored `.env` selects `wan2.7-image-pro` and `happyhorse-1.0-i2v` through
the independent `local_media_gateway.py` service. Start it from the repository:

```bash
uv run --locked uvicorn local_media_gateway:app --host 127.0.0.1 --port 8766
```

The local endpoint is configured in `.env`. A separate local bearer token protects
it; upstream credentials remain inside the gateway. It translates the existing
OpenAI image/video client requests, leaving the FilmDSL and pipeline unchanged.
Reference images use inline Base64 in their original order, avoiding OSS basename
collisions. Sprite-sheet requests return 404, invoking CineCrew's FFmpeg fallback.
Video tasks can still be polled after a gateway restart using their provider IDs.

With the gateway running, adding `--execute` calls paid media providers.
Reference generation remains off in the upstream settings; enabling it later is
a separate experiment choice, not silently changed by this setup.

### HappyHorse Compatibility Limits

- The upstream flow uses one keyframe per job, matching HappyHorse first-frame
  conditioning. A supplied tail frame is rejected rather than silently dropped.
- HappyHorse accepts integer durations from 3 to 15 seconds. CineCrew's native
  dialogue segmentation can produce shorter jobs; these are rejected before
  provider submission. No duration padding, trimming or segmentation change is made.
- The existing client rounds its job duration into the `seconds` field. The
  gateway forwards that integer without an additional rounding rule.
- 720P output follows the keyframe's aspect ratio; the gateway does not send a
  `ratio` parameter. Actual dimensions and FPS require validation on a real clip.
- Native provider controls do not include CineCrew's `fps`, `frame_num`, or fixed
  voice presets. The resolved video prompt is passed unchanged (the original
  ProductionOperator already includes spoken lines). Voice identity is therefore
  not guaranteed. No independent TTS or lip-sync stage is invented.

## Verified Without Provider Calls

- Module imports: `src.pipeline`, `src.adapters`.
- Bundled BetterCallSaul2 blueprint and asset schema validation.
- Offline ProductionOperator compilation: four jobs, planned duration 13.5 seconds.
- Qwen thinking parameter and other-provider isolation tests.
- Original image/video SDK clients exercised against the local gateway with
  mocked provider responses: image edit, reference order, video lifecycle,
  authentication, short-clip/tail-frame rejection, and credential-free downloads.

This checkout has no built-in Web UI; the original entry point is the CLI above.

## Mac mini Setup

Install uv and FFmpeg/FFprobe (for example, `brew install uv ffmpeg`), then:

```bash
git clone --branch api-adapter https://github.com/hit-cxf/CineCrew.git
cd CineCrew
uv sync --python 3.12 --locked
cp .env.dashscope.example .env
chmod 600 .env
```

Configure the ignored `.env` before running:

- `LLM_API_KEY` and `DASHSCOPE_MEDIA_API_KEY`: your DashScope key.
- `MEDIA_GATEWAY_TOKEN`, `T2I_API_KEY`, `VIDEO_API_KEY`: the same locally generated
  random token, NOT the upstream provider key. Generate one with
  `uv run --locked python -c 'import secrets; print(secrets.token_urlsafe(32))'`.
- Keep the gateway bound to loopback. Local endpoint defaults are shown in the template.

Start the gateway in one terminal using the command in Media Adapter. In another,
run from the repository root:

```bash
# Paid LLM planning only
uv run --locked python run_dataset_story.py configs/local_examples/wedding_investor

# Paid planning and media generation, with the original visual review loop
uv run --locked python run_dataset_story.py configs/local_examples/wedding_investor --execute

# Offline tests, with mocked providers (no generation costs)
uv run --locked python -m unittest discover -s tests -v
```

Inspect the planned durations before a full paid render. The upstream `--execute`
entry point does not preflight all clip durations; the gateway rejects unsupported
clips when submitted. This branch does not change that pipeline behavior.

## Observed Test Result

One end-to-end run of the included short prompt completed all six clips and
assembled a 720x1280 video with audio. Actual length was 28.95 seconds, NOT the
requested three minutes. Some clips failed visual review even after the original
single retry, but the upstream framework retained them and still assembled a film.
The original concat produced unusual reported FPS; output timing/playback must be
checked before treating this as a formal benchmark result. Model, duration, language,
and quality compliance are not implied by a successful process exit.

Secrets, local test scripts under `data/`, media and run logs are not uploaded.
