from dataclasses import dataclass, field

ORCHESTRATION_QUEUE = "factory-orchestration"
AGENTS_QUEUE = "factory-agents"
GIT_QUEUE = "factory-git"


@dataclass
class Job:
    id: str
    issue: int
    title: str
    dir: str
    repo: str
    worktree: str
    branch: str
    base: str
    max_rounds: int = 3


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


@dataclass
class QueueSnapshot:
    issues: list[QueueIssue]
    concurrency: int


@dataclass
class JobState:
    """Sent by a JobWorkflow to the queue whenever it starts waiting, resumes or ends."""
    issue: int
    stage: str
    cost_usd: float = 0.0


@dataclass
class QueueInput:
    poll_seconds: float = 60.0
    jobs: dict[str, JobState] = field(default_factory=dict)  # carried across continue-as-new


@dataclass
class Comment:
    number: int
    body: str


@dataclass
class LabelChange:
    number: int
    add: list[str] = field(default_factory=list)  # label kinds: queue | needs_info | needs_human
    remove: list[str] = field(default_factory=list)
