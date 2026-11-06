#!/usr/bin/env python3
# Better Call CineCrew: Consistent Ultra-Long Narrative-to-Film Generation
# Paper: ECCV 2026
# Licensed under the Apache License, Version 2.0
"""Loopback-only OpenAI media API bridge; no changes to the CineCrew pipeline."""

import base64
import mimetypes
import os
import secrets
import time

import dashscope
import requests
from dashscope import VideoSynthesis
from dashscope.aigc.image_generation import ImageGeneration
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from src.config import Config

BASE_URL = os.environ.get("DASHSCOPE_MEDIA_BASE_URL", "").rstrip("/")
API_KEY = os.environ.get("DASHSCOPE_MEDIA_API_KEY", "")
TOKEN = os.environ.get("MEDIA_GATEWAY_TOKEN", "")
app = FastAPI(title="CineCrew Local Media Adapter", docs_url=None, redoc_url=None)


def authorize(request: Request):
    if not TOKEN or not secrets.compare_digest(request.headers.get("authorization", ""), f"Bearer {TOKEN}"):
        raise HTTPException(401, "Invalid local adapter credential")


def checked(response):
    if response.status_code != 200:
        raise HTTPException(400, f"DashScope {response.status_code}: {response.code}: {response.message}")
    return response.output or {}


async def read_input(request):
    if request.headers.get("content-type", "").startswith("application/json"):
        return await request.json(), []
    form = await request.form(max_files=20, max_part_size=32 * 1024 * 1024)
    fields, uploads = {}, []
    for name, value in form.multi_items():
        if hasattr(value, "filename"):
            raw = await value.read(20 * 1024 * 1024 + 1)
            await value.close()
            if len(raw) > 20 * 1024 * 1024:
                raise HTTPException(413, "Reference image exceeds 20 MB")
            mime = mimetypes.guess_type(value.filename or "image.png")[0] or "image/png"
            uploads.append((name, f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"))
        else:
            fields[name] = value
    return fields, uploads


def configured():
    if not API_KEY or not BASE_URL:
        raise HTTPException(503, "DashScope media credentials or endpoint are not configured")
    dashscope.base_http_api_url = BASE_URL


def render_image(fields, uploads):
    if fields.get("model", Config.T2I_MODEL) != "wan2.7-image-pro":
        raise HTTPException(400, "This adapter is configured for wan2.7-image-pro")
    if int(fields.get("n", 1)) != 1:
        raise HTTPException(400, "Only n=1 is supported")
    configured()
    content = [{"image": uri} for name, uri in uploads if name in {"image", "image[]"}]
    content.append({"text": fields["prompt"]})
    parameters = {"n": 1, "size": fields.get("size", Config.T2I_SIZE).replace("x", "*"), "watermark": False}
    for name in ("negative_prompt", "seed"):
        if fields.get(name) not in (None, ""):
            parameters[name] = int(fields[name]) if name == "seed" else fields[name]
    output = checked(ImageGeneration.call(
        api_key=API_KEY, model="wan2.7-image-pro",
        messages=[{"role": "user", "content": content}], **parameters,
    ))
    for choice in output.get("choices", []):
        for part in choice.get("message", {}).get("content", []):
            if part.get("image"):
                return {"created": int(time.time()), "data": [{"url": part["image"]}]}
    raise HTTPException(502, "DashScope returned no image")


def submit_video(fields, uploads):
    model = fields.get("model", Config.VIDEO_MODEL)
    if model != "happyhorse-1.0-i2v":
        raise HTTPException(400, "This adapter is configured for happyhorse-1.0-i2v")
    references = [uri for name, uri in uploads if name == "input_reference"]
    if len(references) != 1 or any(fields.get(name) for name in ("last_frame", "last_frame_url", "media")):
        raise HTTPException(400, "HappyHorse I2V requires exactly one first frame; no tail-frame fallback is performed")
    try:
        duration = int(fields.get("seconds", "5"))
    except (TypeError, ValueError):
        raise HTTPException(400, "seconds must be an integer")
    if not 3 <= duration <= 15:
        raise HTTPException(400, "HappyHorse requires 3-15 seconds per clip; CineCrew timing was not changed")
    if fields.get("size", Config.VIDEO_SIZE) != "720x1280":
        raise HTTPException(400, "This run targets 720x1280; provide a 9:16 first frame")
    configured()
    parameters = {"resolution": "720P", "duration": duration, "watermark": False}
    if fields.get("seed") not in (None, ""):
        parameters["seed"] = int(fields["seed"])
    output = checked(VideoSynthesis.async_call(
        api_key=API_KEY, model=model, prompt=fields["prompt"],
        media=[{"type": "first_frame", "url": references[0]}], **parameters,
    ))
    if not output.get("task_id"):
        raise HTTPException(502, "DashScope returned no task id")
    return {"id": output["task_id"], "object": "video", "model": model, "status": "queued",
            "created_at": int(time.time()), "seconds": str(duration), "size": fields.get("size", Config.VIDEO_SIZE),
            "adapter_notes": "Prompt unchanged. fps/frame_num and voice presets are not provider controls; audio follows the resolved video prompt."}


def retrieve_video(task_id):
    if not task_id or any(c not in "0123456789abcdef-" for c in task_id):
        raise HTTPException(400, "Invalid DashScope task id")
    configured()
    response = requests.get(f"{BASE_URL}/tasks/{task_id}", headers={"Authorization": f"Bearer {API_KEY}"}, timeout=120)
    if response.status_code != 200:
        raise HTTPException(400, "DashScope task lookup failed")
    payload = response.json()
    output = payload.get("output", {})
    status = {"PENDING": "queued", "RUNNING": "in_progress", "SUCCEEDED": "completed", "FAILED": "failed", "CANCELED": "failed", "UNKNOWN": "failed"}.get(output.get("task_status"))
    if status is None:
        raise HTTPException(502, "Unrecognized DashScope task status")
    result = {"id": task_id, "object": "video", "status": status, "progress": 100 if status == "completed" else 0}
    if status == "failed":
        result["error"] = {"code": output.get("code", payload.get("code", "generation_failed")), "message": output.get("message", payload.get("message", "Task failed"))}
    return result, output


@app.get("/health")
def health():
    return {"ok": True, "configured": bool(API_KEY and TOKEN and BASE_URL), "image_model": Config.T2I_MODEL, "video_model": Config.VIDEO_MODEL}


@app.post("/v1/images/generations", dependencies=[Depends(authorize)])
@app.post("/v1/images/edits", dependencies=[Depends(authorize)])
async def images(request: Request):
    fields, uploads = await read_input(request)
    if not fields.get("prompt"):
        raise HTTPException(400, "prompt is required")
    return await run_in_threadpool(render_image, fields, uploads)


@app.post("/v1/videos", dependencies=[Depends(authorize)])
async def videos(request: Request):
    fields, uploads = await read_input(request)
    if not fields.get("prompt"):
        raise HTTPException(400, "prompt is required")
    return await run_in_threadpool(submit_video, fields, uploads)


@app.get("/v1/videos/{task_id}", dependencies=[Depends(authorize)])
def video(task_id: str):
    return retrieve_video(task_id)[0]


@app.get("/v1/videos/{task_id}/content", dependencies=[Depends(authorize)])
def video_content(task_id: str, variant: str = "video"):
    if variant != "video":
        raise HTTPException(404, "No spritesheet; CineCrew will use its FFmpeg fallback")
    result, output = retrieve_video(task_id)
    if result["status"] != "completed" or not output.get("video_url"):
        raise HTTPException(409, "Video is not ready")
    # Provider credentials must never be forwarded to the media host.
    response = requests.get(output["video_url"], timeout=120)
    response.raise_for_status()
    return Response(response.content, media_type="video/mp4")
