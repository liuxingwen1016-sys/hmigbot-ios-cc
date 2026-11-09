import unittest

from intelligent_scheduler import Task, TaskScheduler


class SchedulerTests(unittest.TestCase):
    def test_schedule_respects_host_limits_and_dependencies(self):
        scheduler = TaskScheduler(max_workers=4, host_limits={"claude": 1, "codex": 2})
        scheduler.add_task(Task("a", 20, host="claude"))
        scheduler.add_task(Task("b", 5, host="claude"))
        scheduler.add_task(Task("c", 5, dependencies=["a"], host="codex"))
        scheduler.add_task(Task("d", 5, host="codex"))
        batches = scheduler.schedule()
        self.assertEqual(batches[0], ["a", "d"])
        self.assertEqual(batches[1], ["b", "c"])

    def test_acquire_releases_independent_work_without_waiting_for_slow_task(self):
        scheduler = TaskScheduler(max_workers=2, host_limits={"claude": 2})
        scheduler.add_task(Task("slow", 60))
        scheduler.add_task(Task("independent", 5))
        scheduler.add_task(Task("dependent", 5, dependencies=["slow"]))
        first = {task.id for task in scheduler.acquire()}
        self.assertEqual(first, {"slow", "independent"})
        scheduler.finish("independent")
        self.assertEqual(scheduler.acquire(), [])
        scheduler.finish("slow")
        self.assertEqual([task.id for task in scheduler.acquire()], ["dependent"])

    def test_unknown_dependency_and_cycle_are_rejected(self):
        scheduler = TaskScheduler()
        scheduler.add_task(Task("a", 1, dependencies=["missing"]))
        with self.assertRaises(ValueError):
            scheduler.schedule()
        scheduler = TaskScheduler()
        scheduler.add_task(Task("a", 1, dependencies=["b"]))
        scheduler.add_task(Task("b", 1, dependencies=["a"]))
        with self.assertRaises(ValueError):
            scheduler.schedule()


if __name__ == "__main__":
    unittest.main()
