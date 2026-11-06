# Better Call CineCrew: Consistent Ultra-Long Narrative-to-Film Generation
# Paper: ECCV 2026
# Licensed under the Apache License, Version 2.0
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.config import Config
from src.utils import generate_structured_data


class LocalLLMTests(unittest.TestCase):
    def test_qwen_thinking_is_disabled_only_on_dashscope(self):
        for model, endpoint, expected in [
            ("qwen3.5-plus", "https://dashscope.aliyuncs.com/compatible-mode/v1", {"enable_thinking": False}),
            ("other-model", "https://dashscope.aliyuncs.com/compatible-mode/v1", None),
            ("qwen3.5-plus", "https://example.invalid/v1", None),
        ]:
            with self.subTest(model=model, endpoint=endpoint):
                create = Mock(return_value=(object(), SimpleNamespace(usage=None)))
                client = SimpleNamespace(create_with_completion=create)
                with patch.object(Config, "LLM_BASE_URL", endpoint):
                    generate_structured_data(client, object, "system", "user", model=model)
                self.assertEqual(create.call_args.kwargs.get("extra_body"), expected)
                self.assertEqual(create.call_args.kwargs["messages"][1]["content"], "user")


if __name__ == "__main__":
    unittest.main()
