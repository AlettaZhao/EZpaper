import unittest

import feishu_app_probe


class ProbeLoggingSecurityTests(unittest.TestCase):
    def test_redact_sensitive_fields_keeps_original_unchanged(self):
        response = {
            "code": 0,
            "tenant_access_token": "t-very-sensitive-token",
            "data": {
                "user_list": [
                    {"mobile": "13812345678", "user_id": "ou_sensitive_identifier"}
                ]
            },
        }

        redacted = feishu_app_probe.redact_sensitive_fields(response)

        self.assertEqual(redacted["code"], 0)
        self.assertNotIn("very-sensitive", redacted["tenant_access_token"])
        self.assertNotEqual(redacted["data"]["user_list"][0]["mobile"], "13812345678")
        self.assertEqual(response["tenant_access_token"], "t-very-sensitive-token")

    def test_short_sensitive_values_are_fully_masked(self):
        self.assertEqual(feishu_app_probe.mask_sensitive_value("ou_123"), "***")


if __name__ == "__main__":
    unittest.main()
