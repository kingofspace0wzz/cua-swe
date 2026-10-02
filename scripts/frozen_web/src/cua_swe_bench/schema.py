from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


Track = Literal["web_frontend", "mobilegym"]
BenchmarkDomain = Literal[
    "web",
    "mobile",
    "full-stack-product-workflows",
    "devops-observability",
    "game-interactive-app-qa",
    "accessibility-visual-regression",
    "data-apps-extensions-electron",
]
TaskType = Literal[
    "functional_ui",
    "visual_layout",
    "interaction_state",
    "async_loading_error",
    "gameplay_regression",
    "mobile_app_behavior",
]
Difficulty = Literal["l1", "l2", "l3", "l4"]
RepoSource = Literal["local", "git", "archive", "mobilegym_overlay"]
RepoCopyMode = Literal["filtered", "exact"]
AdapterName = Literal["playwright_web", "mobilegym"]
MobileGymRuntimeKind = Literal["bench_env.run", "env_api"]
ObservationMode = Literal["structured", "visual"]
GameRuntimeProvider = Literal["gameworld"]


class RepoSnapshot(BaseModel):
    source: RepoSource
    ref: str
    path: str | None = None
    url: str | None = None
    overlay_patch: str | None = None
    link_node_modules: bool = True
    copy_mode: RepoCopyMode = "filtered"

    @model_validator(mode="after")
    def validate_source_fields(self) -> "RepoSnapshot":
        if self.source in {"local", "mobilegym_overlay"} and not self.path:
            raise ValueError(f"{self.source} repo snapshots require path")
        if self.source in {"git", "archive"} and not self.url:
            raise ValueError("git and archive repo snapshots require url")
        return self


class SetupCommands(BaseModel):
    install: list[str] = Field(default_factory=list)
    launch: list[str] = Field(default_factory=list)
    reset: list[str] = Field(default_factory=list)


class EnvironmentSpec(BaseModel):
    adapter: AdapterName
    start_url: str | None = None
    viewport_or_device: str
    observation_mode: ObservationMode = "structured"


class AllowedTools(BaseModel):
    code_edit: bool
    terminal: bool
    browser_gui: bool
    mobile_gui: bool


class Budgets(BaseModel):
    wall_time_sec: int = Field(gt=0)
    max_steps: int = Field(gt=0)
    max_gui_actions: int = Field(ge=0)
    max_test_runs: int = Field(ge=0)


class VerifierSpec(BaseModel):
    build: list[str] = Field(default_factory=list)
    unit: list[str] = Field(default_factory=list)
    ui: list[str] = Field(default_factory=list)
    visual: list[str] = Field(default_factory=list)
    state: list[str] = Field(default_factory=list)
    side_effects: list[str] = Field(default_factory=list)

    def ordered_commands(self) -> list[tuple[str, str]]:
        commands: list[tuple[str, str]] = []
        for group in ["build", "unit", "ui", "visual", "state", "side_effects"]:
            for command in getattr(self, group):
                commands.append((group, command))
        return commands


class ArtifactSpec(BaseModel):
    collect_patch: bool = True
    collect_logs: bool = True
    collect_screenshots: bool = True
    collect_trajectory: bool = True
    collect_state_diff: bool = True


class MobileGymRuntimeSpec(BaseModel):
    upstream_task_id: str
    mobilegym_root: str = "../baselines/repos/mobilegym"
    runtime: MobileGymRuntimeKind = "bench_env.run"
    verifier: MobileGymRuntimeKind = "bench_env.run"


class GameRuntimeSpec(BaseModel):
    provider: GameRuntimeProvider = "gameworld"
    game_id: str = Field(min_length=1)
    state_api: Literal["window.gameAPI"] = "window.gameAPI"
    seed: int = Field(default=42, ge=0)
    level: int | None = Field(default=None, ge=1)


class TaskBundle(BaseModel):
    id: str
    track: Track
    benchmark_domain: BenchmarkDomain | None = None
    type: TaskType
    difficulty: Difficulty
    repo_snapshot: RepoSnapshot
    instruction: str = Field(min_length=1)
    setup: SetupCommands
    environment: EnvironmentSpec
    allowed_tools: AllowedTools
    budgets: Budgets
    verifiers: VerifierSpec
    artifacts: ArtifactSpec
    mobilegym_runtime: MobileGymRuntimeSpec | None = None
    game_runtime: GameRuntimeSpec | None = None

    @model_validator(mode="after")
    def validate_track_contract(self) -> "TaskBundle":
        if self.track == "web_frontend":
            if self.environment.adapter != "playwright_web":
                raise ValueError("web_frontend tasks must use the playwright_web adapter")
            if not self.allowed_tools.browser_gui:
                raise ValueError("web_frontend tasks require browser_gui")
        if self.track == "mobilegym":
            if self.environment.adapter != "mobilegym":
                raise ValueError("mobilegym tasks must use the mobilegym adapter")
            if not self.allowed_tools.mobile_gui:
                raise ValueError("mobilegym tasks require mobile_gui")
        if self.game_runtime is not None and self.type != "gameplay_regression":
            raise ValueError(
                "game_runtime may only be declared for gameplay_regression tasks"
            )
        if self.type == "gameplay_regression":
            if self.benchmark_domain != "game-interactive-app-qa":
                raise ValueError(
                    "gameplay_regression tasks must use the game-interactive-app-qa domain"
                )
            if self.track != "web_frontend":
                raise ValueError("gameplay_regression tasks must use the web_frontend track")
            if self.environment.observation_mode != "visual":
                raise ValueError(
                    "gameplay_regression tasks require visual observation mode"
                )
            if self.game_runtime is None:
                raise ValueError("gameplay_regression tasks must declare game_runtime")
            if not self.verifiers.state:
                raise ValueError(
                    "gameplay_regression tasks require a hidden state verifier"
                )
            if not self.artifacts.collect_screenshots or not self.artifacts.collect_trajectory:
                raise ValueError(
                    "gameplay_regression tasks must collect screenshots and trajectory"
                )
        domain_prefixes = {
            "full-stack-product-workflows": "fullstack.",
            "devops-observability": "devops.",
            "game-interactive-app-qa": "gameqa.",
            "accessibility-visual-regression": "a11y.",
            "data-apps-extensions-electron": "dataapp.",
        }
        expected_prefix = domain_prefixes.get(self.benchmark_domain)
        if expected_prefix and not self.id.startswith(expected_prefix):
            raise ValueError(
                f"{self.benchmark_domain} task ids must start with {expected_prefix}"
            )
        return self
