"""Large network performance and stress testing for ccpm-scheduler."""

import time

from ccpm_scheduler import (
    Link,
    Network,
    Resource,
    Task,
    build_schedule,
    check_schedule,
    validate_network,
)


def generate_100_task_network() -> Network:
    """Generates a synthetic 100-task project network with 5 resources,

    multiple parallel chains, and merge points into a main critical path.
    """
    resources = [
        Resource(id="r1", name="Engineering", capacity=2),
        Resource(id="r2", name="Design", capacity=1),
        Resource(id="r3", name="QA", capacity=2),
        Resource(id="r4", name="DevOps", capacity=1),
        Resource(id="r5", name="Docs", capacity=1),
    ]

    tasks = []
    # Main critical chain: T001 -> T010 -> T020 -> ... -> T100
    for i in range(1, 101):
        task_id = f"T{i:03d}"
        name = f"Project Task {i}"
        duration = 2 + (i % 7)  # durations between 2 and 8 days

        # Assign resources based on task index
        res_index = (i % 5) + 1
        res_ids = {f"r{res_index}"}

        # Build dependencies: linear main chain plus parallel feeding chains
        links = []
        if i > 1:
            if i % 10 == 1:
                # Chain merge: depends on previous main anchor
                prev_id = f"T{i - 10:03d}"
                links.append(Link(pred_id=prev_id))
            else:
                # In-chain predecessor
                links.append(Link(pred_id=f"T{i - 1:03d}"))

        tasks.append(
            Task(
                id=task_id,
                name=name,
                realistic_duration=duration,
                links=links,
                resource_ids=res_ids,
            )
        )

    return Network(tasks=tasks, resources=resources)


def test_100_task_large_network_performance():
    """Tests validation, resource-leveling, schedule building, and schedule verification

    on a 100-task project network within performance thresholds (< 2 seconds).
    """
    net = generate_100_task_network()
    assert len(net.tasks) == 100

    # 1. Validate network
    start_time = time.perf_counter()
    report = validate_network(net)
    assert report.ok, f"100-task network validation failed: {[i.message for i in report.issues]}"

    # 2. Build schedule (resource leveling + buffer placement)
    result = build_schedule(net, title="100-Task Benchmark Project")
    build_duration = time.perf_counter() - start_time

    assert result.schedule is not None
    assert len(result.schedule.rows) >= 100
    assert build_duration < 5.0, f"100-task build took too long: {build_duration:.3f}s"

    # 3. Check schedule integrity
    check_report = check_schedule(result.schedule, net)
    assert check_report.ok, f"100-task schedule check failed: {[i.message for i in check_report.issues]}"
