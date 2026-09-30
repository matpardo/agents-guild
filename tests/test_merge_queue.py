import unittest

from guild import merge_queue


def _ref(number):
    return "acme/app#{}".format(number)


def _pr(number, **overrides):
    pr = {
        "ref": _ref(number),
        "repo": "acme/app",
        "number": number,
        "party": "alpha",
        "quest": "demo",
        "tid": "T{:02d}".format(number),
        "lifecycle": "ready",
        "checks_failing": 0,
        "checks_passing": 3,
        "mergeable": "MERGEABLE",
        "additions": 10,
        "deletions": 0,
        "created_at": "2026-09-01T10:00:00Z",
        "globs": [],
        "task_key": ("acme", "epic", "T{:02d}".format(number)),
        "dep_keys": [],
        "unmet_deps": [],
    }
    pr.update(overrides)
    return pr


def _pin(first, second, author):
    return {"first": _ref(first), "second": _ref(second), "author": author}


def _refs(entries):
    return [entry["ref"] for entry in entries]


def _reasons(result):
    return {entry["ref"]: entry["reason"] for entry in result["queue"]}


class OrderingTests(unittest.TestCase):
    def test_independent_prs_are_ordered_by_number(self):
        result = merge_queue.compute([_pr(3), _pr(1), _pr(2)], [])
        self.assertEqual(_refs(result["queue"]), [_ref(1), _ref(2), _ref(3)])
        self.assertEqual(result["blocked"], [])

    def test_position_reason_for_a_free_pr(self):
        result = merge_queue.compute([_pr(1)], [])
        self.assertEqual(_reasons(result), {_ref(1): "ready, checks ✓3"})

    def test_pr_without_checks_says_so(self):
        result = merge_queue.compute([_pr(1, checks_passing=0)], [])
        self.assertEqual(_reasons(result), {_ref(1): "ready, no checks"})

    def test_task_dependency_puts_the_dependency_first(self):
        prs = [_pr(1, dep_keys=[("acme", "epic", "T02")]), _pr(2)]
        result = merge_queue.compute(prs, [])
        self.assertEqual(_refs(result["queue"]), [_ref(2), _ref(1)])
        reasons = _reasons(result)
        self.assertEqual(
            reasons[_ref(2)], "ready, checks ✓3; before acme/app#1 (task T01 depends on T02)"
        )
        self.assertEqual(reasons[_ref(1)], "ready, checks ✓3; after acme/app#2 (needs task T02)")

    def test_overlap_puts_the_smaller_diff_first(self):
        prs = [
            _pr(1, globs=["config/locales/es.yml"], additions=50, deletions=10),
            _pr(2, globs=["config/locales/es.yml"], additions=5, deletions=1),
        ]
        result = merge_queue.compute(prs, [])
        self.assertEqual(_refs(result["queue"]), [_ref(2), _ref(1)])
        reasons = _reasons(result)
        self.assertEqual(
            reasons[_ref(2)],
            "ready, checks ✓3; before acme/app#1 (shares config/locales/es.yml, smaller diff)",
        )
        self.assertEqual(
            reasons[_ref(1)], "ready, checks ✓3; after acme/app#2 (shares config/locales/es.yml)"
        )

    def test_overlap_with_equal_diff_puts_the_earlier_created_first(self):
        prs = [
            _pr(1, globs=["a"], created_at="2026-09-02T10:00:00Z"),
            _pr(2, globs=["a"], created_at="2026-09-01T10:00:00Z"),
        ]
        result = merge_queue.compute(prs, [])
        self.assertEqual(_refs(result["queue"]), [_ref(2), _ref(1)])
        self.assertIn("(shares a, created earlier)", _reasons(result)[_ref(2)])

    def test_overlap_with_equal_diff_and_time_puts_the_lower_number_first(self):
        result = merge_queue.compute([_pr(2, globs=["a"]), _pr(1, globs=["a"])], [])
        self.assertEqual(_refs(result["queue"]), [_ref(1), _ref(2)])
        self.assertIn("(shares a, lower number)", _reasons(result)[_ref(1)])

    def test_overlap_lists_every_shared_glob(self):
        prs = [_pr(1, globs=["b", "a"]), _pr(2, globs=["a", "b", "c"])]
        result = merge_queue.compute(prs, [])
        self.assertIn("(shares a, b, lower number)", _reasons(result)[_ref(1)])

    def test_overlap_along_a_task_dependency_keeps_both_reasons(self):
        prs = [
            _pr(1, globs=["a"], additions=9, dep_keys=[("acme", "epic", "T02")]),
            _pr(2, globs=["a"], additions=1),
        ]
        result = merge_queue.compute(prs, [])
        self.assertEqual(_refs(result["queue"]), [_ref(2), _ref(1)])
        self.assertEqual(
            _reasons(result)[_ref(2)],
            "ready, checks \u27133; before acme/app#1 (task T01 depends on T02);"
            " before acme/app#1 (shares a, smaller diff)",
        )

    def test_overlap_across_repos_is_not_sequential(self):
        prs = [_pr(2, globs=["a"], additions=1), _pr(1, repo="acme/web", ref="acme/web#1", globs=["a"])]
        result = merge_queue.compute(prs, [])
        self.assertEqual(_refs(result["queue"]), ["acme/web#1", _ref(2)])
        self.assertNotIn("shares", _reasons(result)["acme/web#1"])

    def test_prs_without_shared_globs_do_not_overlap(self):
        prs = [_pr(1, globs=["a"]), _pr(2, globs=["b"])]
        result = merge_queue.compute(prs, [])
        self.assertNotIn("shares", _reasons(result)[_ref(1)])

    def test_pin_overrides_the_overlap_order(self):
        prs = [
            _pr(1, globs=["a"], additions=50),
            _pr(2, globs=["a"], additions=5),
        ]
        result = merge_queue.compute(prs, [_pin(1, 2, "pre-piloto")])
        self.assertEqual(_refs(result["queue"]), [_ref(1), _ref(2)])
        reasons = _reasons(result)
        self.assertEqual(reasons[_ref(1)], "ready, checks ✓3; pinned before acme/app#2 by pre-piloto")
        self.assertEqual(reasons[_ref(2)], "ready, checks ✓3; pinned after acme/app#1 by pre-piloto")

    def test_pin_overrides_the_number_order_without_overlap(self):
        result = merge_queue.compute([_pr(1), _pr(2)], [_pin(2, 1, None)])
        self.assertEqual(_refs(result["queue"]), [_ref(2), _ref(1)])
        self.assertIn("pinned before acme/app#1 by human", _reasons(result)[_ref(2)])

    def test_transitive_overlaps_stay_sequential(self):
        prs = [
            _pr(1, globs=["a"], additions=30),
            _pr(2, globs=["a"], additions=20),
            _pr(3, globs=["a"], additions=10),
        ]
        result = merge_queue.compute(prs, [])
        self.assertEqual(_refs(result["queue"]), [_ref(3), _ref(2), _ref(1)])

    def test_pin_and_dependency_cycle_blocks_the_involved_prs(self):
        prs = [_pr(1, dep_keys=[("acme", "epic", "T02")]), _pr(2), _pr(3)]
        result = merge_queue.compute(prs, [_pin(1, 2, "alpha")])
        self.assertEqual(_refs(result["queue"]), [_ref(3)])
        self.assertEqual([entry["ref"] for entry in result["blocked"]], [_ref(1), _ref(2)])
        self.assertEqual(
            result["blocked"][0]["reasons"],
            ["ordering cycle between pins and task dependencies: acme/app#1, acme/app#2"],
        )

    def test_pin_against_the_heuristic_does_not_create_a_cycle_with_overlap(self):
        prs = [_pr(1, globs=["a"], additions=1), _pr(2, globs=["a"], additions=9)]
        result = merge_queue.compute(prs, [_pin(2, 1, "alpha")])
        self.assertEqual(_refs(result["queue"]), [_ref(2), _ref(1)])
        self.assertEqual(result["blocked"], [])


class EligibilityTests(unittest.TestCase):
    def _blocked_reasons(self, **overrides):
        result = merge_queue.compute([_pr(1, **overrides)], [])
        self.assertEqual(result["queue"], [])
        return result["blocked"][0]["reasons"]

    def test_needs_human(self):
        self.assertEqual(self._blocked_reasons(lifecycle="needs-human"), ["needs-human"])

    def test_draft(self):
        self.assertEqual(self._blocked_reasons(lifecycle="draft"), ["draft"])

    def test_converging(self):
        self.assertEqual(self._blocked_reasons(lifecycle="converging"), ["converging"])

    def test_failing_checks(self):
        self.assertEqual(self._blocked_reasons(checks_failing=2), ["checks failing (2)"])

    def test_merge_conflict(self):
        self.assertEqual(self._blocked_reasons(mergeable="CONFLICTING"), ["merge conflict"])

    def test_unknown_mergeable_state_is_not_a_conflict(self):
        result = merge_queue.compute([_pr(1, mergeable=None), _pr(2, mergeable="UNKNOWN")], [])
        self.assertEqual(_refs(result["queue"]), [_ref(1), _ref(2)])

    def test_unmet_task_dependencies(self):
        self.assertEqual(
            self._blocked_reasons(unmet_deps=["T07", "T08"]),
            ["waits on task T07", "waits on task T08"],
        )

    def test_reasons_accumulate_in_a_fixed_order(self):
        reasons = self._blocked_reasons(
            lifecycle="converging", checks_failing=1, mergeable="CONFLICTING", unmet_deps=["T09"]
        )
        self.assertEqual(
            reasons, ["converging", "checks failing (1)", "merge conflict", "waits on task T09"]
        )

    def test_blocked_entry_carries_the_pr_identity(self):
        result = merge_queue.compute([_pr(4, lifecycle="draft", party="beta")], [])
        entry = result["blocked"][0]
        self.assertEqual((entry["ref"], entry["party"], entry["task"]), (_ref(4), "beta", "demo/T04"))

    def test_pr_without_a_task_has_no_task_label(self):
        result = merge_queue.compute([_pr(4, quest=None, tid=None, task_key=None)], [])
        self.assertIsNone(result["queue"][0]["task"])

    def test_merged_and_closed_prs_never_appear(self):
        result = merge_queue.compute([_pr(1, lifecycle="merged"), _pr(2, lifecycle="closed"), _pr(3)], [])
        self.assertEqual(_refs(result["queue"]), [_ref(3)])
        self.assertEqual(result["blocked"], [])

    def test_pin_involving_a_merged_pr_is_ignored(self):
        result = merge_queue.compute([_pr(1, lifecycle="merged"), _pr(2), _pr(3)], [_pin(1, 3, "a"), _pin(3, 1, "a")])
        self.assertEqual(_refs(result["queue"]), [_ref(2), _ref(3)])
        self.assertNotIn("pinned", _reasons(result)[_ref(3)])

    def test_pin_involving_a_blocked_pr_is_ignored(self):
        result = merge_queue.compute([_pr(1, lifecycle="draft"), _pr(2), _pr(3)], [_pin(3, 1, "a")])
        self.assertEqual(_refs(result["queue"]), [_ref(2), _ref(3)])

    def test_blocked_prs_do_not_take_part_in_overlap(self):
        prs = [_pr(1, globs=["a"], checks_failing=1), _pr(2, globs=["a"])]
        result = merge_queue.compute(prs, [])
        self.assertNotIn("shares", _reasons(result)[_ref(2)])

    def test_dependency_on_a_blocked_pr_adds_no_edge(self):
        prs = [_pr(1, dep_keys=[("acme", "epic", "T02")]), _pr(2, lifecycle="draft")]
        result = merge_queue.compute(prs, [])
        self.assertEqual(_refs(result["queue"]), [_ref(1)])


class GraphHelperTests(unittest.TestCase):
    def test_find_path_returns_the_shortest_path(self):
        pairs = [("a", "b"), ("b", "c"), ("a", "c"), ("c", "d")]
        self.assertEqual(merge_queue.find_path(pairs, "a", "d"), ["a", "c", "d"])

    def test_find_path_returns_none_when_unreachable(self):
        self.assertIsNone(merge_queue.find_path([("a", "b")], "b", "a"))

    def test_dependency_pairs_link_dependency_to_dependent(self):
        prs = [_pr(1, dep_keys=[("acme", "epic", "T02")]), _pr(2)]
        self.assertEqual(merge_queue.dependency_pairs(prs), [(_ref(2), _ref(1))])

    def test_dependency_pairs_ignore_a_pr_depending_on_its_own_task(self):
        prs = [_pr(1, dep_keys=[("acme", "epic", "T01")])]
        self.assertEqual(merge_queue.dependency_pairs(prs), [])


if __name__ == "__main__":
    unittest.main()
