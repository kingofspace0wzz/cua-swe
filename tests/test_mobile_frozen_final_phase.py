"""Final evaluation uses one new phase without entering construction aggregation."""
import unittest
from types import SimpleNamespace

from cua_swe_bench.mobile_evaluation.core import Fault
from cua_swe_bench.mobile_evaluation.dispatch import validate_phase

class FinalPhaseTests(unittest.TestCase):
    def test_one_fresh_evaluation_slot(self):
        task = SimpleNamespace(c={"purpose": "candidate"})
        validate_phase(task, "evaluation", 1)
        for slot in (0, 2, 3, 4):
            with self.assertRaises(Fault):
                validate_phase(task, "evaluation", slot)

    def test_usability_cannot_be_evaluation(self):
        with self.assertRaises(Fault):
            validate_phase(SimpleNamespace(c={"purpose": "usability-control"}), "evaluation", 1)

if __name__ == "__main__":
    unittest.main()
