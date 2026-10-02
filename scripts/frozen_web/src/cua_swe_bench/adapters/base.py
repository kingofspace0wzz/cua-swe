from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


MAX_SCROLL_DELTA = 4_000
MAX_DRAG_STEPS = 100
MAX_ACTION_DURATION_MS = 2_000
ClickModifier = Literal["Shift", "Control", "Alt", "Meta"]
CLICK_MODIFIERS: tuple[ClickModifier, ...] = ("Shift", "Control", "Alt", "Meta")
GuiActionKind = Literal[
    "click",
    "type",
    "press",
    "key_hold",
    "scroll",
    "drag",
    "drag_start",
    "drag_move",
    "drag_end",
    "back",
    "forward",
    "resize",
    "wait",
]


class GuiAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: GuiActionKind
    x: int | None = None
    y: int | None = None
    end_x: int | None = None
    end_y: int | None = None
    delta_x: int | None = None
    delta_y: int | None = None
    steps: int | None = None
    text: str | None = None
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None
    modifiers: Annotated[list[ClickModifier], Field(strict=True, max_length=4)] | None = None

    @model_validator(mode="after")
    def validate_action_shape(self) -> GuiAction:
        allowed_fields = {
            "click": {"x", "y", "modifiers"},
            "type": {"text"},
            "press": {"text"},
            "key_hold": {"text", "duration_ms"},
            "scroll": {"x", "y", "delta_x", "delta_y"},
            "drag": {"x", "y", "end_x", "end_y", "steps"},
            "drag_start": {"x", "y"},
            "drag_move": {"x", "y", "steps"},
            "drag_end": {"x", "y", "steps"},
            "back": set(),
            "forward": set(),
            "resize": {"width", "height"},
            "wait": {"duration_ms"},
        }
        required_fields = {
            "click": {"x", "y"},
            "type": {"text"},
            "press": {"text"},
            "key_hold": {"text", "duration_ms"},
            "scroll": {"x", "y"},
            "drag": {"x", "y", "end_x", "end_y"},
            "drag_start": {"x", "y"},
            "drag_move": {"x", "y"},
            "drag_end": set(),
            "back": set(),
            "forward": set(),
            "resize": {"width", "height"},
            "wait": set(),
        }

        supplied = self.model_fields_set - {"kind"}
        unexpected = supplied - allowed_fields[self.kind]
        if unexpected:
            names = ", ".join(sorted(unexpected))
            raise ValueError(f"{self.kind} action does not accept fields: {names}")

        missing = {name for name in required_fields[self.kind] if getattr(self, name) is None}
        if missing:
            names = " and ".join(sorted(missing))
            raise ValueError(f"{self.kind} action requires {names}")

        if self.modifiers is not None and len(set(self.modifiers)) != len(self.modifiers):
            raise ValueError("click modifiers must not repeat a key")

        if self.kind == "scroll":
            delta_x = self.delta_x or 0
            delta_y = self.delta_y or 0
            if delta_x == 0 and delta_y == 0:
                raise ValueError("scroll action requires a non-zero delta_x or delta_y")
            if abs(delta_x) > MAX_SCROLL_DELTA or abs(delta_y) > MAX_SCROLL_DELTA:
                raise ValueError(
                    f"scroll deltas must be between {-MAX_SCROLL_DELTA} and {MAX_SCROLL_DELTA}"
                )

        if self.kind in {"drag", "drag_move", "drag_end"} and self.steps is not None:
            if self.steps < 1 or self.steps > MAX_DRAG_STEPS:
                raise ValueError(f"drag steps must be between 1 and {MAX_DRAG_STEPS}")

        if self.kind == "drag_end":
            if (self.x is None) != (self.y is None):
                raise ValueError("drag_end action requires both x and y when either is supplied")
            if self.steps is not None and self.x is None:
                raise ValueError("drag_end action requires x and y when steps is supplied")

        if self.duration_ms is not None:
            if self.duration_ms < 1 or self.duration_ms > MAX_ACTION_DURATION_MS:
                raise ValueError(
                    f"duration_ms must be between 1 and {MAX_ACTION_DURATION_MS}"
                )

        if self.kind == "key_hold":
            assert self.text is not None
            keys = [key.strip() for key in self.text.split("+") if key.strip()]
            if not keys or len(keys) > 2:
                raise ValueError("key_hold text must contain one or two '+'-separated keys")
            if len(set(keys)) != len(keys):
                raise ValueError("key_hold text must not repeat a key")

        if self.kind == "resize":
            assert self.width is not None and self.height is not None
            if self.width <= 0 or self.height <= 0:
                raise ValueError("resize width and height must be positive integers")
            if self.width > 3_840 or self.height > 2_160:
                raise ValueError("resize viewport must not exceed 3840x2160")

        return self


class GuiObservation(BaseModel):
    url: str | None = None
    screenshot_path: str | None = None
    text: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)


class EnvironmentAdapter(Protocol):
    def start(self, workspace: Path) -> None:
        raise NotImplementedError

    def observe(self) -> GuiObservation:
        raise NotImplementedError

    def act(self, action: GuiAction) -> GuiObservation:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError
