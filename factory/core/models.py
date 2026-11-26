from dataclasses import dataclass, field
from enum import Enum

ORCHESTRATION_QUEUE = "factory-orchestration"
AGENTS_QUEUE = "factory-agents"
GIT_QUEUE = "factory-git"


class Stage(str, Enum):
    """Job stage. A str enum with the exact historical values, so it serializes as a plain string."""
    STARTING = "starting"
    INTAKE = "intake"
    NEEDS_INFO = "needs-info"
    SPEC = "spec"
    BUILD = "build"
    GATE = "gate"
    REVIEW = "review"
    APPROVE = "approve"
    MERGING = "merging"
    NEEDS_HUMAN = "needs-human"
    MERGED = "merged"
    REJECTED = "rejected"
    FAILED = "failed"  # only sent via notify, never stored in a flow's stage
    RESUMING = "resuming"  # set by FactoryQueueWorkflow only
    CHECKS = "checks"  # CI dry run: running the gate on the base branch
    PASSED = "passed"  # CI dry run: terminal
    CHECKS_FAILED = "checks-failed"  # CI dry run: terminal


class LabelKind(str, Enum):
    """A key of config `labels`."""
    QUEUE = "queue"
    NEEDS_INFO = "needs_info"
    NEEDS_HUMAN = "needs_human"


class FlowName(str, Enum):
    """A key of config `flows` and of flows/registry.py `FLOWS`."""
    IMPLEMENT = "implement"
    CI_DRY_RUN = "ci-dry-run"


@dataclass
class Job:
    id: str
    issue: int  # 0 when the flow has no issue (CI dry run)
    title: str
    dir: str
    repo: str
    worktree: str
    branch: str
    base: str
    max_rounds: int = 3


@dataclass
class DryRunInput:
    base: str | None = None  # default: config base_branch
    key: str = ""  # job folder suffix; the workflow sets it from its start time when empty


@dataclass
class AgentRequest:
    job: Job
    role: str  # intake | spec-writer | builder | reviewer-<lens>
    message: str
    round: int = 1
    session_id: str | None = None
    model: str | None = None  # model alias override (reviewers: from routing)


@dataclass
class ReviewResult:
    lens: str
    verdict: str  # PASS | CHANGES
    cost_usd: float = 0.0


@dataclass
class AgentResult:
    session_id: str | None = None
    cost_usd: float = 0.0
    reply: str = ""


@dataclass
class IntakeResult:
    decision: str  # ACCEPT | NEEDS-INFO | REJECT
    risk: str
    surfaces: list[str]
    rescoped: bool
    body: str
    agent: AgentResult = field(default_factory=AgentResult)


@dataclass
class BuildResult:
    status: str  # READY | BLOCKED
    blocked: str
    agent: AgentResult = field(default_factory=AgentResult)


@dataclass
class DecisionResult:
    decision: str  # APPROVE | ESCALATE
    body: str  # everything below the first line of decision.md
    agent: AgentResult = field(default_factory=AgentResult)


@dataclass
class GateRequest:
    job: Job
    round: int
    merge: bool = False  # after syncing with base: writes merge-checks.md


@dataclass
class MergeRequest:
    job: Job
    pr: int
    round: int


@dataclass
class MergeResult:
    merged: bool
    detail: str = ""


@dataclass
class EscalateArgs:
    job: Job
    why: str
    pr: int | None = None
    write_decision: bool = True  # False when the approver already wrote decision.md


@dataclass
class TextArgs:
    job: Job
    text: str
    pr: int | None = None


@dataclass
class GateResult:
    verdict: str  # PASS | FAIL
    commit: str
    exit_code: int
    protected: list[str]


@dataclass
class PrInfo:
    number: int
    url: str


@dataclass
class QueueIssue:
    number: int
    needs_info: bool  # labeled factory:needs-info
    replied: bool  # the author or operator commented after the factory's last comment
    flow: FlowName = FlowName.IMPLEMENT  # picked from the issue's labels (config `flows`)


@dataclass
class QueueSnapshot:
    issues: list[QueueIssue]
    concurrency: int


@dataclass
class JobState:
    """Sent by a flow to the queue whenever it starts waiting, resumes or ends."""
    issue: int
    stage: Stage
    cost_usd: float = 0.0
    workflow_id: str = ""  # empty in states sent before flows existed: means factory-job-<issue>


@dataclass
class QueueInput:
    poll_seconds: float = 60.0
    jobs: dict[str, JobState] = field(default_factory=dict)  # by workflow id; carried across continue-as-new


@dataclass
class Comment:
    number: int
    body: str


@dataclass
class LabelChange:
    number: int
    add: list[LabelKind] = field(default_factory=list)
    remove: list[LabelKind] = field(default_factory=list)
    remove_flow_label: FlowName | None = None  # also remove this flow's trigger label (flows.<name>.label)
