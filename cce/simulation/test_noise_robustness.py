import json
import tempfile
import unittest
from pathlib import Path

from cce.simulation.h1_h2_experiments import (
    DEFAULT_CONFIG,
    file_sha256,
    load_config,
)
from cce.simulation.noise_robustness import (
    DEFAULT_NOISE_CONFIG,
    load_noise_config,
    run_all,
    seeded_observations,
    write_results,
)


class NoiseRobustnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_all(load_config(), load_noise_config())
        cls.h1 = [
            row
            for row in cls.result["aggregate"]
            if row["experiment"] == "H1a-noise"
        ]
        cls.h2 = [
            row
            for row in cls.result["aggregate"]
            if row["experiment"] == "H2-noise"
        ]

    def test_same_seed_reproduces_same_observations(self):
        arguments = {
            "bases": [0.8] * 10,
            "seed": 41000,
            "mean": 0.0,
            "standard_deviation": 0.1,
            "lower": -1.0,
            "upper": 1.0,
        }
        self.assertEqual(
            seeded_observations(**arguments),
            seeded_observations(**arguments),
        )

    def test_different_seed_changes_observations(self):
        common = {
            "bases": [0.8] * 10,
            "mean": 0.0,
            "standard_deviation": 0.1,
            "lower": -1.0,
            "upper": 1.0,
        }
        self.assertNotEqual(
            seeded_observations(seed=41000, **common),
            seeded_observations(seed=41001, **common),
        )

    def test_run_count_is_100_for_each_of_nine_conditions(self):
        self.assertEqual(len(self.result["per_run"]), 900)
        self.assertEqual(len(self.result["aggregate"]), 9)
        self.assertTrue(all(row["runs"] == 100 for row in self.result["aggregate"]))

    def test_h1_median_cumulative_error_decreases_with_learning_rate(self):
        medians = [row["cumulative_model_error_median"] for row in self.h1]
        self.assertEqual(medians, sorted(medians, reverse=True))

    def test_h2_median_maximum_error_increases_with_learning_rate(self):
        medians = [row["maximum_model_error_median"] for row in self.h2]
        self.assertEqual(medians, sorted(medians))

    def test_quantile_bounds_contain_median(self):
        for row in self.result["aggregate"]:
            for metric in (
                "cumulative_model_error",
                "maximum_model_error",
                "proposal_mismatch_steps",
                "final_model_error",
            ):
                self.assertLessEqual(row[f"{metric}_q05"], row[f"{metric}_median"])
                self.assertLessEqual(row[f"{metric}_median"], row[f"{metric}_q95"])

    def test_output_files_are_written(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            write_results(self.result, output_dir)
            self.assertTrue((output_dir / "per_run.csv").is_file())
            self.assertTrue((output_dir / "aggregate.csv").is_file())
            self.assertTrue((output_dir / "metadata.json").is_file())
            metadata = json.loads(
                (output_dir / "metadata.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metadata["model_version"], "CCE-MVM-v0.1")
            self.assertEqual(
                metadata["specification_version"], "CCE-SPECIFICATION-v0.1"
            )
            self.assertEqual(
                metadata["config_sha256"], file_sha256(DEFAULT_NOISE_CONFIG)
            )
            self.assertEqual(
                metadata["base_config_sha256"], file_sha256(DEFAULT_CONFIG)
            )
            self.assertEqual(
                metadata["generator_module"],
                "cce.simulation.noise_robustness",
            )
            self.assertEqual(
                metadata["source_release_status"],
                "unreleased_internal_candidate",
            )
            self.assertEqual(metadata["independent_noise_sequences"], 100)
            self.assertEqual(metadata["conditions_per_noise_sequence"], 9)
            self.assertEqual(
                metadata["comparison_design"],
                "common_random_numbers_paired_across_conditions",
            )
            self.assertNotIn("python_version", metadata)
            self.assertNotIn("operating_system", metadata)


if __name__ == "__main__":
    unittest.main()
