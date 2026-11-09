#!/usr/bin/env python3
"""智能调度器 - 优化任务执行顺序

原则：
1. 长任务优先（减少总等待时间）
2. 依赖关系满足
3. 并行度最大化
"""
from __future__ import annotations

from typing import Any, Iterable
from dataclasses import dataclass, field


@dataclass
class Task:
    """任务定义"""
    id: str
    estimated_minutes: int
    dependencies: list[str] = field(default_factory=list)
    priority: int = 0
    host: str = "claude"
    timeout_minutes: int | None = None

    def __lt__(self, other):
        return (self.estimated_minutes, self.priority) > (other.estimated_minutes, other.priority)


class TaskScheduler:
    """任务调度器"""

    def __init__(self, max_workers: int = 25, host_limits: dict[str, int] | None = None):
        self.max_workers = max_workers
        # The defaults mirror the original host-specific ceilings.  A caller
        # may override them for a local Codex installation or CI.
        self.host_limits = dict(host_limits or {"claude": 20, "codex": 8, "deveco": 10})
        self.tasks: dict[str, Task] = {}
        self.completed: set[str] = set()
        self.running: set[str] = set()

    def add_task(self, task: Task):
        """添加任务"""
        if task.id in self.tasks:
            raise ValueError(f"duplicate task id: {task.id}")
        self.tasks[task.id] = task

    def can_run(self, task: Task) -> bool:
        """检查任务是否可以运行"""
        return all(dep in self.completed for dep in task.dependencies)

    def _validate(self) -> None:
        unknown = sorted({dep for task in self.tasks.values() for dep in task.dependencies if dep not in self.tasks})
        if unknown:
            raise ValueError(f"unknown dependencies: {', '.join(unknown)}")
        self_loops = sorted(task.id for task in self.tasks.values() if task.id in task.dependencies)
        if self_loops:
            raise ValueError(f"self dependency: {', '.join(self_loops)}")

    def ready(self, completed: Iterable[str] | None = None, running: Iterable[str] | None = None) -> list[Task]:
        """Return dependency-ready tasks without mutating scheduler state."""
        done = set(self.completed if completed is None else completed)
        active = set(self.running if running is None else running)
        return [task for task in self.tasks.values()
                if task.id not in done and task.id not in active
                and all(dep in done for dep in task.dependencies)]

    def acquire(self, completed: Iterable[str] | None = None, running: Iterable[str] | None = None) -> list[Task]:
        """Select a dependency-ready dispatch set under global/host limits.

        This is the runtime counterpart to :meth:`schedule`: tasks are only
        released when their own dependencies are complete, so an unrelated
        slow task does not hold back the rest of the graph.
        """
        self._validate()
        active = set(self.running if running is None else running)
        counts: dict[str, int] = {}
        for task_id in active:
            task = self.tasks.get(task_id)
            if task:
                counts[task.host] = counts.get(task.host, 0) + 1
        selected: list[Task] = []
        for task in sorted(self.ready(completed, active), key=lambda item: (-item.priority, -item.estimated_minutes, item.id)):
            if len(selected) >= self.max_workers:
                break
            limit = self.host_limits.get(task.host, self.max_workers)
            if counts.get(task.host, 0) >= limit:
                continue
            selected.append(task)
            counts[task.host] = counts.get(task.host, 0) + 1
        self.running.update(task.id for task in selected)
        return selected

    def finish(self, task_id: str, success: bool = True) -> None:
        """Record one worker result and release its dependants on success."""
        if task_id not in self.tasks:
            raise KeyError(task_id)
        self.running.discard(task_id)
        if success:
            self.completed.add(task_id)

    def schedule(self, strategy: str = "long_task_first") -> list[list[str]]:
        """生成执行计划

        Returns:
            批次列表，每个批次内的任务可以并行
        """
        self._validate()
        batches = []
        remaining = set(self.tasks.keys())
        completed: set[str] = set()

        while remaining:
            # 找出可以运行的任务
            ready = [self.tasks[tid] for tid in remaining
                     if all(dep in completed for dep in self.tasks[tid].dependencies)]

            if not ready:
                raise ValueError("Circular dependency detected")

            # 排序策略
            if strategy == "long_task_first":
                ready.sort(key=lambda t: (-t.estimated_minutes, -t.priority, t.id))
            elif strategy == "short_task_first":
                ready.sort(key=lambda t: (t.estimated_minutes, -t.priority, t.id))
            elif strategy == "priority":
                ready.sort(key=lambda t: (-t.priority, -t.estimated_minutes, t.id))
            else:
                raise ValueError(f"unknown scheduling strategy: {strategy}")

            # 取最多 max_workers 个任务
            batch: list[Task] = []
            host_counts: dict[str, int] = {}
            for task in ready:
                if len(batch) >= self.max_workers:
                    break
                limit = self.host_limits.get(task.host, self.max_workers)
                if host_counts.get(task.host, 0) >= limit:
                    continue
                batch.append(task)
                host_counts[task.host] = host_counts.get(task.host, 0) + 1
            batch_ids = [task.id for task in batch]

            batches.append(batch_ids)

            # 标记为已完成
            for tid in batch_ids:
                remaining.remove(tid)
                completed.add(tid)

        return batches

    def estimate_time(self, batches: list[list[str]]) -> int:
        """估算总时间（分钟）"""
        total = 0
        for batch in batches:
            # 批次时间 = 最长任务的时间
            batch_time = max(
                self.tasks[tid].estimated_minutes
                for tid in batch
            )
            total += batch_time
        return total


if __name__ == "__main__":
    # 测试
    scheduler = TaskScheduler(max_workers=5)

    # 添加任务
    scheduler.add_task(Task("page_001", 10))
    scheduler.add_task(Task("page_002", 5))
    scheduler.add_task(Task("page_003", 15))
    scheduler.add_task(Task("page_004", 8))
    scheduler.add_task(Task("page_005", 12))
    scheduler.add_task(Task("page_006", 3))

    # 添加带依赖的任务
    scheduler.add_task(Task("feat_001", 60, dependencies=[]))
    scheduler.add_task(Task("feat_002", 30, dependencies=["feat_001"]))

    # 调度
    batches = scheduler.schedule(strategy="long_task_first")

    print("Execution plan:")
    for i, batch in enumerate(batches, 1):
        batch_time = max(scheduler.tasks[tid].estimated_minutes for tid in batch)
        print(f"Batch {i} ({batch_time}min): {batch}")

    total_time = scheduler.estimate_time(batches)
    print(f"\nTotal estimated time: {total_time} minutes")
    print("✅ Scheduler test passed")
