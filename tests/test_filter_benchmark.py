import unittest

from benchmarks.evaluate_filters import evaluate


class FilterBenchmarkTests(unittest.TestCase):
    def test_labelled_filter_precision_and_accuracy(self):
        metrics = evaluate()
        self.assertEqual(metrics["cases"], 30)
        self.assertGreaterEqual(metrics["precision"], 0.95)
        self.assertGreaterEqual(metrics["accuracy"], 0.95)


if __name__ == "__main__":
    unittest.main()
