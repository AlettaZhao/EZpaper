import os
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

import check_config


class CheckConfigTests(unittest.TestCase):
    def test_webhook_only_channel_is_valid(self):
        env = {
            "FEISHU_WEBHOOKS": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
            "OPENAI_API_KEY": "sk-test",
        }
        with patch.dict(os.environ, env, clear=True):
            with patch.object(check_config, "load_env_file", return_value=None):
                with redirect_stdout(StringIO()):
                    check_config.main()

    def test_incomplete_app_channel_fails_even_with_webhook(self):
        env = {
            "FEISHU_OPEN_IDS": "ou_test",
            "FEISHU_WEBHOOKS": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
            "OPENAI_API_KEY": "sk-test",
        }
        with patch.dict(os.environ, env, clear=True):
            with patch.object(check_config, "load_env_file", return_value=None):
                with redirect_stdout(StringIO()):
                    with self.assertRaises(SystemExit):
                        check_config.main()


if __name__ == "__main__":
    unittest.main()
