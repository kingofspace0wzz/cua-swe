from __future__ import annotations

from pathlib import Path

import yaml

from cua_swe_bench.schema import TaskBundle


class TaskRegistry:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def list_tasks(self) -> list[TaskBundle]:
        tasks: list[TaskBundle] = []
        for path in sorted(self.root.glob("**/task.yaml")):
            tasks.append(self._load_file(path))
        return tasks

    def get(self, task_id: str) -> TaskBundle:
        for task in self.list_tasks():
            if task.id == task_id:
                return task
        raise KeyError(f"task not found: {task_id}")

    def _load_file(self, path: Path) -> TaskBundle:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"task file must contain a mapping: {path}")
        return TaskBundle.model_validate(data)
