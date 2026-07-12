from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .task_review.release_e2e import RELEASE_E2E_SCENARIO_ID


class SubTaskInfo(BaseModel):
    subtask_id: str
    description: str
    agent_id: str
    priority: int
    status: str
    progress: float
    dependencies: List[str]
    output_file: Optional[str] = None
    duration: Optional[float] = None
    error_message: Optional[str] = None
    fix_plan: Optional[str] = None
    wave_number: int = 1
    owner_decision: Optional[Dict[str, Any]] = None
    waiting_on_dependencies: List[str] = Field(default_factory=list)
    blocked_reason: Optional[str] = None
    running_for_seconds: Optional[float] = None
    contract: Optional[Dict[str, Any]] = None


class WaveInfo(BaseModel):
    wave_id: str
    wave_number: int
    subtasks: List[SubTaskInfo]
    status: str
    is_blocked: bool = False
    governance_status: Optional[str] = None
    blocked_by_wave: Optional[int] = None
    is_revalidating: bool = False
    owner_decision: Optional[Dict[str, Any]] = None


class TaskInfo(BaseModel):
    task_id: str
    description: str
    status: str
    external_task: bool = False
    task_types: List[str] = Field(default_factory=list)
    delivery_mode: str = "external"
    owner_delivery_contract: Optional[Dict[str, Any]] = None
    owner_agent: Optional[str] = None
    allowed_subtask_agents: List[str] = Field(default_factory=list)
    project_dir: Optional[str] = None
    subtasks: List[SubTaskInfo]
    waves: List[WaveInfo] = Field(default_factory=list)
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    artifact_versions: Dict[str, int] = Field(default_factory=dict)
    acceptance_records: List[Dict[str, Any]] = Field(default_factory=list)
    owner_session_id: Optional[str] = None
    last_owner_decision: Optional[Dict[str, Any]] = None
    can_handle_directly: bool = False
    direct_response: Optional[str] = None
    progress: float
    completed_count: int = 0
    total_count: int = 0
    created_at: float
    updated_at: float
    error: Optional[str] = None
    requirement_manifest: Optional[Dict[str, Any]] = None
    quality_health: Dict[str, Any] = Field(default_factory=dict)
    delivery_report: Dict[str, Any] = Field(default_factory=dict)
    observability: Dict[str, Any] = Field(default_factory=dict)
    review_status: str = "pending"
    accepted_at: Optional[float] = None


class TaskSummaryInfo(BaseModel):
    task_id: str
    description: str
    status: str
    external_task: bool = False
    progress: float = 0
    completed_count: int = 0
    total_count: int = 0
    created_at: float = 0
    updated_at: float = 0
    project_dir: Optional[str] = None
    owner_agent: Optional[str] = None
    delivery_mode: str = "external"
    review_status: str = "pending"
    accepted_at: Optional[float] = None


class TaskPageResponse(BaseModel):
    tasks: List[TaskSummaryInfo]
    total: int
    limit: int
    offset: int
    has_more: bool


class TaskDispatchRequest(BaseModel):
    subtask_ids: Optional[List[str]] = None


class JobInfo(BaseModel):
    job_id: str
    subtask_id: str
    agent_id: str
    task_description: str
    status: str
    progress: float
    logs: List[str]
    result: Optional[str]
    error: Optional[str]


class TaskDispatchResponse(BaseModel):
    task_id: str
    dispatched_jobs: List[JobInfo]
    ready_remaining: int


class AutoTaskRequest(BaseModel):
    description: str
    task_types: List[str] = Field(default_factory=list)
    owner_agent: Optional[str] = None
    allowed_subtask_agents: List[str] = Field(default_factory=list)
    project_dir: Optional[str] = None
    strict_dependency: bool = True
    enable_wave_gate: bool = True


class AutoTaskResponse(BaseModel):
    task_id: str
    status: str
    message: str
    implementation: str = "external"
    external_task: bool = False


class ReleaseE2EScenarioListResponse(BaseModel):
    scenarios: List[Dict[str, Any]]


class ReleaseE2ETaskRequest(BaseModel):
    scenario_id: str = RELEASE_E2E_SCENARIO_ID
    project_dir: Optional[str] = None
    run_label: Optional[str] = None


class ReleaseE2ETaskResponse(BaseModel):
    task_id: str
    status: str
    message: str
    scenario_id: str
    project_dir: str
    complexity_score: int
    required_files: List[str]
    implementation: str = "external"
    external_task: bool = False
    orchestrator_transport: Optional[str] = None


def pydantic_dump(model: BaseModel, **kwargs: Any) -> Dict[str, Any]:
    return model.model_dump(**kwargs) if hasattr(model, "model_dump") else model.dict(**kwargs)
