"""Every authored exercise must actually run: reference solutions score 100%.

These tests are the contract between the content and the sandbox: a solution
that no longer passes, or a grader that accepts the starter stub, fails here.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "api"))

from runner_worker.policy import Policy  # noqa: E402
from runner_worker.execution import evaluate  # noqa: E402
from runner_worker.sandbox_kernel import landlock_abi  # noqa: E402

from app.runner_exercise_content import RUNNER_EXERCISES  # noqa: E402

ABI = landlock_abi()


@unittest.skipUnless(ABI >= 4, "kernel does not provide Landlock")
class AuthoredExerciseExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.TemporaryDirectory()
        cls.state = Path(cls.root.name)
        cls.policy = Policy("", "", cls.state, cls.state / "catalog.json", cls.state / "attestation.json",
                            backend="landlock")
        cls.policy.state.mkdir(parents=True, exist_ok=True)
        (cls.state / "catalog.json").write_text("[]", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.root.cleanup()

    def run_source(self, exercise, source):
        entry = {"cases": exercise["cases"]}
        request = {"source": source, "exercise_id": exercise["exercise_id"],
                   "exercise_version": exercise["version"]}
        return evaluate(self.policy, f"catalog-{exercise['exercise_id']}", request, entry)

    def test_reference_solutions_pass_every_case(self):
        failures = []
        for exercise_id, exercise in sorted(RUNNER_EXERCISES.items()):
            result = self.run_source(exercise, exercise["solution"])
            if result["status"] != "finished" or result["tests_passed"] != result["tests_total"]:
                failures.append((exercise_id, result["status"], result["tests_passed"],
                                 result["tests_total"], result.get("error_code")))
        self.assertEqual(failures, [], f"{len(failures)} exercises did not score 100%")

    def test_starter_code_never_scores_full_marks(self):
        accepted = []
        for exercise_id, exercise in sorted(RUNNER_EXERCISES.items()):
            entry = {"cases": [case for case in exercise["cases"] if case["visibility"] == "public"]}
            request = {"source": exercise["starter_code"], "exercise_id": exercise_id,
                       "exercise_version": exercise["version"]}
            result = evaluate(self.policy, f"starter-{exercise_id}", request, entry)
            if result["status"] == "finished" and result["tests_passed"] == result["tests_total"]:
                accepted.append(exercise_id)
        self.assertEqual(accepted, [], "starter code passed the grader for these exercises")

    def test_exercises_cover_every_visibility(self):
        for exercise_id, exercise in RUNNER_EXERCISES.items():
            with self.subTest(exercise=exercise_id):
                self.assertGreaterEqual(sum(case["visibility"] == "hidden" for case in exercise["cases"]), 1)
                self.assertGreaterEqual(sum(case["visibility"] == "public" for case in exercise["cases"]), 1)
                self.assertTrue(exercise["solution"].strip())


if __name__ == "__main__":
    unittest.main()
