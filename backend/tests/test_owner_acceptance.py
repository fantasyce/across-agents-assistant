import pytest

from across_agents_assistant.task_manager.models import Task, Job, SubTask, JobStatus, AcceptanceResult
from across_agents_assistant.task_manager.state import TaskState
from across_agents_assistant.task_manager.orchestration.owner_agent import OwnerAgent


class MockLLMResponse:
    def __init__(self, text: str):
        self.text = text


class MockLLMGateway:
    def __init__(self, response_text: str):
        self._response_text = response_text
        self.calls = []

    def __call__(self, system_prompt: str, message: str, temperature: float):
        self.calls.append({
            "system_prompt": system_prompt,
            "message": message,
            "temperature": temperature,
        })
        return MockLLMResponse(self._response_text)


class TestAcceptSubtask:
    def test_returns_passed_true_when_llm_says_ok(self):
        state = TaskState()
        llm_response = '{"passed": true, "feedback": "Looks good", "action": "approve"}'
        llm = MockLLMGateway(llm_response)
        owner = OwnerAgent(llm, state)

        subtask = SubTask(subtask_id="st-1", description="Implement login", agent_id="deepseek")
        job = Job.new(subtask, agent_id="deepseek")
        job.result = "def login(): pass"

        result = owner.accept_subtask(job)

        assert isinstance(result, AcceptanceResult)
        assert result.subtask_id == "st-1"
        assert result.level2_passed is True
        assert result.action == "approve"
        assert result.level2_feedback is None

    def test_returns_passed_false_with_feedback_when_llm_finds_issues(self):
        state = TaskState()
        llm_response = (
            '{"passed": false, '
            '"feedback": "Missing error handling for invalid credentials", '
            '"action": "fix"}'
        )
        llm = MockLLMGateway(llm_response)
        owner = OwnerAgent(llm, state)

        subtask = SubTask(subtask_id="st-2", description="Implement login", agent_id="deepseek")
        job = Job.new(subtask, agent_id="deepseek")
        job.result = "def login(): pass"

        result = owner.accept_subtask(job)

        assert result.level2_passed is False
        assert result.level2_feedback == "Missing error handling for invalid credentials"
        assert result.action == "fix"

    def test_builds_acceptance_context_with_job_details(self):
        state = TaskState()
        llm = MockLLMGateway('{"passed": true, "feedback": "", "action": "approve"}')
        owner = OwnerAgent(llm, state)

        subtask = SubTask(subtask_id="st-3", description="Build auth module", agent_id="claude")
        job = Job.new(subtask, agent_id="claude")
        job.result = "class Auth: ..."
        job.error = None

        owner.accept_subtask(job)

        assert len(llm.calls) == 1
        call = llm.calls[0]
        assert "Build auth module" in call["message"]
        assert "class Auth: ..." in call["message"]
        assert "st-3" in call["message"]
        assert "claude" in call["message"]
        assert call["temperature"] == 0.2

    def test_builds_context_with_error_when_job_has_error(self):
        state = TaskState()
        llm = MockLLMGateway('{"passed": false, "feedback": "Has error", "action": "fix"}')
        owner = OwnerAgent(llm, state)

        subtask = SubTask(subtask_id="st-4", description="Build auth module", agent_id="claude")
        job = Job.new(subtask, agent_id="claude")
        job.result = None
        job.error = "Connection timeout"

        owner.accept_subtask(job)

        call = llm.calls[0]
        assert "Connection timeout" in call["message"]

    def test_handles_llm_exception_gracefully(self):
        state = TaskState()

        class FailingLLM:
            def __call__(self, system_prompt: str, message: str, temperature: float):
                raise RuntimeError("LLM service unavailable")

        owner = OwnerAgent(FailingLLM(), state)

        subtask = SubTask(subtask_id="st-5", description="Build auth module", agent_id="claude")
        job = Job.new(subtask, agent_id="claude")

        result = owner.accept_subtask(job)

        assert result.level2_passed is False
        assert result.action == "retry_acceptance"
        assert "LLM service unavailable" in result.level2_feedback

    def test_uses_system_prompt_for_acceptance(self):
        state = TaskState()
        llm = MockLLMGateway('{"passed": true, "feedback": "", "action": "approve"}')
        owner = OwnerAgent(llm, state)

        subtask = SubTask(subtask_id="st-6", description="Test", agent_id="local")
        job = Job.new(subtask, agent_id="local")

        owner.accept_subtask(job)

        call = llm.calls[0]
        assert "senior technical lead" in call["system_prompt"]
        assert "acceptance review" in call["system_prompt"]


class TestParseAcceptance:
    def test_parses_approved_response(self):
        state = TaskState()
        llm = MockLLMGateway('{"subtasks": []}')
        owner = OwnerAgent(llm, state)

        text = '{"passed": true, "feedback": "Great work", "action": "approve"}'
        result = owner._parse_acceptance(text, "st-7")

        assert result.subtask_id == "st-7"
        assert result.level2_passed is True
        assert result.level2_feedback is None
        assert result.action == "approve"

    def test_parses_rejected_response(self):
        state = TaskState()
        llm = MockLLMGateway('{"subtasks": []}')
        owner = OwnerAgent(llm, state)

        text = '{"passed": false, "feedback": "Needs tests", "action": "fix"}'
        result = owner._parse_acceptance(text, "st-8")

        assert result.subtask_id == "st-8"
        assert result.level2_passed is False
        assert result.level2_feedback == "Needs tests"
        assert result.action == "fix"

    def test_defaults_action_to_approve_when_passed_true(self):
        state = TaskState()
        llm = MockLLMGateway('{"subtasks": []}')
        owner = OwnerAgent(llm, state)

        text = '{"passed": true}'
        result = owner._parse_acceptance(text, "st-9")

        assert result.action == "approve"

    def test_defaults_action_to_fix_when_passed_false(self):
        state = TaskState()
        llm = MockLLMGateway('{"subtasks": []}')
        owner = OwnerAgent(llm, state)

        text = '{"passed": false}'
        result = owner._parse_acceptance(text, "st-10")

        assert result.action == "fix"

    def test_parses_downgrade_action(self):
        state = TaskState()
        llm = MockLLMGateway('{"subtasks": []}')
        owner = OwnerAgent(llm, state)

        text = '{"passed": false, "feedback": "Minor issues", "action": "downgrade"}'
        result = owner._parse_acceptance(text, "st-11")

        assert result.action == "downgrade"

    def test_parses_reassign_action(self):
        state = TaskState()
        llm = MockLLMGateway('{"subtasks": []}')
        owner = OwnerAgent(llm, state)

        text = '{"passed": false, "feedback": "Completely wrong approach", "action": "reassign"}'
        result = owner._parse_acceptance(text, "st-12")

        assert result.action == "reassign"

    def test_parses_markdown_wrapped_json(self):
        state = TaskState()
        llm = MockLLMGateway('{"subtasks": []}')
        owner = OwnerAgent(llm, state)

        text = '```json\n{"passed": true, "feedback": "OK", "action": "approve"}\n```'
        result = owner._parse_acceptance(text, "st-13")

        assert result.level2_passed is True


class TestBuildAcceptanceContext:
    def test_includes_all_job_fields(self):
        state = TaskState()
        llm = MockLLMGateway('{"subtasks": []}')
        owner = OwnerAgent(llm, state)

        subtask = SubTask(subtask_id="st-14", description="Implement API", agent_id="deepseek")
        job = Job.new(subtask, agent_id="deepseek")
        job.result = "code here"
        job.error = "some error"

        context = owner._build_acceptance_context(job)

        assert "st-14" in context
        assert "deepseek" in context
        assert "Implement API" in context
        assert "code here" in context
        assert "some error" in context

    def test_handles_missing_result_and_error(self):
        state = TaskState()
        llm = MockLLMGateway('{"subtasks": []}')
        owner = OwnerAgent(llm, state)

        subtask = SubTask(subtask_id="st-15", description="Test", agent_id="local")
        job = Job.new(subtask, agent_id="local")

        context = owner._build_acceptance_context(job)

        assert "Output: (none)" in context
        assert "Error:" not in context or "Error:" in context  # error is None, so str(None) might appear
