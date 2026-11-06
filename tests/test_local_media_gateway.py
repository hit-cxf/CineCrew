# Better Call CineCrew: Consistent Ultra-Long Narrative-to-Film Generation
# Paper: ECCV 2026
# Licensed under the Apache License, Version 2.0
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from openai import OpenAI

import local_media_gateway as gateway
from src.adapters.t2i_client import T2IClient
from src.adapters.video_client import VideoClient
from src.schemas.video_jobs import VideoJob


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.patches = [patch.object(gateway, "TOKEN", "test-token"), patch.object(gateway, "API_KEY", "provider-secret"),
                        patch.object(gateway, "BASE_URL", "https://provider.invalid/api/v1"),
                        patch.object(gateway.Config, "T2I_MODEL", "wan2.7-image-pro"),
                        patch.object(gateway.Config, "VIDEO_MODEL", "happyhorse-1.0-i2v"),
                        patch.object(gateway.Config, "VIDEO_SIZE", "720x1280")]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.http = TestClient(gateway.app)
        self.addCleanup(self.http.close)
        self.sdk = OpenAI(api_key="test-token", base_url="http://testserver/v1", http_client=self.http, max_retries=0)

    def test_authentication(self):
        self.assertEqual(self.http.post("/v1/images/generations", json={"prompt": "x"}).status_code, 401)
        self.assertEqual(self.http.get("/health").status_code, 200)

    def test_image_edit_through_original_client_preserves_same_name_references(self):
        response = SimpleNamespace(status_code=200, output={"choices": [{"message": {"content": [{"image": "https://media.invalid/result"}]}}]})
        with TemporaryDirectory() as tmp:
            paths = []
            for index in range(2):
                path = Path(tmp) / str(index) / "front.png"
                path.parent.mkdir()
                path.write_bytes(bytes([index]))
                paths.append(str(path))
            client = T2IClient(api_key="test", base_url="http://testserver/v1")
            client._client = self.sdk
            with patch.object(gateway.ImageGeneration, "call", return_value=response) as call, \
                 patch("urllib.request.urlopen", return_value=io.BytesIO(b"generated")):
                result = client.render("original prompt", reference_images=paths, size="900x1600", seed=42)
            self.assertEqual(result, b"generated")
            data = call.call_args.kwargs
            self.assertEqual(data["size"], "900*1600")
            self.assertEqual(data["seed"], 42)
            self.assertEqual(data["messages"][0]["content"], [
                {"image": "data:image/png;base64,AA=="}, {"image": "data:image/png;base64,AQ=="}, {"text": "original prompt"}])
            self.assertTrue(all(Path(path).exists() for path in paths))

    def test_original_video_client_submit_wait_download(self):
        task_id = "12345678-1234-1234-1234-123456789abc"
        submitted = SimpleNamespace(status_code=200, output={"task_id": task_id})
        poll = Mock(status_code=200)
        poll.json.return_value = {"output": {"task_status": "SUCCEEDED", "video_url": "https://media.invalid/clip"}}
        media = Mock(content=b"video bytes")
        client = VideoClient(api_key="test", base_url="http://testserver/v1")
        client._client = self.sdk
        with TemporaryDirectory() as tmp:
            frame = Path(tmp) / "first.png"
            frame.write_bytes(b"frame")
            job = VideoJob(scene_id="scene", shot_id="shot", prompt="say the line", image_reference=str(frame),
                           duration=5, width=720, height=1280, fps=30)
            with patch.object(gateway.VideoSynthesis, "async_call", return_value=submitted) as call, \
                 patch.object(gateway.requests, "get", side_effect=[poll, poll, media]) as get:
                video_id = client.submit(job)
                self.assertEqual(client.wait(video_id).status, "completed")
                path = client.download(video_id, Path(tmp) / "clip.mp4")
                self.assertEqual(path.read_bytes(), b"video bytes")
            data = call.call_args.kwargs
            self.assertEqual(data["prompt"], "say the line")
            self.assertEqual(data["media"], [{"type": "first_frame", "url": "data:image/png;base64,ZnJhbWU="}])
            self.assertEqual(data["resolution"], "720P")
            self.assertEqual(data["duration"], 5)
            self.assertNotIn("ratio", data)
            self.assertNotIn("headers", get.call_args.kwargs)

    def test_short_clip_and_tail_frame_are_rejected_without_submission(self):
        for seconds, extra in [("1", {}), ("5", {"last_frame_url": "https://media.invalid/tail"})]:
            with self.subTest(seconds=seconds, extra=extra), patch.object(gateway.VideoSynthesis, "async_call") as call:
                response = self.http.post("/v1/videos", headers={"Authorization": "Bearer test-token"},
                    data={"model": "happyhorse-1.0-i2v", "prompt": "original", "seconds": seconds, "size": "720x1280", **extra},
                    files={"input_reference": ("first.png", b"frame", "image/png")})
                self.assertEqual(response.status_code, 400)
                call.assert_not_called()

    def test_failed_tasks_and_spritesheet_fallback(self):
        poll = Mock(status_code=200)
        poll.json.return_value = {"output": {"task_status": "FAILED", "code": "InvalidParameter", "message": "bad input"}}
        with patch.object(gateway.requests, "get", return_value=poll):
            result, _ = gateway.retrieve_video("abcd-1234")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["message"], "bad input")
        response = self.http.get("/v1/videos/abcd-1234/content?variant=spritesheet", headers={"Authorization": "Bearer test-token"})
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
