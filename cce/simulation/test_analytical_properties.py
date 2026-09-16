import unittest

from cce.simulation.analytical_properties import (
    ema_closed_form,
    permanent_change_error,
    post_shock_model,
    synthetic_response_effect,
    temporary_shock_peak,
)
from cce.simulation.h1_h2_experiments import simulate_sequence
from cce.simulation.h1b_experiments import coupled_response, normalized_distance


class AnalyticalPropertiesTests(unittest.TestCase):
    def test_closed_form_matches_iterated_update(self):
        rate = 0.2
        steps = 7
        points = simulate_sequence(
            experiment="closed_form_check",
            learning_rate=rate,
            initial_model=-0.8,
            references=[0.8] * steps,
            observations=[0.8] * steps,
            risk_deduction=0.0,
        )
        expected = ema_closed_form(
            initial_model=-0.8,
            constant_observation=0.8,
            learning_rate=rate,
            steps=steps,
        )
        self.assertAlmostEqual(points[-1].model, expected)

    def test_zero_learning_preserves_initial_model(self):
        self.assertEqual(
            ema_closed_form(
                initial_model=-0.8,
                constant_observation=0.8,
                learning_rate=0.0,
                steps=100,
            ),
            -0.8,
        )

    def test_full_learning_uses_observation_after_one_step(self):
        self.assertEqual(
            ema_closed_form(
                initial_model=-0.8,
                constant_observation=0.8,
                learning_rate=1.0,
                steps=1,
            ),
            0.8,
        )

    def test_slower_learning_leaves_more_permanent_change_error(self):
        slow = permanent_change_error(
            initial_model=-0.8,
            new_reference=0.8,
            learning_rate=0.05,
            steps=5,
        )
        fast = permanent_change_error(
            initial_model=-0.8,
            new_reference=0.8,
            learning_rate=0.8,
            steps=5,
        )
        self.assertGreater(slow, fast)

    def test_faster_learning_moves_farther_during_same_temporary_shock(self):
        slow = temporary_shock_peak(
            stable_reference=0.8,
            shock_observation=-0.8,
            learning_rate=0.05,
            shock_steps=2,
        )
        fast = temporary_shock_peak(
            stable_reference=0.8,
            shock_observation=-0.8,
            learning_rate=0.8,
            shock_steps=2,
        )
        self.assertGreater(abs(fast - 0.8), abs(slow - 0.8))

    def test_post_shock_closed_form_returns_toward_reference(self):
        peak = temporary_shock_peak(
            stable_reference=0.8,
            shock_observation=-0.8,
            learning_rate=0.5,
            shock_steps=2,
        )
        recovered = post_shock_model(
            stable_reference=0.8,
            shock_observation=-0.8,
            learning_rate=0.5,
            shock_steps=2,
            recovery_steps=3,
        )
        self.assertLess(abs(recovered - 0.8), abs(peak - 0.8))

    def test_response_effect_formula_matches_simulated_coupling(self):
        baseline = 1.0
        proposal = -1.0
        for coupling in (0.0, 0.2, 0.5, 0.8, 1.0):
            response = coupled_response(baseline, proposal, coupling)
            observed = normalized_distance(response, baseline)
            expected = synthetic_response_effect(
                baseline=baseline,
                proposal=proposal,
                coupling=coupling,
            )
            self.assertAlmostEqual(observed, expected)

    def test_invalid_parameters_are_rejected(self):
        with self.assertRaises(ValueError):
            ema_closed_form(
                initial_model=0.0,
                constant_observation=0.0,
                learning_rate=1.1,
                steps=1,
            )
        with self.assertRaises(ValueError):
            synthetic_response_effect(
                baseline=0.0,
                proposal=0.0,
                coupling=-0.1,
            )


if __name__ == "__main__":
    unittest.main()

