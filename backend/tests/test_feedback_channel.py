import pytest

from across_agents_assistant.legacy_task_history.models import Feedback
from across_agents_assistant.task_review.feedback import FeedbackChannel


class TestFeedbackChannel:
    def test_submit_returns_feedback_id(self):
        channel = FeedbackChannel()
        feedback = Feedback(
            feedback_id="",
            feedback_type="suggestion",
            from_agent="agent-1",
            to_agent="agent-2",
            target="artifact-1",
            observed="slow",
            expected="fast",
        )
        fid = channel.submit(feedback)
        assert fid
        assert fid.startswith("fb-")

    def test_submit_persists_in_memory(self):
        channel = FeedbackChannel()
        feedback = Feedback(
            feedback_id="fb-001",
            feedback_type="suggestion",
            from_agent="agent-1",
            to_agent="agent-2",
            target="artifact-1",
            observed="slow",
            expected="fast",
        )
        channel.submit(feedback)
        assert channel._feedbacks["fb-001"] is feedback
        assert "agent-2" in channel._pending_by_agent
        assert "fb-001" in channel._pending_by_agent["agent-2"]

    def test_get_pending_for_agent(self):
        channel = FeedbackChannel()
        fb1 = Feedback(
            feedback_id="fb-001",
            feedback_type="suggestion",
            from_agent="agent-1",
            to_agent="agent-2",
            target="artifact-1",
            observed="slow",
            expected="fast",
        )
        fb2 = Feedback(
            feedback_id="fb-002",
            feedback_type="bug",
            from_agent="agent-3",
            to_agent="agent-2",
            target="artifact-2",
            observed="crash",
            expected="stable",
        )
        fb3 = Feedback(
            feedback_id="fb-003",
            feedback_type="praise",
            from_agent="agent-1",
            to_agent="agent-3",
            target="artifact-3",
            observed="good",
            expected="good",
        )
        channel.submit(fb1)
        channel.submit(fb2)
        channel.submit(fb3)

        pending = channel.get_pending_for_agent("agent-2")
        assert len(pending) == 2
        assert {f.feedback_id for f in pending} == {"fb-001", "fb-002"}

    def test_get_pending_for_agent_no_match(self):
        channel = FeedbackChannel()
        assert channel.get_pending_for_agent("nonexistent-agent") == []

    def test_route_to_owner_existing(self):
        channel = FeedbackChannel()
        feedback = Feedback(
            feedback_id="fb-001",
            feedback_type="suggestion",
            from_agent="agent-1",
            to_agent="agent-2",
            target="artifact-1",
            observed="slow",
            expected="fast",
        )
        channel.submit(feedback)
        assert channel.route_to_owner(feedback) is True

    def test_route_to_owner_nonexistent(self):
        channel = FeedbackChannel()
        feedback = Feedback(
            feedback_id="fb-999",
            feedback_type="suggestion",
            from_agent="agent-1",
            to_agent="agent-2",
            target="artifact-1",
            observed="slow",
            expected="fast",
        )
        assert channel.route_to_owner(feedback) is False

    def test_get_all_pending(self):
        channel = FeedbackChannel()
        fb1 = Feedback(
            feedback_id="fb-001",
            feedback_type="suggestion",
            from_agent="agent-1",
            to_agent="agent-2",
            target="artifact-1",
            observed="slow",
            expected="fast",
        )
        fb2 = Feedback(
            feedback_id="fb-002",
            feedback_type="bug",
            from_agent="agent-3",
            to_agent="agent-2",
            target="artifact-2",
            observed="crash",
            expected="stable",
        )
        channel.submit(fb1)
        channel.submit(fb2)

        all_pending = channel.get_all_pending()
        assert len(all_pending) == 2

    def test_get_all_pending_empty(self):
        channel = FeedbackChannel()
        assert channel.get_all_pending() == []

    def test_resolve_removes_feedback(self):
        channel = FeedbackChannel()
        feedback = Feedback(
            feedback_id="fb-001",
            feedback_type="suggestion",
            from_agent="agent-1",
            to_agent="agent-2",
            target="artifact-1",
            observed="slow",
            expected="fast",
        )
        channel.submit(feedback)
        assert channel.resolve("fb-001") is True
        assert "fb-001" not in channel._feedbacks
        assert "agent-2" not in channel._pending_by_agent

    def test_resolve_unknown_feedback(self):
        channel = FeedbackChannel()
        assert channel.resolve("nonexistent") is False

    def test_resolve_keeps_other_feedbacks_for_same_agent(self):
        channel = FeedbackChannel()
        fb1 = Feedback(
            feedback_id="fb-001",
            feedback_type="suggestion",
            from_agent="agent-1",
            to_agent="agent-2",
            target="artifact-1",
            observed="slow",
            expected="fast",
        )
        fb2 = Feedback(
            feedback_id="fb-002",
            feedback_type="bug",
            from_agent="agent-3",
            to_agent="agent-2",
            target="artifact-2",
            observed="crash",
            expected="stable",
        )
        channel.submit(fb1)
        channel.submit(fb2)
        assert channel.resolve("fb-001") is True
        assert "fb-002" in channel._feedbacks
        assert channel._pending_by_agent["agent-2"] == ["fb-002"]
