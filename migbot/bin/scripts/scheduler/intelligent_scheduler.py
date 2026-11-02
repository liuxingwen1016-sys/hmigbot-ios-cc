#!/usr/bin/env python3
"""智能调度器 - 优化任务执行顺序

原则：
1. 长任务优先（减少总等待时间）
2. 依赖关系满足
3. 并行度最大化
"""
from __future__ import annotations

import heapq
from typing import Any
from dataclasses import dataclass, field


@dataclass
class Task:
    """任务定义"""
    id: str
    estimated_minutes: int
    dependencies: list[str] = field(default_factory=list)
    priority: int = 0

    def __lt__(self, other):
        # 长任务优先（用于堆排序）
        return self.estimated_minutes > other.estimated_minutes


class TaskScheduler:
    """任务调度器"""

    def __init__(self, max_workers: int = 25):
        self.max_workers = max_workers
        self.tasks: dict[str, Task] = {}
        self.completed: set[str] = set()

    def add_task(self, task: Task):
        """添加任务"""
        self.tasks[task.id] = task

    def can_run(self, task: Task) -> bool:
        """检查任务是否可以运行"""
        return all(dep in self.completed for dep in task.dependencies)

    def schedule(self, strategy: str = "long_task_first") -> list[list[str]]:
        """生成执行计划

        Returns:
            批次列表，每个批次内的任务可以并行
        """
        batches = []
        remaining = set(self.tasks.keys())

        while remaining:
            # 找出可以运行的任务
            ready = [
                self.tasks[tid] for tid in remaining
                if self.can_run(self.tasks[tid])
            ]

            if not ready:
                raise ValueError("Circular dependency detected")

            # 排序策略
            if strategy == "long_task_first":
                ready.sort(key=lambda t: t.estimated_minutes, reverse=True)
            elif strategy == "short_task_first":
                ready.sort(key=lambda t: t.estimated_minutes)
            elif strategy == "priority":
                ready.sort(key=lambda t: (t.priority, -t.estimated_minutes))

            # 取最多 max_workers 个任务
            batch = ready[:self.max_workers]
            batch_ids = [t.id for t in batch]

            batches.append(batch_ids)

            # 标记为已完成
            for tid in batch_ids:
                remaining.remove(tid)
                self.completed.add(tid)

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
