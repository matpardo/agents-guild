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
        "card": None,
        "lifecycle": "ready",
        "checks_failing": 0,
        "checks_billing": 0,
        "checks_passing": 3,
        "checks_pending": 0,
        "mergeable": "MERGEABLE",
        "review_decision": None,
        "unresolved_threads": None,
        "merge_state": None,
        "additions": 10,
        "deletions": 0,
        "created_at": "2026-09-01T10:00:00Z",
        "globs": [],
        "task_key": ("acme", "epic", "T{:02d}".format(number)),
        "dep_keys": [],
        "unmet_deps": [],
        "needs_ask_answer": False,
        "ask_id": None,
        "needs_human_pr_review": False,
        "branch": None,
        "base_branch": None,
        "fixes_main": False,
        "fixes_flaky": False,
        "blocked_external": None,
        "comments_after_head": None,
        "unseen_comments": 0,
        "ci_label": None,
        "trace_valid": None,
        "trace_reason": None,
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

    def test_needs_ask_answer_blocks(self):
        self.assertEqual(self._blocked_reasons(needs_ask_answer=True), ["needs ask answer"])

    def test_needs_ask_answer_is_a_label_and_the_action_names_the_reason(self):
        entry = self._entry(needs_ask_answer=True, party="beta")
        self.assertEqual(
            (entry["labels"], entry["action"]), (["needs-ask-answer"], "fix: needs ask answer \u2192 beta")
        )

    def test_review_flag_does_not_block_and_asks_for_a_human_review(self):
        entry = self._entry(needs_human_pr_review=True)
        self.assertEqual(
            (entry["state"], entry["labels"], entry["action"], entry["why"]),
            ("ready", ["needs-human-pr-review"], "review: human, then merge", "ready, checks \u27133"),
        )

    def test_labels_list_lifecycle_then_ask_then_review(self):
        entry = self._entry(lifecycle="converging", needs_ask_answer=True, needs_human_pr_review=True)
        self.assertEqual(entry["labels"], ["converging", "needs-ask-answer", "needs-human-pr-review"])

    def test_labels_put_the_urgency_marks_after_the_lifecycle(self):
        entry = self._entry(lifecycle="converging", fixes_main=True, fixes_flaky=True, needs_ask_answer=True)
        self.assertEqual(
            entry["labels"], ["converging", "fixes-main", "fixes-flaky", "needs-ask-answer"]
        )

    def test_the_entry_carries_the_branch(self):
        self.assertEqual(self._entry(branch="hotfix/main-red")["branch"], "hotfix/main-red")

    def test_the_entry_carries_no_branch_when_the_pr_has_none(self):
        self.assertIsNone(self._entry()["branch"])

    def test_draft_ready_with_the_review_flag_is_promoted_first(self):
        entry = self._entry(lifecycle="draft", needs_human_pr_review=True, party="beta")
        self.assertEqual(entry["action"], "promote: gh pr ready \u2192 beta")

    def test_review_flag_with_pending_checks_waits(self):
        entry = self._entry(needs_human_pr_review=True, checks_pending=1)
        self.assertEqual((entry["state"], entry["action"]), ("waiting", "wait: checks pending (1)"))

    def test_review_entry_is_not_a_next_action_target(self):
        prs = [_pr(1, checks_failing=1), _pr(2, needs_human_pr_review=True)]
        self.assertFalse(_by_ref(_compute(prs, []))[_ref(1)]["next_action"])

    def test_draft_and_converging_are_labels_not_blocked_reasons(self):
        for lifecycle in ("draft", "converging"):
            with self.subTest(lifecycle=lifecycle):
                entry = self._entry(lifecycle=lifecycle)
                self.assertEqual((entry["state"], entry["labels"]), ("ready", [lifecycle]))

    def test_failing_checks(self):
        self.assertEqual(self._blocked_reasons(checks_failing=2), ["checks failing (2)"])

    def test_billing_checks_show_a_label_and_do_not_block(self):
        entry = self._entry(checks_failing=2, checks_billing=1)
        self.assertEqual(entry["state"], "ready")
        self.assertIn("checks blocked by billing (2)", entry["labels"])

    def test_real_failures_keep_blocking_without_the_billing_flag(self):
        entry = self._entry(checks_failing=2, checks_billing=0)
        self.assertEqual(entry["blockers"], ["checks failing (2)"])
        self.assertNotIn("checks blocked by billing (2)", entry["labels"])

    def test_merge_conflict(self):
        self.assertEqual(self._blocked_reasons(mergeable="CONFLICTING"), ["merge conflict"])

    def test_changes_requested(self):
        self.assertEqual(self._blocked_reasons(review_decision="CHANGES_REQUESTED"), ["changes requested"])

    def test_unresolved_threads(self):
        self.assertEqual(self._blocked_reasons(unresolved_threads=1), ["1 unresolved thread"])
        self.assertEqual(self._blocked_reasons(unresolved_threads=2), ["2 unresolved threads"])

    def test_behind_base(self):
        self.assertEqual(self._blocked_reasons(merge_state="BEHIND"), ["behind base"])

    def test_dirty_blocked_and_empty_signals_are_ready(self):
        self.assertEqual(merge_queue.review_reasons(None, None, None, None), [])
        self.assertEqual(merge_queue.review_reasons("MERGEABLE", "APPROVED", 0, "DIRTY"), [])
        self.assertEqual(merge_queue.review_reasons("MERGEABLE", None, 0, "BLOCKED"), [])

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
            needs_ask_answer=True, checks_failing=1, mergeable="CONFLICTING", unmet_deps=["T09"]
        )
        self.assertEqual(
            reasons, ["needs ask answer", "checks failing (1)", "merge conflict", "waits on task T09"]
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


class StackTests(unittest.TestCase):
    def test_child_merges_after_its_base_despite_number_and_unblocks(self):
        prs = [_pr(1, base_branch="feat/base"), _pr(2, branch="feat/base"), _pr(3, dep_keys=[("acme", "epic", "T01")])]
        result = _compute(prs, [])
        self.assertEqual(_refs(result["queue"]), [_ref(2), _ref(1), _ref(3)])
        self.assertIn("stacked on", _by_ref(result)[_ref(1)]["why"])

    def test_child_waits_on_a_blocked_base(self):
        prs = [_pr(1, base_branch="feat/base"), _pr(2, branch="feat/base", needs_ask_answer=True)]
        entry = _by_ref(_compute(prs, []))[_ref(1)]
        self.assertEqual(entry["reasons"], ["waits on acme/app#2"])

    def test_prs_of_different_repos_are_not_linked(self):
        prs = [_pr(1, base_branch="feat/base"), _pr(2, repo="acme/other", ref="acme/other#2", branch="feat/base")]
        self.assertEqual(merge_queue.stack_pairs(prs), [])

    def test_missing_base_branch_is_ignored(self):
        self.assertEqual(merge_queue.stack_pairs([_pr(1), _pr(2, branch="feat/base")]), [])

    def test_merged_base_does_not_order_the_child(self):
        prs = [_pr(1, base_branch="feat/base"), _pr(2, branch="feat/base", lifecycle="merged")]
        self.assertEqual(_refs(_compute(prs, [])["queue"]), [_ref(1)])


class BlockedPlacementTests(unittest.TestCase):
    def test_blocked_pr_pinned_first_stays_first(self):
        result = _compute([_pr(1, needs_ask_answer=True), _pr(2), _pr(3)], [_pin(1, 3, "a")])
        self.assertEqual(_refs(result["queue"]), [_ref(1), _ref(2), _ref(3)])
        self.assertEqual([entry["state"] for entry in result["queue"]], ["blocked", "ready", "blocked"])

    def test_pin_to_a_blocked_pr_makes_the_pinned_pr_wait_on_it(self):
        result = _compute([_pr(1, needs_ask_answer=True), _pr(2), _pr(3)], [_pin(1, 3, "a")])
        entry = _by_ref(result)[_ref(3)]
        self.assertEqual(entry["reasons"], ["waits on acme/app#1"])
        self.assertEqual(entry["action"], "fix: waits on acme/app#1 \u2192 alpha")

    def test_waiting_propagates_through_chained_pins(self):
        prs = [_pr(1, needs_ask_answer=True), _pr(3), _pr(5)]
        result = _compute(prs, [_pin(1, 3, "a"), _pin(3, 5, "a")])
        self.assertEqual(_refs(result["queue"]), [_ref(1), _ref(3), _ref(5)])
        self.assertEqual(_by_ref(result)[_ref(5)]["reasons"], ["waits on acme/app#3"])

    def test_dependent_of_a_blocked_pr_waits_on_it(self):
        prs = [_pr(1, dep_keys=[("acme", "epic", "T02")]), _pr(2, needs_ask_answer=True)]
        result = _compute(prs, [])
        self.assertEqual(_refs(result["queue"]), [_ref(2), _ref(1)])
        self.assertEqual(_by_ref(result)[_ref(1)]["reasons"], ["waits on acme/app#2"])

    def test_dependent_of_a_ready_pr_stays_ready(self):
        prs = [_pr(1, dep_keys=[("acme", "epic", "T02")]), _pr(2)]
        self.assertEqual([entry["state"] for entry in _compute(prs, [])["queue"]], ["ready", "ready"])

    def test_blocked_pr_keeps_its_place_by_unblock_value(self):
        prs = [_pr(1), _pr(2, needs_ask_answer=True, globs=["a"]), _pr(3, globs=["a"])]
        result = _compute(prs, [])
        self.assertEqual(_refs(result["queue"]), [_ref(2), _ref(3), _ref(1)])

    def test_blocked_prs_count_in_overlap_unblocks(self):
        prs = [_pr(1, globs=["a"], checks_failing=1), _pr(2, globs=["a"])]
        self.assertEqual([entry["unblocks"] for entry in _compute(prs, [])["queue"]], [1, 1])

    def test_next_action_flags_the_first_blocked_entry_above_a_ready_one(self):
        prs = [_pr(1, needs_ask_answer=True), _pr(2, needs_ask_answer=True), _pr(3)]
        result = _compute(prs, [])
        self.assertEqual([entry["next_action"] for entry in result["queue"]], [True, False, False])

    def test_next_action_is_absent_when_no_ready_entry_follows(self):
        result = _compute([_pr(1), _pr(2, needs_ask_answer=True)], [])
        self.assertEqual([entry["next_action"] for entry in result["queue"]], [False, False])

    def test_next_action_ignores_a_promote_after_the_blocked_entry(self):
        prs = [_pr(1, needs_ask_answer=True), _pr(2, lifecycle="draft")]
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

    def test_successor_of_a_review_flagged_ready_pr_stays_ready(self):
        entry = self._successor_entry({"needs_human_pr_review": True})
        self.assertEqual((entry["state"], entry["reasons"]), ("ready", []))

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


def _human(prs, main=()):
    entry = merge_queue.compute(prs, [], list(main))["queue"][0]
    return entry["human_state"], entry["human_missing"]


def _billing_row(repo):
    return {"repo": repo, "source": "gh", "reason": "x", "external": "billing"}


class HumanReadyTests(unittest.TestCase):
    def test_green_head_is_ready(self):
        self.assertEqual(_human([_pr(1)]), ("ready", []))

    def test_comment_after_head_blocks_while_the_queue_state_stays_ready(self):
        entry = merge_queue.compute([_pr(1, comments_after_head=1)], [], [])["queue"][0]
        self.assertEqual((entry["state"], entry["action"]), ("ready", "merge"))
        self.assertEqual((entry["human_state"], entry["human_missing"]), ("blocked", ["1 comment after head"]))

    def test_several_comments_are_pluralized(self):
        self.assertEqual(_human([_pr(1, comments_after_head=2)]), ("blocked", ["2 comments after head"]))

    def test_unknown_comments_have_no_effect(self):
        self.assertEqual(_human([_pr(1, comments_after_head=None)]), ("ready", []))

    def test_draft_waits(self):
        self.assertEqual(_human([_pr(1, lifecycle="draft")]), ("waiting", []))

    def test_no_checks_without_label_waits(self):
        no_checks = {"checks_passing": 0}
        entry = merge_queue.compute([_pr(1, **no_checks)], [], [])["queue"][0]
        self.assertEqual(entry["why"], "ready, no checks")
        self.assertEqual((entry["human_state"], entry["human_missing"]), ("waiting", ["no checks on head"]))

    def test_no_checks_with_label_present_waits(self):
        self.assertEqual(
            _human([_pr(1, checks_passing=0, ci_label=1)]), ("waiting", ["no checks on head"])
        )

    def test_no_checks_with_label_absent_is_ci_pending(self):
        self.assertEqual(_human([_pr(1, checks_passing=0, ci_label=0)]), (merge_queue.CI_PENDING_STATE, []))

    def test_billing_classified_checks_are_ci_pending(self):
        pr = _pr(1, checks_failing=2, checks_passing=0, checks_billing=1)
        self.assertEqual(_human([pr]), (merge_queue.CI_PENDING_STATE, []))

    def test_main_billing_of_the_same_repo_makes_no_checks_ci_pending(self):
        pr = _pr(1, checks_passing=0)
        self.assertEqual(_human([pr], [_billing_row("acme/app")]), (merge_queue.CI_PENDING_STATE, []))

    def test_main_billing_of_another_repo_does_not(self):
        pr = _pr(1, checks_passing=0)
        self.assertEqual(_human([pr], [_billing_row("acme/web")]), ("waiting", ["no checks on head"]))

    def test_green_head_stays_ready_under_billing_main(self):
        self.assertEqual(_human([_pr(1)], [_billing_row("acme/app")]), ("ready", []))

    def test_real_failure_stays_blocked_under_billing_main(self):
        pr = _pr(1, checks_failing=1, checks_passing=0, checks_billing=0)
        self.assertEqual(_human([pr], [_billing_row("acme/app")]), ("blocked", []))

    def test_pending_checks_wait_even_when_the_label_is_absent(self):
        pr = _pr(1, checks_passing=0, checks_pending=1, ci_label=0)
        self.assertEqual(_human([pr]), ("waiting", []))

    def test_unresolved_threads_block_without_missing_items(self):
        self.assertEqual(_human([_pr(1, unresolved_threads=2)]), ("blocked", []))

    def test_draft_without_checks_has_no_missing_items(self):
        self.assertEqual(_human([_pr(1, lifecycle="draft", checks_passing=0)]), ("waiting", []))

    def _human_pair(self, first, second):
        result = merge_queue.compute([first, second], [_pin(first["number"], second["number"], "me")], [])
        return _by_ref(result)[second["ref"]]

    def test_successor_of_a_commented_predecessor_waits_while_the_queue_says_merge(self):
        entry = self._human_pair(_pr(1, comments_after_head=2), _pr(2))
        self.assertEqual((entry["state"], entry["action"]), ("ready", "merge"))
        self.assertEqual((entry["human_state"], entry["human_missing"]), ("waiting", [f"waits on {_ref(1)}"]))

    def test_successor_of_a_predecessor_without_checks_waits(self):
        entry = self._human_pair(_pr(1, checks_passing=0, ci_label=1), _pr(2))
        self.assertEqual((entry["human_state"], entry["human_missing"]), ("waiting", [f"waits on {_ref(1)}"]))

    def test_grandchild_waits_behind_a_not_ready_grandparent(self):
        prs = [_pr(1, comments_after_head=1), _pr(2), _pr(3)]
        pins = [_pin(1, 2, "me"), _pin(2, 3, "me")]
        entry = _by_ref(merge_queue.compute(prs, pins, []))[_ref(3)]
        self.assertEqual((entry["human_state"], entry["human_missing"]), ("waiting", [f"waits on {_ref(2)}"]))

    def test_ci_pending_predecessor_does_not_hold_the_successor(self):
        entry = self._human_pair(_pr(1, checks_passing=0, ci_label=0), _pr(2))
        self.assertEqual((entry["human_state"], entry["human_missing"]), ("ready", []))

    def test_ready_predecessor_does_not_hold_the_successor(self):
        entry = self._human_pair(_pr(1), _pr(2))
        self.assertEqual((entry["human_state"], entry["human_missing"]), ("ready", []))

    def test_invalid_trace_blocks_while_the_queue_state_stays_ready(self):
        entry = merge_queue.compute([_pr(1, trace_valid=0, trace_reason="no trace")], [], [])["queue"][0]
        self.assertEqual(entry["state"], "ready")
        self.assertEqual((entry["human_state"], entry["human_missing"]), ("blocked", ["review trace invalid: no trace"]))

    def test_unvalidated_trace_waits_with_its_reason(self):
        pr = _pr(1, trace_valid=None, trace_reason="validator timed out after 30s")
        self.assertEqual(
            _human([pr]), ("waiting", ["review trace not validated: validator timed out after 30s"])
        )

    def test_valid_and_unconfigured_traces_keep_ready(self):
        self.assertEqual(_human([_pr(1, trace_valid=1, trace_reason=None)]), ("ready", []))
        self.assertEqual(_human([_pr(1)]), ("ready", []))

    def test_successor_of_an_invalid_trace_waits(self):
        entry = self._human_pair(_pr(1, trace_valid=0, trace_reason="no trace"), _pr(2))
        self.assertEqual((entry["human_state"], entry["human_missing"]), ("waiting", [f"waits on {_ref(1)}"]))

    def test_draft_predecessor_names_the_wait_once(self):
        entry = self._human_pair(_pr(1, lifecycle="draft"), _pr(2))
        self.assertEqual(entry["human_missing"], [])


class MainStatusTests(unittest.TestCase):
    def test_main_rows_are_returned_ordered_by_repo_and_source(self):
        rows = [
            {"repo": "acme/web", "source": "gh", "reason": "x", "external": None},
            {"repo": "acme/app", "source": "manual", "reason": "y", "external": None},
            {"repo": "acme/app", "source": "gh", "reason": "z", "external": None},
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


class UrgencyOrderingTests(unittest.TestCase):
    def test_a_marked_pr_goes_first_among_free_prs(self):
        result = _compute([_pr(1), _pr(2, fixes_main=True), _pr(3)], [])
        self.assertEqual(_refs(result["queue"]), [_ref(2), _ref(1), _ref(3)])

    def test_the_flaky_mark_weighs_the_same_as_the_main_mark(self):
        result = _compute([_pr(1), _pr(2, fixes_flaky=True)], [])
        self.assertEqual(_refs(result["queue"]), [_ref(2), _ref(1)])

    def test_a_mark_beats_unblocking_more_prs(self):
        prs = [
            _pr(1, task_key=("acme", "epic", "T01")),
            _pr(2, task_key=("acme", "epic", "T02"), dep_keys=[("acme", "epic", "T01")]),
            _pr(3, fixes_main=True),
        ]
        result = _compute(prs, [])
        self.assertEqual(_refs(result["queue"]), [_ref(3), _ref(1), _ref(2)])

    def test_a_mark_never_jumps_a_task_dependency(self):
        prs = [
            _pr(1, task_key=("acme", "epic", "T01")),
            _pr(2, task_key=("acme", "epic", "T02"), dep_keys=[("acme", "epic", "T01")], fixes_main=True),
        ]
        result = _compute(prs, [])
        self.assertEqual(_refs(result["queue"]), [_ref(1), _ref(2)])

    def test_a_mark_never_jumps_a_pin(self):
        result = _compute([_pr(1), _pr(2, fixes_main=True)], [_pin(1, 2, "human")])
        self.assertEqual(_refs(result["queue"]), [_ref(1), _ref(2)])

    def test_both_marks_fall_back_to_the_number_tiebreak(self):
        result = _compute([_pr(2, fixes_main=True), _pr(1, fixes_flaky=True)], [])
        self.assertEqual(_refs(result["queue"]), [_ref(1), _ref(2)])

    def test_the_reason_names_the_mark_first(self):
        entry = _by_ref(_compute([_pr(1, fixes_main=True)], []))[_ref(1)]
        self.assertEqual(entry["why"], "fixes a broken main; ready, checks \u27133")

    def test_a_marked_pr_with_failing_checks_is_blocked_at_the_top(self):
        result = _compute([_pr(1), _pr(2, fixes_main=True, checks_failing=1)], [])
        self.assertEqual(_refs(result["queue"]), [_ref(2), _ref(1)])
        self.assertEqual(result["queue"][0]["state"], "blocked")


if __name__ == "__main__":
    unittest.main()


class ExternalBlockTests(unittest.TestCase):
    def test_flagged_pr_is_blocked_with_a_wait_action_and_keeps_its_place(self):
        result = merge_queue.compute(
            [_pr(1, blocked_external="team meeting"), _pr(2)], [], []
        )["queue"]
        self.assertEqual(_refs(result), [_ref(1), _ref(2)])
        self.assertEqual(result[0]["state"], "blocked")
        self.assertEqual(result[0]["reasons"], ["manual block: team meeting"])
        self.assertEqual(result[0]["action"], "manual block: team meeting")
        self.assertEqual(result[1]["action"], "merge")

    def test_pinned_dependent_is_blocked_and_waits_externally(self):
        result = merge_queue.compute(
            [_pr(1, blocked_external="team meeting"), _pr(2)], [_pin(1, 2, "alpha")], []
        )["queue"]
        self.assertEqual(result[1]["state"], "blocked")
        self.assertEqual(result[1]["reasons"], ["waits on {}".format(_ref(1))])
        self.assertEqual(result[1]["action"], "waits on manually blocked {}: team meeting".format(_ref(1)))
        self.assertEqual(result[1]["external"], "team meeting")

    def test_cross_repo_pin_propagates(self):
        other = _pr(3, repo="acme/docs", ref="acme/docs#3")
        pin = {"first": _ref(1), "second": "acme/docs#3", "author": "alpha"}
        result = merge_queue.compute([_pr(1, blocked_external="x"), other], [pin], [])["queue"]
        self.assertEqual(result[1]["external"], "x")

    def test_external_entry_is_not_the_next_action_target(self):
        result = merge_queue.compute(
            [_pr(1, blocked_external="x"), _pr(2, checks_failing=1), _pr(3)], [], []
        )["queue"]
        self.assertEqual([entry["next_action"] for entry in result], [False, True, False])


class ReadyForPersonTests(unittest.TestCase):
    def _selected(self, prs, pins, main):
        result = merge_queue.compute(prs, pins, main)
        return _refs(merge_queue.ready_for_person(result["queue"], result["main"]))

    def test_keeps_human_ready_prs_in_queue_order(self):
        prs = [_pr(1), _pr(2), _pr(3)]
        self.assertEqual(self._selected(prs, [_pin(3, 1, "alpha")], []), [_ref(3), _ref(1), _ref(2)])

    def test_drops_draft_waiting_blocked_and_manually_blocked(self):
        prs = [
            _pr(1),
            _pr(2, lifecycle="draft"),
            _pr(3, checks_failing=1),
            _pr(4, comments_after_head=1),
            _pr(5, blocked_external="vendor"),
        ]
        self.assertEqual(self._selected(prs, [], []), [_ref(1)])

    def test_keeps_ci_pending_and_the_human_review_pr(self):
        prs = [_pr(1, checks_passing=0, ci_label=0), _pr(2, needs_human_pr_review=True)]
        self.assertEqual(self._selected(prs, [], []), [_ref(1), _ref(2)])

    def test_red_main_drops_the_prs_of_that_repo_only(self):
        prs = [_pr(1), _pr(2, repo="acme/web", ref="acme/web#2")]
        red = {"repo": "acme/app", "source": "gh", "reason": "x", "external": None}
        self.assertEqual(self._selected(prs, [], [red]), ["acme/web#2"])

    def test_billing_main_keeps_the_prs(self):
        self.assertEqual(self._selected([_pr(1)], [], [_billing_row("acme/app")]), [_ref(1)])
