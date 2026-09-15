import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

import main


ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>https://arxiv.org/abs/2609.00001v1</id>
    <title>Resilient XR Systems</title>
    <summary>An XR paper about robust interaction.</summary>
    <published>2026-09-15T00:00:00Z</published>
    <author><name>Test Author</name></author>
    <arxiv:primary_category term="cs.HC" />
    <category term="cs.HC" />
  </entry>
</feed>
"""


class ArxivResilienceTests(unittest.TestCase):
    def test_fetch_recent_retries_after_timeout(self):
        with (
            patch.object(main, "ARXIV_RETRY_ATTEMPTS", 3),
            patch.object(main, "ARXIV_RETRY_BACKOFF_SECONDS", 0),
            patch.object(main, "get_text", side_effect=[TimeoutError("timed out"), ATOM_FEED]) as get_text,
        ):
            papers = main.fetch_recent("cs.HC", max_results=1)

        self.assertEqual(get_text.call_count, 2)
        self.assertEqual([paper["id"] for paper in papers], ["2609.00001v1"])

    def test_main_continues_when_one_category_fails(self):
        output = StringIO()
        with (
            patch.object(main, "CATEGORIES", ["cs.AI", "cs.HC"]),
            patch.object(main, "ARXIV_REQUEST_DELAY_SECONDS", 0),
            patch.object(main, "fetch_recent", side_effect=[RuntimeError("timeout"), []]),
            patch.object(main, "load_sent_history", return_value={}),
            patch.object(main, "prune_sent_history", return_value=0),
            patch.object(main, "select_daily_papers", return_value=([], {})),
            redirect_stdout(output),
        ):
            main.main()

        self.assertIn("1/2 个 arXiv 分类抓取失败", output.getvalue())
        self.assertIn("今天没有命中的新论文", output.getvalue())

    def test_main_fails_when_all_categories_fail(self):
        with (
            patch.object(main, "CATEGORIES", ["cs.AI", "cs.HC"]),
            patch.object(main, "ARXIV_REQUEST_DELAY_SECONDS", 0),
            patch.object(main, "fetch_recent", side_effect=RuntimeError("timeout")),
        ):
            with self.assertRaisesRegex(RuntimeError, "所有 arXiv 分类都抓取失败"):
                main.main()


if __name__ == "__main__":
    unittest.main()
