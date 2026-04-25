import json
import logging
import re
from typing import Dict, Any, Optional

from ..llm_gateway.gateway import LLMGateway
from .models import Task, TaskType, SubTask

logger = logging.getLogger("across_agents_assistant.task_manager")

SYSTEM_PROMPT = """You are a task planning assistant for a macOS assistant app called "Across Agents Assistant".

Your role is to break down user requests into clear, actionable sub-tasks assigned to specialized agents.

**Available Agents:**
- openclaw: General purpose development and automation tasks
- hermes: Specific scenario development and conversational tasks
- claude: Code/technical deep expertise and code reviews

**Task Types:**
- research: Information gathering, web search, knowledge lookup
- code_review: Code analysis, quality assessment, refactoring suggestions
- automation: repetitive tasks, scripting, workflow automation
- simple_qa: Questions the app can answer directly without agent dispatch
- unknown: Cannot determine type

**Output Format:**
You MUST output a JSON object with this exact structure:
{
    "task_type": "research|code_review|automation|simple_qa|unknown",
    "can_handle_directly": true|false,
    "direct_response": "..." (only if can_handle_directly is true),
    "subtasks": [
        {"description": "...", "agent": "openclaw|hermes|claude", "priority": 1, "dependencies": []}
    ]
}

**Rules:**
1. If the task is a simple question or can be answered from context, set can_handle_directly=true
2. Complex tasks should be broken into subtasks assigned to appropriate agents
3. Dependencies indicate which subtask must complete before this one starts (use subtask descriptions to match)
4. Priority 1 = highest, run first
5. Keep descriptions concise but actionable
"""

class TaskDecomposer:
    """Uses LLM to decompose user requests into subtasks."""

    VALID_AGENTS = ["openclaw", "hermes", "claude"]
    TASK_TYPES = ["research", "code_review", "automation", "simple_qa", "unknown"]

    def __init__(self, gateway: LLMGateway):
        self._gateway = gateway
        self._default_agents = self.VALID_AGENTS

    async def decompose(self, task: Task, context: Optional[Dict[str, Any]] = None) -> Task:
        """
        Use LLM to decompose a task into subtasks.

        Args:
            task: The task to decompose
            context: Optional context dict (e.g., frontmost_app, window_title)

        Returns:
            The same task object with subtasks populated
        """
        user_message = task.description

        try:
            response = await self._gateway.chat(
                message=user_message,
                system_prompt=SYSTEM_PROMPT,
                context=context,
                temperature=0.3,
                max_tokens=2048
            )

            logger.info(f"LLM decomposition response: {response.text[:200]}...")

            decomposition = self._parse_llm_response(response.text)
            if decomposition:
                self._apply_decomposition(task, decomposition)
                logger.info(f"Task {task.task_id} decomposed into {len(task.subtasks)} subtasks")
            else:
                logger.warning(f"Failed to parse LLM response for task {task.task_id}")
                task.task_type = TaskType.UNKNOWN

        except Exception as e:
            logger.error(f"Task decomposition failed for {task.task_id}: {e}")
            task.task_type = TaskType.UNKNOWN

        return task

    def _parse_llm_response(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract and parse JSON from LLM response text."""
        text = text.strip()

        # Try direct JSON parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON in markdown code blocks
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try to find JSON object pattern
        obj_match = re.search(r"\{[\s\S]*\}", text)
        if obj_match:
            try:
                return json.loads(obj_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def _apply_decomposition(self, task: Task, decomposition: Dict[str, Any]) -> None:
        """Apply parsed decomposition to task."""
        # Parse task type
        task_type_str = decomposition.get("task_type", "unknown")
        if task_type_str in self.TASK_TYPES:
            task.task_type = TaskType(task_type_str)
        else:
            task.task_type = TaskType.UNKNOWN

        # Parse direct handling
        task.can_handle_directly = decomposition.get("can_handle_directly", False)
        task.direct_response = decomposition.get("direct_response")

        # Parse subtasks
        for st_data in decomposition.get("subtasks", []):
            description = st_data.get("description", "")
            if not description:
                continue

            agent = self._validate_agent(st_data.get("agent"))
            priority = int(st_data.get("priority", 1))
            dependencies = st_data.get("dependencies", [])

            subtask = SubTask(
                subtask_id=f"st-",  # Will be set properly in dispatch
                description=description,
                agent_id=agent,
                priority=priority,
                dependencies=dependencies
            )
            task.subtasks.append(subtask)

    def _validate_agent(self, agent: Optional[str]) -> str:
        """Validate and normalize agent ID."""
        if agent and agent in self.VALID_AGENTS:
            return agent
        logger.warning(f"Invalid agent '{agent}', defaulting to 'openclaw'")
        return "openclaw"