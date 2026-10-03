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
        "checks_pending": 0,
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


def _by_ref(result):
    return {entry["ref"]: entry for entry in result["queue"]}


def _compute(prs, pins):
    return merge_queue.compute(prs, pins, [])


class OrderingTests(unittest.TestCase):
    def test_independent_prs_are_ordered_by_number(self):
        result = _compute([_pr(3), _pr(1), _pr(2)], [])
        self.assertEqual(_refs(result["queue"]), [_ref(1), _ref(2), _ref(3)])

    def test_number_tiebreak_uses_the_repo_when_numbers_match(self):
        prs = [_pr(1, repo="acme/web", ref="acme/web#1"), _pr(1)]
        self.assertEqual(_refs(_compute(prs, [])["queue"]), [_ref(1), "acme/web#1"])

    def test_free_pr_is_ready_with_a_merge_action(self):
        entry = _compute([_pr(1)], [])["queue"][0]
        self.assertEqual(
            (entry["state"], entry["reasons"], entry["action"], entry["why"], entry["unblocks"]),
            ("ready", [], "merge", "ready, checks \u27133", 0),
        )

    def test_pr_without_checks_says_so(self):
        self.assertEqual(_compute([_pr(1, checks_passing=0)], [])["queue"][0]["why"], "ready, no checks")

    def test_task_dependency_puts_the_dependency_first(self):
        prs = [_pr(1, dep_keys=[("acme", "epic", "T02")]), _pr(2)]
        result = _compute(prs, [])
        self.assertEqual(_refs(result["queue"]), [_ref(2), _ref(1)])
        entries = _by_ref(result)
        self.assertEqual(
            entries[_ref(2)]["why"], "ready, checks \u27133; before acme/app#1 (task T01 depends on T02)"
        )
        self.assertEqual(entries[_ref(1)]["why"], "ready, checks \u27133; after acme/app#2 (needs task T02)")

    def test_more_unblocks_goes_first(self):
        prs = [_pr(1), _pr(2), _pr(3, globs=["a"]), _pr(4, globs=["a"]), _pr(5, globs=["a"])]
        result = _compute(prs, [])
        self.assertEqual(_refs(result["queue"]), [_ref(3), _ref(4), _ref(5), _ref(1), _ref(2)])
        self.assertEqual([entry["unblocks"] for entry in result["queue"]], [2, 2, 2, 0, 0])

    def test_unblocks_counts_transitive_dependents(self):
        prs = [
            _pr(1, dep_keys=[("acme", "epic", "T02")]),
            _pr(2, dep_keys=[("acme", "epic", "T03")]),
            _pr(3),
        ]
        result = _compute(prs, [])
        self.assertEqual(_refs(result["queue"]), [_ref(3), _ref(2), _ref(1)])
        self.assertEqual([entry["unblocks"] for entry in result["queue"]], [2, 1, 0])

    def test_unblocks_does_not_count_a_pr_twice(self):
        prs = [_pr(1, globs=["a"]), _pr(2, globs=["a"], dep_keys=[("acme", "epic", "T01")])]
        self.assertEqual(_by_ref(_compute(prs, []))[_ref(1)]["unblocks"], 1)

    def test_overlap_across_repos_does_not_unblock(self):
        prs = [_pr(2, globs=["a"]), _pr(1, repo="acme/web", ref="acme/web#1", globs=["a"])]
        result = _compute(prs, [])
        self.assertEqual([entry["unblocks"] for entry in result["queue"]], [0, 0])

    def test_prs_without_shared_globs_do_not_unblock(self):
        prs = [_pr(1, globs=["a"]), _pr(2, globs=["b"])]
        self.assertEqual([entry["unblocks"] for entry in _compute(prs, [])["queue"]], [0, 0])

    def test_pin_overrides_the_unblock_order(self):
        prs = [_pr(1), _pr(2, globs=["a"]), _pr(3, globs=["a"])]
        result = _compute(prs, [_pin(1, 2, "pre-piloto")])
        self.assertEqual(_refs(result["queue"]), [_ref(1), _ref(2), _ref(3)])
        entries = _by_ref(result)
        self.assertEqual(entries[_ref(1)]["why"], "ready, checks \u27133; pinned before acme/app#2 by pre-piloto")
        self.assertEqual(entries[_ref(2)]["why"], "ready, checks \u27133; pinned after acme/app#1 by pre-piloto")

    def test_pin_overrides_the_number_order(self):
        result = _compute([_pr(1), _pr(2)], [_pin(2, 1, None)])
        self.assertEqual(_refs(result["queue"]), [_ref(2), _ref(1)])
        self.assertIn("pinned before acme/app#1 by human", _by_ref(result)[_ref(2)]["why"])

    def test_pin_and_dependency_cycle_moves_the_involved_prs_to_the_end(self):
        prs = [_pr(1, dep_keys=[("acme", "epic", "T02")]), _pr(2), _pr(3)]
        result = _compute(prs, [_pin(1, 2, "alpha")])
        self.assertEqual(_refs(result["queue"]), [_ref(3), _ref(1), _ref(2)])
        entry = result["queue"][1]
        cycle = "ordering cycle between pins and task dependencies: acme/app#1, acme/app#2"
        self.assertEqual((entry["state"], entry["reasons"]), ("blocked", [cycle]))
        self.assertEqual(entry["action"], "fix: {} \u2192 alpha".format(cycle))


class StateTests(unittest.TestCase):
    def _entry(self, **overrides):
        return _compute([_pr(1, **overrides)], [])["queue"][0]

    def _blocked_reasons(self, **overrides):
        entry = self._entry(**overrides)
        self.assertEqual(entry["state"], "blocked")
        return entry["reasons"]

    def test_needs_human(self):
        self.assertEqual(self._blocked_reasons(lifecycle="needs-human"), ["needs-human"])

    def test_draft_and_converging_are_labels_not_blocked_reasons(self):
        for lifecycle in ("draft", "converging"):
            with self.subTest(lifecycle=lifecycle):
                entry = self._entry(lifecycle=lifecycle)
                self.assertEqual((entry["state"], entry["labels"]), ("ready", [lifecycle]))

    def test_failing_checks(self):
        self.assertEqual(self._blocked_reasons(checks_failing=2), ["checks failing (2)"])

    def test_merge_conflict(self):
        self.assertEqual(self._blocked_reasons(mergeable="CONFLICTING"), ["merge conflict"])

    def test_unknown_mergeable_state_is_not_a_conflict(self):
        result = _compute([_pr(1, mergeable=None), _pr(2, mergeable="UNKNOWN")], [])
        self.assertEqual([entry["state"] for entry in result["queue"]], ["ready", "ready"])

    def test_unmet_task_dependencies(self):
        self.assertEqual(
            self._blocked_reasons(unmet_deps=["T07", "T08"]),
            ["waits on task T07", "waits on task T08"],
        )

    def test_reasons_accumulate_in_a_fixed_order(self):
        reasons = self._blocked_reasons(
            lifecycle="needs-human", checks_failing=1, mergeable="CONFLICTING", unmet_deps=["T09"]
        )
        self.assertEqual(
            reasons, ["needs-human", "checks failing (1)", "merge conflict", "waits on task T09"]
        )

    def test_blocked_action_names_the_reasons_and_the_party(self):
        entry = self._entry(checks_failing=1, mergeable="CONFLICTING", party="beta")
        self.assertEqual(entry["action"], "fix: checks failing (1); merge conflict \u2192 beta")

    def test_pending_checks_make_the_pr_wait(self):
        entry = self._entry(checks_pending=2)
        self.assertEqual(
            (entry["state"], entry["reasons"], entry["action"], entry["why"]),
            ("waiting", ["checks pending (2)"], "wait: checks pending (2)", ""),
        )

    def test_failing_and_pending_checks_block(self):
        entry = self._entry(checks_failing=1, checks_pending=2)
        self.assertEqual((entry["state"], entry["reasons"]), ("blocked", ["checks failing (1)"]))

    def test_ready_draft_is_promoted(self):
        entry = self._entry(lifecycle="draft", party="beta")
        self.assertEqual(
            (entry["state"], entry["action"], entry["why"]),
            ("ready", "promote: gh pr ready \u2192 beta", "ready, checks \u27133"),
        )

    def test_draft_with_a_conflict_is_blocked(self):
        entry = self._entry(lifecycle="draft", mergeable="CONFLICTING", party="beta")
        self.assertEqual(
            (entry["state"], entry["action"]), ("blocked", "fix: merge conflict \u2192 beta")
        )

    def test_converging_with_pending_checks_waits(self):
        entry = self._entry(lifecycle="converging", checks_pending=1)
        self.assertEqual((entry["state"], entry["labels"]), ("waiting", ["converging"]))

    def test_entry_carries_the_pr_identity(self):
        entry = _compute([_pr(4, lifecycle="draft", party="beta")], [])["queue"][0]
        self.assertEqual((entry["ref"], entry["party"], entry["task"]), (_ref(4), "beta", "demo/T04"))

    def test_pr_without_a_task_has_no_task_label(self):
        result = _compute([_pr(4, quest=None, tid=None, task_key=None)], [])
        self.assertIsNone(result["queue"][0]["task"])

    def test_merged_and_closed_prs_never_appear(self):
        result = _compute([_pr(1, lifecycle="merged"), _pr(2, lifecycle="closed"), _pr(3)], [])
        self.assertEqual(_refs(result["queue"]), [_ref(3)])

    def test_pin_involving_a_merged_pr_is_ignored(self):
        prs = [_pr(1, lifecycle="merged"), _pr(2), _pr(3)]
        result = _compute(prs, [_pin(1, 3, "a"), _pin(3, 1, "a")])
        self.assertEqual(_refs(result["queue"]), [_ref(2), _ref(3)])
        self.assertNotIn("pinned", _by_ref(result)[_ref(3)]["why"])


class BlockedPlacementTests(unittest.TestCase):
    def test_blocked_pr_pinned_first_stays_first(self):
        result = _compute([_pr(1, lifecycle="needs-human"), _pr(2), _pr(3)], [_pin(1, 3, "a")])
        self.assertEqual(_refs(result["queue"]), [_ref(1), _ref(2), _ref(3)])
        self.assertEqual([entry["state"] for entry in result["queue"]], ["blocked", "ready", "blocked"])

    def test_pin_to_a_blocked_pr_makes_the_pinned_pr_wait_on_it(self):
        result = _compute([_pr(1, lifecycle="needs-human"), _pr(2), _pr(3)], [_pin(1, 3, "a")])
        entry = _by_ref(result)[_ref(3)]
        self.assertEqual(entry["reasons"], ["waits on acme/app#1"])
        self.assertEqual(entry["action"], "fix: waits on acme/app#1 \u2192 alpha")

    def test_waiting_propagates_through_chained_pins(self):
        prs = [_pr(1, lifecycle="needs-human"), _pr(3), _pr(5)]
        result = _compute(prs, [_pin(1, 3, "a"), _pin(3, 5, "a")])
        self.assertEqual(_refs(result["queue"]), [_ref(1), _ref(3), _ref(5)])
        self.assertEqual(_by_ref(result)[_ref(5)]["reasons"], ["waits on acme/app#3"])

    def test_dependent_of_a_blocked_pr_waits_on_it(self):
        prs = [_pr(1, dep_keys=[("acme", "epic", "T02")]), _pr(2, lifecycle="needs-human")]
        result = _compute(prs, [])
        self.assertEqual(_refs(result["queue"]), [_ref(2), _ref(1)])
        self.assertEqual(_by_ref(result)[_ref(1)]["reasons"], ["waits on acme/app#2"])

    def test_dependent_of_a_ready_pr_stays_ready(self):
        prs = [_pr(1, dep_keys=[("acme", "epic", "T02")]), _pr(2)]
        self.assertEqual([entry["state"] for entry in _compute(prs, [])["queue"]], ["ready", "ready"])

    def test_blocked_pr_keeps_its_place_by_unblock_value(self):
        prs = [_pr(1), _pr(2, lifecycle="needs-human", globs=["a"]), _pr(3, globs=["a"])]
        result = _compute(prs, [])
        self.assertEqual(_refs(result["queue"]), [_ref(2), _ref(3), _ref(1)])

    def test_blocked_prs_count_in_overlap_unblocks(self):
        prs = [_pr(1, globs=["a"], checks_failing=1), _pr(2, globs=["a"])]
        self.assertEqual([entry["unblocks"] for entry in _compute(prs, [])["queue"]], [1, 1])

    def test_next_action_flags_the_first_blocked_entry_above_a_ready_one(self):
        prs = [_pr(1, lifecycle="needs-human"), _pr(2, lifecycle="needs-human"), _pr(3)]
        result = _compute(prs, [])
        self.assertEqual([entry["next_action"] for entry in result["queue"]], [True, False, False])

    def test_next_action_is_absent_when_no_ready_entry_follows(self):
        result = _compute([_pr(1), _pr(2, lifecycle="needs-human")], [])
        self.assertEqual([entry["next_action"] for entry in result["queue"]], [False, False])

    def test_next_action_ignores_a_promote_after_the_blocked_entry(self):
        prs = [_pr(1, lifecycle="needs-human"), _pr(2, lifecycle="draft")]
        result = _compute(prs, [])
        self.assertEqual([entry["next_action"] for entry in result["queue"]], [False, False])

    def test_next_action_is_absent_when_everything_is_ready(self):
        result = _compute([_pr(1), _pr(2)], [])
        self.assertEqual([entry["next_action"] for entry in result["queue"]], [False, False])


class WaitingPropagationTests(unittest.TestCase):
    def _successor_entry(self, predecessor):
        prs = [_pr(1, dep_keys=[("acme", "epic", "T02")]), _pr(2, **predecessor)]
        return _by_ref(_compute(prs, []))[_ref(1)]

    def test_successor_of_a_draft_ready_pr_waits(self):
        entry = self._successor_entry({"lifecycle": "draft"})
        self.assertEqual(
            (entry["state"], entry["reasons"], entry["action"]),
            ("waiting", ["waits on acme/app#2"], "wait: waits on acme/app#2"),
        )

    def test_successor_of_a_waiting_pr_waits(self):
        entry = self._successor_entry({"checks_pending": 1})
        self.assertEqual((entry["state"], entry["reasons"]), ("waiting", ["waits on acme/app#2"]))

    def test_successor_of_a_blocked_pr_is_blocked(self):
        entry = self._successor_entry({"checks_failing": 1})
        self.assertEqual((entry["state"], entry["reasons"]), ("blocked", ["waits on acme/app#2"]))

    def test_waiting_propagates_through_a_chain(self):
        prs = [_pr(1, checks_pending=1), _pr(3), _pr(5)]
        result = _compute(prs, [_pin(1, 3, "a"), _pin(3, 5, "a")])
        self.assertEqual(
            [entry["state"] for entry in result["queue"]], ["waiting", "waiting", "waiting"]
        )

    def test_blocked_beats_waiting(self):
        prs = [_pr(1, checks_failing=1), _pr(2, checks_pending=1), _pr(3)]
        result = _compute(prs, [_pin(1, 3, "a"), _pin(2, 3, "a")])
        entry = _by_ref(result)[_ref(3)]
        self.assertEqual((entry["state"], entry["reasons"]), ("blocked", ["waits on acme/app#1"]))

    def test_waiting_entry_does_not_flag_next_action(self):
        result = _compute([_pr(1, checks_pending=1), _pr(2)], [])
        self.assertEqual([entry["next_action"] for entry in result["queue"]], [False, False])


class MainStatusTests(unittest.TestCase):
    def test_main_rows_are_returned_ordered_by_repo_and_source(self):
        rows = [
            {"repo": "acme/web", "source": "gh", "reason": "x"},
            {"repo": "acme/app", "source": "manual", "reason": "y"},
            {"repo": "acme/app", "source": "gh", "reason": "z"},
        ]
        result = merge_queue.compute([_pr(1)], [], rows)
        self.assertEqual(
            [(row["repo"], row["source"]) for row in result["main"]],
            [("acme/app", "gh"), ("acme/app", "manual"), ("acme/web", "gh")],
        )

    def test_no_main_rows_means_an_empty_main_list(self):
        self.assertEqual(_compute([_pr(1)], [])["main"], [])


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
