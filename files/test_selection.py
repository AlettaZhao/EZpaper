import os
import unittest

import main


def paper(paper_id, title, abstract, published="2026-08-18", categories=None):
    return {
        "id": paper_id,
        "title": title,
        "abstract": abstract,
        "url": f"https://arxiv.org/abs/{paper_id}",
        "authors": ["Test Author"],
        "published": published,
        "source": "arXiv",
        "categories": categories or [],
    }


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.old_require_core = main.REQUIRE_CORE_RELEVANCE
        self.old_allow_repeat = main.ALLOW_REPEAT_PAPERS
        self.old_min_score = main.MIN_RELEVANCE_SCORE
        self.old_use_sample = os.environ.pop("USE_SAMPLE_PAPERS", None)

        main.REQUIRE_CORE_RELEVANCE = True
        main.ALLOW_REPEAT_PAPERS = False
        main.MIN_RELEVANCE_SCORE = 4

    def tearDown(self):
        main.REQUIRE_CORE_RELEVANCE = self.old_require_core
        main.ALLOW_REPEAT_PAPERS = self.old_allow_repeat
        main.MIN_RELEVANCE_SCORE = self.old_min_score
        if self.old_use_sample is not None:
            os.environ["USE_SAMPLE_PAPERS"] = self.old_use_sample

    def test_dedupe_uses_arxiv_base_id(self):
        papers = [
            paper("2608.12345v2", "XR Motion Study", "virtual reality motion dataset"),
            paper("2608.12345v1", "XR Motion Study", "virtual reality motion dataset"),
        ]

        deduped = main.dedupe_papers(papers)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["id"], "2608.12345v2")
        self.assertEqual(deduped[0]["_history_key"], "2608.12345")

    def test_history_skips_sent_versions(self):
        papers = [paper("2608.12345v2", "XR Motion Study", "virtual reality motion dataset")]
        history = {
            "version": 1,
            "updated": "2026-08-18",
            "sent": {"2608.12345": {"sent_on": "2026-08-18", "last_version": "2608.12345v1"}},
        }

        unsent, skipped = main.filter_unsent_papers(papers, history)

        self.assertEqual(unsent, [])
        self.assertEqual(skipped, 1)

    def test_mark_sent_records_base_id(self):
        history = main.empty_sent_history()
        papers = [paper("2608.12345v2", "XR Motion Study", "virtual reality motion dataset")]

        changed = main.mark_papers_sent(history, papers)

        self.assertEqual(changed, 1)
        self.assertIn("2608.12345", history["sent"])
        self.assertNotIn("2608.12345v2", history["sent"])
        self.assertEqual(history["sent"]["2608.12345"]["last_version"], "2608.12345v2")

    def test_coarse_filter_rejects_generic_ml_without_core_context(self):
        papers = [
            paper(
                "2608.20001v1",
                "A Better Neural Network Benchmark",
                "We introduce a machine learning dataset and evaluation for neural networks.",
                categories=["cs.LG"],
            )
        ]
        stats = {}

        filtered = main.coarse_filter(papers, stats)

        self.assertEqual(filtered, [])
        self.assertEqual(stats.get("weak_relevance"), 1)

    def test_medical_mr_does_not_count_as_mixed_reality(self):
        papers = [
            paper(
                "2608.20003v1",
                "Automated ACL Footprint Identification Using 3D Deep Learning",
                "We evaluate a neural network on MR images and a medical imaging dataset.",
                categories=["cs.CV"],
            )
        ]
        stats = {}

        filtered = main.coarse_filter(papers, stats)

        self.assertEqual(filtered, [])
        self.assertEqual(stats.get("weak_relevance"), 1)

    def test_coarse_filter_accepts_xr_context(self):
        papers = [
            paper(
                "2608.20002v1",
                "Generating Synthetic Behavioral Populations from XR Motion",
                "We generate virtual reality motion trajectories for XR behavioral modeling and evaluate identification.",
                categories=["cs.HC"],
            )
        ]

        filtered = main.coarse_filter(papers, {})

        self.assertEqual(len(filtered), 1)
        self.assertIn("XR/空间交互", filtered[0]["_relevance_labels"])


if __name__ == "__main__":
    unittest.main()
