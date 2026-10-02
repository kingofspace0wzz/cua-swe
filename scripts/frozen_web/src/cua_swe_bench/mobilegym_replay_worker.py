from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import replace as dc_replace
from pathlib import Path
from typing import Any


def _json_default(value: Any) -> str:
    return str(value)


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _contains_any(text: str, candidates: list[str]) -> bool:
    return any(candidate and candidate in text for candidate in candidates)


async def _body_text(env: Any) -> str:
    text = await env.page.evaluate("() => document.body?.innerText || document.body?.textContent || ''")
    return _normalized_text(text)


async def _note_row_text(env: Any, title: str) -> str:
    text = await env.page.evaluate(
        """(title) => {
            const target = String(title || '').trim();
            const buttons = Array.from(document.querySelectorAll('button'));
            const match = buttons.find((button) => {
              const text = button.innerText || button.textContent || '';
              return target && text.includes(target);
            });
            if (!match) return '';
            return (match.innerText || match.textContent || '').replace(/\\s+/g, ' ').trim();
        }""",
        title,
    )
    return _normalized_text(text)


def _write_json(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")


def _physical_point(env: Any, box: dict[str, float]) -> list[int]:
    css_x = float(box["x"]) + float(box["width"]) / 2.0
    css_y = float(box["y"]) + float(box["height"]) / 2.0
    return _css_to_physical(env, css_x, css_y)


def _physical_point_at(env: Any, box: dict[str, float], *, css_dx: float, css_dy: float) -> list[int]:
    css_x = float(box["x"]) + css_dx
    css_y = float(box["y"]) + css_dy
    return _css_to_physical(env, css_x, css_y)


def _css_to_physical(env: Any, css_x: float, css_y: float) -> list[int]:
    return [
        int(round(css_x / float(env.css_width) * float(env.physical_width))),
        int(round(css_y / float(env.css_height) * float(env.physical_height))),
    ]


async def _point_for_locator(env: Any, locator: Any, *, timeout_ms: int = 8000) -> list[int]:
    await locator.wait_for(state="visible", timeout=timeout_ms)
    box = await locator.bounding_box()
    if box is None:
        raise RuntimeError("visible locator has no bounding box")
    return _physical_point(env, box)


async def _point_for_selector(env: Any, selector: str, *, timeout_ms: int = 8000) -> list[int]:
    return await _point_for_locator(env, env.page.locator(selector).first, timeout_ms=timeout_ms)


async def _point_for_selector_at(
    env: Any,
    selector: str,
    *,
    css_dx: float,
    css_dy: float,
    timeout_ms: int = 8000,
) -> list[int]:
    locator = env.page.locator(selector).first
    await locator.wait_for(state="visible", timeout=timeout_ms)
    box = await locator.bounding_box()
    if box is None:
        raise RuntimeError(f"visible selector has no bounding box: {selector}")
    return _physical_point_at(env, box, css_dx=css_dx, css_dy=css_dy)


async def _point_for_role(env: Any, role: str, name: str, *, timeout_ms: int = 8000) -> list[int]:
    return await _point_for_locator(env, env.page.get_by_role(role, name=name).first, timeout_ms=timeout_ms)


async def _point_for_text(env: Any, text: str, *, timeout_ms: int = 8000) -> list[int]:
    return await _point_for_locator(env, env.page.get_by_text(text, exact=True).first, timeout_ms=timeout_ms)


def _make_action(action_type: Any, data: dict[str, Any], summary: str = "") -> Any:
    from bench_env.env.base import Action

    return Action(action_type=action_type, data=data, summary=summary)


async def _record_and_step(
    *,
    env: Any,
    episode: Any,
    action: Any,
    trace: list[dict[str, Any]],
    step_idx: int,
) -> tuple[Any, bool, str | None]:
    obs = await env.get_observation()
    episode.record_step(
        step_idx=step_idx,
        obs=obs,
        action=action,
        route=obs.route,
        model_response="",
        model_prompt=None,
    )
    trace.append(
        {
            "step": step_idx,
            "action_type": action.action_type,
            "data": action.data,
            "thought": action.thought[:200] if action.thought else "",
        }
    )
    result = await env.step(action)
    return result.observation, result.done, result.stop_reason


async def _run_create_note_with_reminder(args: argparse.Namespace) -> dict[str, Any]:
    from bench_env.config import RunnerConfig
    from bench_env import factory
    from bench_env.env import RunRecorder
    from bench_env.env.base import ActionType
    from bench_env.runner.base import Controller, Evaluator, EpisodeResult, ExecutionResult
    from bench_env.task.judge import JudgeInput
    from bench_env.task.notes.app import Notes

    config = RunnerConfig(
        agent="cua_swe_replay",
        model_name="deterministic",
        env_url=args.env_url,
        headless=args.headless,
        coord_space="physical",
        delay_after_action=args.delay_after_action,
        quiet=args.quiet,
        task_id=args.task_id,
        runs_dir=Path(args.runs_dir),
        no_save_trajectory=False,
        screenshot_scale=args.screenshot_scale,
        eval_mode="grounded",
    )
    env = await factory.create_env(config)
    recorder = RunRecorder(
        Path(args.runs_dir),
        save_trajectory=True,
        coord_space="physical",
        screenshot_scale=args.screenshot_scale,
    )
    run_dir = recorder.start_run(
        agent="cua-swe-deterministic-replay",
        model_name="deterministic",
        extra_meta={
            **config.to_dict(),
            "replay_name": args.replay_name,
            "task_id": args.task_id,
        },
    )
    trace: list[dict[str, Any]] = []
    start_time = time.time()
    episode = None
    exec_error: str | None = None
    stop_reason: Any = None
    finished = False
    truncated = False

    try:
        tasks = factory.load_tasks(config)
        if len(tasks) != 1:
            raise RuntimeError(f"expected one task for {args.task_id}, got {len(tasks)}")
        task = tasks[0]
        env.set_current_task(task.id)
        initial_obs, _params = await Controller.setup(env, task, eval_mode="grounded")
        episode = recorder.start_episode(
            task_id=task.id,
            task_name=task.description,
            extra_meta={"agent": "cua-swe-deterministic-replay", "max_steps": args.max_steps},
        )

        step_idx = 1

        async def step(action: Any) -> None:
            nonlocal step_idx, stop_reason, finished
            _obs, done, reason = await _record_and_step(
                env=env,
                episode=episode,
                action=action,
                trace=trace,
                step_idx=step_idx,
            )
            step_idx += 1
            finished = bool(done)
            stop_reason = reason

        def click(point: list[int], summary: str) -> Any:
            return _make_action(ActionType.CLICK, {"point": point}, summary=summary)

        def wait(seconds: float, summary: str) -> Any:
            return _make_action(ActionType.WAIT, {"value": seconds}, summary=summary)

        def type_text(value: str, summary: str, point: list[int] | None = None) -> Any:
            data: dict[str, Any] = {"value": value}
            if point is not None:
                data["point"] = point
            return _make_action(ActionType.TYPE, data, summary=summary)

        title = str(task.params.get("title") or "明天开会")
        content = str(task.params.get("content") or "记得带文件")

        await step(click(await _point_for_role(env, "button", "新建笔记"), "open new note editor"))
        await step(wait(0.4, "wait for editor"))
        title_point = await _point_for_selector(env, "input[placeholder='标题']")
        await step(type_text(title, "type note title", point=title_point))
        await step(wait(1.0, "wait for initial autosave"))
        content_point = await _point_for_selector_at(env, "textarea", css_dx=30, css_dy=24)
        await step(type_text(content, "type note content", point=content_point))
        await step(wait(1.0, "wait for content autosave"))
        await step(click(await _point_for_role(env, "button", "完成"), "finish editing"))
        await step(wait(0.5, "wait for list"))
        await step(click(await _point_for_locator(env, env.page.get_by_text(title, exact=False).first), "reopen created note"))
        await step(wait(0.4, "wait for existing editor"))
        await step(click(await _point_for_role(env, "button", "更多"), "open more menu"))
        await step(click(await _point_for_text(env, "设置提醒"), "open reminder dialog"))
        await step(wait(0.3, "wait for reminder dialog"))
        await step(click(await _point_for_role(env, "button", "确定"), "confirm default reminder"))
        await step(wait(0.8, "wait for reminder save"))
        if args.replay_name == "notes-reminder-navigation-v0":
            await step(click(_css_to_physical(env, 34, 74), "return to list after reminder"))
            await step(wait(0.5, "wait for list after reminder"))
            await step(
                click(
                    await _point_for_locator(env, env.page.get_by_text(title, exact=False).first),
                    "reopen note after reminder navigation",
                )
            )
            await step(wait(0.4, "wait for reminder-backed editor"))

        current_state = await env.get_state(required_apps=["notes"])
        note = Notes((current_state.get("apps") or {}).get("notes") or {}).latest_note_by_title(title)
        alarm_at = (note or {}).get("alarmAt")
        labels = (
            Notes.reminder_time_labels(int(alarm_at))
            if isinstance(alarm_at, (int, float)) and alarm_at > 0
            else []
        )
        answer = labels[-1] if labels else ""
        if not answer:
            raise RuntimeError(f"could not derive reminder answer for note title={title!r}: {note!r}")

        await step(_make_action(ActionType.AWAKE, {"value": "answer_sheet"}, "open answer sheet"))
        await step(wait(0.4, "wait for answer sheet"))
        answer_point = await _point_for_selector(env, "input[type='text']")
        await step(type_text(answer, "type reminder answer", point=answer_point))
        await step(click(_css_to_physical(env, 180, 430), "dismiss answer keyboard"))
        await step(wait(0.3, "wait for submit footer"))
        await step(click(await _point_for_text(env, "提交答案"), "submit answer"))
        await step(wait(0.3, "wait for answer submission"))
        await step(_make_action(ActionType.COMPLETE, {"return": f"submitted reminder time {answer}"}, "complete"))

        final_obs = await env.get_observation()
        final_state = await env.get_state(required_apps=list(task.apps) if task.apps else None)
        final_obs = dc_replace(final_obs, state=final_state)
        stopwatch_total_s = float(getattr(env.stopwatch, "total", 0.0))
        try:
            stopwatch_flat = env.stopwatch.to_flat()
            stopwatch_tree = env.stopwatch.to_tree()
        except Exception:
            stopwatch_flat = {}
            stopwatch_tree = []
        exec_result = ExecutionResult(
            steps=len(trace),
            trace=trace,
            runtime_s=time.time() - start_time,
            finished=True,
            truncated=False,
            stop_reason=ActionType.COMPLETE,
            agent_message=env.agent_message,
            agent_answer=env.agent_answer,
            error=None,
            stopwatch_total_s=stopwatch_total_s,
            stopwatch_flat=stopwatch_flat,
            stopwatch_tree=stopwatch_tree,
        )
        judge = await Evaluator(judge_mode="state", eval_mode="grounded").evaluate(
            task,
            initial_obs,
            final_obs,
            exec_result,
            episode,
        )
        episode_result = EpisodeResult(
            task_id=task.id,
            task_name=task.description,
            suite=task.suite,
            execution=exec_result,
            judge=judge,
            trial_id=0,
            apps=list(task.apps),
            max_steps=args.max_steps,
            **EpisodeResult._task_taxonomy(task),
        )
        episode.finish(episode_result.to_dict())
        summary = {
            "ok": bool(episode_result.success),
            "task_id": task.id,
            "observed_outcome": "success" if episode_result.success else "failed",
            "run_dir": str(run_dir),
            "answer": answer,
            "params": dict(task.params),
            "judge": judge.to_dict() if judge else None,
            "steps": len(trace),
        }
    except Exception as exc:
        exec_error = f"{type(exc).__name__}: {exc}"
        if episode is not None:
            exec_result = ExecutionResult(
                steps=len(trace),
                trace=trace,
                runtime_s=time.time() - start_time,
                finished=finished,
                truncated=truncated,
                stop_reason=stop_reason or "ERROR",
                agent_message=env.agent_message,
                agent_answer=env.agent_answer,
                error=exec_error,
            )
            task_id = args.task_id
            task_name = args.task_id
            suite = task_id.split(".", 1)[0] if "." in task_id else ""
            episode_result = EpisodeResult(
                task_id=task_id,
                task_name=task_name,
                suite=suite,
                execution=exec_result,
                judge=None,
                trial_id=0,
                apps=[],
                max_steps=args.max_steps,
            )
            episode.finish(episode_result.to_dict())
        else:
            recorder.record_result(
                {
                    "id": args.task_id,
                    "task_name": args.task_id,
                    "suite": args.task_id.split(".", 1)[0] if "." in args.task_id else "",
                    "apps": [],
                    "trial_id": 0,
                    "max_steps": args.max_steps,
                    "execution": {"steps": len(trace), "error": exec_error, "stop_reason": "ERROR"},
                    "judge": None,
                    "is_success": False,
                    "is_error": True,
                    "progress": 0.0,
                }
            )
        summary = {
            "ok": False,
            "task_id": args.task_id,
            "observed_outcome": "error",
            "run_dir": str(run_dir),
            "message": exec_error,
            "steps": len(trace),
        }
    finally:
        final_run_dir = recorder.finish_run()
        await env.close()

    summary["run_dir"] = str(final_run_dir)
    summary["summary_path"] = str(final_run_dir / "summary.json")
    summary["results_path"] = str(final_run_dir / "results.jsonl")
    return summary


async def _run_notes_list_reminder_chip(args: argparse.Namespace) -> dict[str, Any]:
    from bench_env.config import RunnerConfig
    from bench_env import factory
    from bench_env.env import RunRecorder
    from bench_env.env.base import ActionType
    from bench_env.runner.base import Controller, EpisodeResult, ExecutionResult
    from bench_env.task.judge import JudgeResult
    from bench_env.task.notes.app import Notes

    config = RunnerConfig(
        agent="cua_swe_replay",
        model_name="deterministic",
        env_url=args.env_url,
        headless=args.headless,
        coord_space="physical",
        delay_after_action=args.delay_after_action,
        quiet=args.quiet,
        task_id=args.task_id,
        runs_dir=Path(args.runs_dir),
        no_save_trajectory=False,
        screenshot_scale=args.screenshot_scale,
        eval_mode="grounded",
    )
    env = await factory.create_env(config)
    recorder = RunRecorder(
        Path(args.runs_dir),
        save_trajectory=True,
        coord_space="physical",
        screenshot_scale=args.screenshot_scale,
    )
    run_dir = recorder.start_run(
        agent="cua-swe-deterministic-replay",
        model_name="deterministic",
        extra_meta={
            **config.to_dict(),
            "replay_name": args.replay_name,
            "task_id": args.task_id,
            "cua_swe_custom_judge": "notes-list-reminder-chip-v0",
        },
    )
    trace: list[dict[str, Any]] = []
    start_time = time.time()
    episode = None
    exec_error: str | None = None
    stop_reason: Any = None
    finished = False
    truncated = False

    try:
        tasks = factory.load_tasks(config)
        if len(tasks) != 1:
            raise RuntimeError(f"expected one task for {args.task_id}, got {len(tasks)}")
        task = tasks[0]
        env.set_current_task(task.id)
        initial_obs, _params = await Controller.setup(env, task, eval_mode="grounded")
        episode = recorder.start_episode(
            task_id=task.id,
            task_name=(
                "CUA-SWE Notes list reminder chip: set a reminder, inspect list row, "
                "reopen detail, and require visible list/detail consistency"
            ),
            extra_meta={"agent": "cua-swe-deterministic-replay", "max_steps": args.max_steps},
        )

        step_idx = 1

        async def step(action: Any) -> None:
            nonlocal step_idx, stop_reason, finished
            _obs, done, reason = await _record_and_step(
                env=env,
                episode=episode,
                action=action,
                trace=trace,
                step_idx=step_idx,
            )
            step_idx += 1
            finished = bool(done)
            stop_reason = reason

        def click(point: list[int], summary: str) -> Any:
            return _make_action(ActionType.CLICK, {"point": point}, summary=summary)

        def wait(seconds: float, summary: str) -> Any:
            return _make_action(ActionType.WAIT, {"value": seconds}, summary=summary)

        def type_text(value: str, summary: str, point: list[int] | None = None) -> Any:
            data: dict[str, Any] = {"value": value}
            if point is not None:
                data["point"] = point
            return _make_action(ActionType.TYPE, data, summary=summary)

        title = str(task.params.get("title") or "明天开会")
        content = str(task.params.get("content") or "记得带文件")

        await step(click(await _point_for_role(env, "button", "新建笔记"), "open new note editor"))
        await step(wait(0.4, "wait for editor"))
        title_point = await _point_for_selector(env, "input[placeholder='标题']")
        await step(type_text(title, "type note title", point=title_point))
        await step(wait(1.0, "wait for initial autosave"))
        content_point = await _point_for_selector_at(env, "textarea", css_dx=30, css_dy=24)
        await step(type_text(content, "type note content", point=content_point))
        await step(wait(1.0, "wait for content autosave"))
        await step(click(await _point_for_role(env, "button", "完成"), "finish editing"))
        await step(wait(0.5, "wait for list"))
        await step(click(await _point_for_locator(env, env.page.get_by_text(title, exact=False).first), "reopen created note"))
        await step(wait(0.4, "wait for existing editor"))
        await step(click(await _point_for_role(env, "button", "更多"), "open more menu"))
        await step(click(await _point_for_text(env, "设置提醒"), "open reminder dialog"))
        await step(wait(0.3, "wait for reminder dialog"))
        await step(click(await _point_for_role(env, "button", "确定"), "confirm default reminder"))
        await step(wait(0.8, "wait for reminder save"))
        await step(click(_css_to_physical(env, 34, 74), "return to list after setting reminder"))
        await step(wait(0.6, "wait for reminder-bearing list row"))

        list_state = await env.get_state(required_apps=["notes"])
        notes_app = Notes((list_state.get("apps") or {}).get("notes") or {})
        note = notes_app.latest_note_by_title(title)
        content_value = str((note or {}).get("content") or "")
        alarm_at = (note or {}).get("alarmAt")
        labels = (
            Notes.reminder_time_labels(int(alarm_at))
            if isinstance(alarm_at, (int, float)) and alarm_at > 0
            else []
        )
        reminder_prefixes = ["提醒", "Reminder"]
        row_text_before_detail = await _note_row_text(env, title)
        list_body_text = await _body_text(env)
        ordinary_note = next(
            (
                candidate
                for candidate in notes_app.visible_notes
                if str(candidate.get("title") or "").strip() != title
                and not isinstance(candidate.get("alarmAt"), (int, float))
            ),
            None,
        )
        ordinary_row_text = (
            await _note_row_text(env, str(ordinary_note.get("title") or ""))
            if ordinary_note
            else ""
        )

        await step(
            click(
                await _point_for_locator(env, env.page.get_by_text(title, exact=False).first),
                "reopen reminder note from list",
            )
        )
        await step(wait(0.4, "wait for detail reminder text"))
        detail_text = await _body_text(env)
        await step(click(_css_to_physical(env, 34, 74), "return to list after detail inspection"))
        await step(wait(0.5, "wait for list after detail inspection"))
        row_text_after_detail = await _note_row_text(env, title)
        await step(
            _make_action(
                ActionType.COMPLETE,
                {"return": "verified Notes list reminder chip consistency"},
                "complete custom list reminder chip replay",
            )
        )

        row_has_prefix = _contains_any(row_text_before_detail, reminder_prefixes)
        row_has_time = _contains_any(row_text_before_detail, labels)
        detail_has_time = _contains_any(detail_text, labels)
        persisted_row_has_prefix = _contains_any(row_text_after_detail, reminder_prefixes)
        persisted_row_has_time = _contains_any(row_text_after_detail, labels)
        ordinary_has_prefix = _contains_any(ordinary_row_text, reminder_prefixes)

        checks = [
            {
                "field": "notes.note_created",
                "expected": title,
                "actual": note.get("title") if note else None,
                "passed": note is not None,
            },
            {
                "field": "notes.note_content",
                "expected": content,
                "actual": content_value,
                "passed": note is not None and content in content_value,
            },
            {
                "field": "notes.note_reminder",
                "expected": "alarmAt > 0",
                "actual": alarm_at,
                "passed": isinstance(alarm_at, (int, float)) and alarm_at > 0,
            },
            {
                "field": "list.reminder_chip_visible",
                "expected": "target list row contains a reminder label and derived reminder time",
                "actual": row_text_before_detail,
                "passed": row_has_prefix and row_has_time,
            },
            {
                "field": "list.reminder_chip_matches_detail",
                "expected": labels,
                "actual": {
                    "list_row": row_text_before_detail,
                    "detail": detail_text,
                },
                "passed": row_has_time and detail_has_time,
            },
            {
                "field": "list.no_false_positive_chip",
                "expected": "ordinary note rows without alarmAt do not show reminder label",
                "actual": {
                    "ordinary_title": ordinary_note.get("title") if ordinary_note else None,
                    "ordinary_row": ordinary_row_text,
                },
                "passed": not ordinary_note or not ordinary_has_prefix,
            },
            {
                "field": "navigation.persistence",
                "expected": "target row still contains reminder label and time after detail/list navigation",
                "actual": row_text_after_detail,
                "passed": persisted_row_has_prefix and persisted_row_has_time,
            },
        ]
        passed = [check for check in checks if check["passed"]]
        failed = [check for check in checks if not check["passed"]]
        judge = JudgeResult(
            success=not failed,
            clean=True,
            progress=len(passed) / len(checks) if checks else 0.0,
            issues=failed,
            warnings=[],
        )

        final_obs = await env.get_observation()
        final_state = await env.get_state(required_apps=list(task.apps) if task.apps else None)
        final_obs = dc_replace(final_obs, state=final_state)
        stopwatch_total_s = float(getattr(env.stopwatch, "total", 0.0))
        try:
            stopwatch_flat = env.stopwatch.to_flat()
            stopwatch_tree = env.stopwatch.to_tree()
        except Exception:
            stopwatch_flat = {}
            stopwatch_tree = []
        exec_result = ExecutionResult(
            steps=len(trace),
            trace=trace,
            runtime_s=time.time() - start_time,
            finished=True,
            truncated=False,
            stop_reason=ActionType.COMPLETE,
            agent_message=env.agent_message,
            agent_answer=env.agent_answer,
            error=None,
            stopwatch_total_s=stopwatch_total_s,
            stopwatch_flat=stopwatch_flat,
            stopwatch_tree=stopwatch_tree,
        )
        episode_result = EpisodeResult(
            task_id=task.id,
            task_name=task.description,
            suite=task.suite,
            execution=exec_result,
            judge=judge,
            trial_id=0,
            apps=list(task.apps),
            max_steps=args.max_steps,
            **EpisodeResult._task_taxonomy(task),
        )
        episode.finish(episode_result.to_dict())
        summary = {
            "ok": bool(episode_result.success),
            "task_id": task.id,
            "observed_outcome": "success" if episode_result.success else "failed",
            "run_dir": str(run_dir),
            "params": dict(task.params),
            "labels": labels,
            "judge": judge.to_dict(),
            "steps": len(trace),
            "debug": {
                "list_body_text": list_body_text,
                "row_text_before_detail": row_text_before_detail,
                "detail_text": detail_text,
                "row_text_after_detail": row_text_after_detail,
                "ordinary_row_text": ordinary_row_text,
            },
        }
    except Exception as exc:
        exec_error = f"{type(exc).__name__}: {exc}"
        if episode is not None:
            exec_result = ExecutionResult(
                steps=len(trace),
                trace=trace,
                runtime_s=time.time() - start_time,
                finished=finished,
                truncated=truncated,
                stop_reason=stop_reason or "ERROR",
                agent_message=env.agent_message,
                agent_answer=env.agent_answer,
                error=exec_error,
            )
            task_id = args.task_id
            task_name = args.task_id
            suite = task_id.split(".", 1)[0] if "." in task_id else ""
            episode_result = EpisodeResult(
                task_id=task_id,
                task_name=task_name,
                suite=suite,
                execution=exec_result,
                judge=None,
                trial_id=0,
                apps=[],
                max_steps=args.max_steps,
            )
            episode.finish(episode_result.to_dict())
        else:
            recorder.record_result(
                {
                    "id": args.task_id,
                    "task_name": args.task_id,
                    "suite": args.task_id.split(".", 1)[0] if "." in args.task_id else "",
                    "apps": [],
                    "trial_id": 0,
                    "max_steps": args.max_steps,
                    "execution": {"steps": len(trace), "error": exec_error, "stop_reason": "ERROR"},
                    "judge": None,
                    "is_success": False,
                    "is_error": True,
                    "progress": 0.0,
                }
            )
        summary = {
            "ok": False,
            "task_id": args.task_id,
            "observed_outcome": "error",
            "run_dir": str(run_dir),
            "message": exec_error,
            "steps": len(trace),
        }
    finally:
        final_run_dir = recorder.finish_run()
        await env.close()

    summary["run_dir"] = str(final_run_dir)
    summary["summary_path"] = str(final_run_dir / "summary.json")
    summary["results_path"] = str(final_run_dir / "results.jsonl")
    return summary


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CUA-SWE deterministic MobileGym replay worker")
    parser.add_argument("--task-id", default="notes.CreateNoteWithReminder")
    parser.add_argument("--env-url", required=True)
    parser.add_argument("--runs-dir", required=True)
    parser.add_argument("--result-json")
    parser.add_argument("--replay-name", default="notes-create-note-with-reminder-v0")
    parser.add_argument("--max-steps", type=int, default=40)
    parser.add_argument("--delay-after-action", type=float, default=0.25)
    parser.add_argument("--screenshot-scale", type=float, default=1.0)
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--headed", action="store_false", dest="headless")
    parser.add_argument("--quiet", action="store_true", default=True)
    parser.add_argument("--verbose", action="store_false", dest="quiet")
    return parser.parse_args(argv)


async def amain(argv: list[str]) -> int:
    args = parse_args(argv)
    result_json = Path(args.result_json) if args.result_json else None
    if args.task_id != "notes.CreateNoteWithReminder":
        payload = {
            "ok": False,
            "task_id": args.task_id,
            "observed_outcome": "error",
            "message": "only notes.CreateNoteWithReminder replay is implemented",
        }
        _write_json(result_json, payload)
        print(json.dumps(payload, ensure_ascii=False, default=_json_default))
        return 2
    if args.replay_name == "notes-list-reminder-chip-v0":
        payload = await _run_notes_list_reminder_chip(args)
    else:
        payload = await _run_create_note_with_reminder(args)
    _write_json(result_json, payload)
    print(json.dumps(payload, ensure_ascii=False, default=_json_default))
    return 0 if payload.get("ok") else 1


def main() -> None:
    raise SystemExit(asyncio.run(amain(sys.argv[1:])))


if __name__ == "__main__":
    main()
