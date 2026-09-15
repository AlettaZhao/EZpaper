import os
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

import feishu


class FeishuDeliveryTests(unittest.TestCase):
    def test_build_daily_card_adds_abs_and_pdf_buttons(self):
        card = feishu.build_daily_card(
            [
                {
                    "id": "2608.12345v1",
                    "plain": "把复杂论文压成一句能看懂的话。",
                    "url": "https://arxiv.org/abs/2608.12345v1",
                    "context_line": "用户研究 · XR",
                    "detail_line": "arXiv · 2026 · 核心匹配：XR/空间交互",
                }
            ],
            "08月19日",
        )

        action_blocks = [item for item in card["elements"] if item.get("tag") == "action"]
        self.assertEqual(len(action_blocks), 1)
        actions = action_blocks[0]["actions"]
        self.assertEqual([button["text"]["content"] for button in actions], ["摘要页", "PDF"])
        self.assertEqual(actions[0]["url"], "https://arxiv.org/abs/2608.12345v1")
        self.assertEqual(actions[1]["url"], "https://arxiv.org/pdf/2608.12345v1")

    def test_send_card_to_open_ids_sends_app_and_webhook_targets(self):
        card = {"elements": []}
        old_secret = os.environ.get("FEISHU_WEBHOOK_SECRET")
        os.environ["FEISHU_WEBHOOK_SECRET"] = "secret"
        try:
            with patch.object(feishu, "send_via_app", return_value={"code": 0, "msg": "ok"}) as app_send:
                with patch.object(feishu, "send_via_webhook", return_value={"code": 0, "msg": "ok"}) as webhook_send:
                    with redirect_stdout(StringIO()):
                        results = feishu.send_card_to_open_ids(
                            card,
                            open_ids=["ou_1"],
                            webhooks=["https://example.com/hook"],
                        )
        finally:
            if old_secret is None:
                os.environ.pop("FEISHU_WEBHOOK_SECRET", None)
            else:
                os.environ["FEISHU_WEBHOOK_SECRET"] = old_secret

        app_send.assert_called_once_with(card, "ou_1")
        webhook_send.assert_called_once_with(card, "https://example.com/hook", "secret")
        self.assertEqual([item["channel"] for item in results], ["app", "webhook"])
        self.assertTrue(all(item["ok"] for item in results))

    def test_send_card_to_open_ids_reports_partial_failure(self):
        card = {"elements": []}
        with patch.object(feishu, "send_via_app", return_value={"code": 0, "msg": "ok"}):
            with patch.object(feishu, "send_via_webhook", side_effect=RuntimeError("bad webhook")):
                with redirect_stdout(StringIO()):
                    results = feishu.send_card_to_open_ids(
                        card,
                        open_ids=["ou_1"],
                        webhooks=["https://example.com/hook"],
                    )

        self.assertEqual(len(results), 2)
        self.assertTrue(results[0]["ok"])
        self.assertFalse(results[1]["ok"])
        self.assertEqual(results[1]["channel"], "webhook")

    def test_app_target_is_masked_in_logs(self):
        open_id = "ou_sensitive_identifier_1234"
        output = StringIO()
        with patch.object(feishu, "send_via_app", return_value={"code": 0, "msg": "ok"}):
            with redirect_stdout(output):
                feishu.send_card_to_open_ids(
                    {"elements": []},
                    open_ids=[open_id],
                    webhooks=[],
                )

        self.assertNotIn(open_id, output.getvalue())
        self.assertIn("ou_s…1234", output.getvalue())


if __name__ == "__main__":
    unittest.main()
