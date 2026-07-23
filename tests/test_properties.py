"""Property-based tests using Hypothesis for the CCPM scheduling engine."""

from collections import defaultdict

import hypothesis.strategies as st
from hypothesis import given, settings

from ccpm_scheduler import (
    BUFFER_METHODS,
    Link,
    Network,
    Resource,
    Task,
    build_schedule,
    check_schedule,
    validate_network,
)


@st.composite
def valid_networks(draw):
    """Generates a guaranteed valid DAG project network with resources."""
    num_resources = draw(st.integers(min_value=1, max_value=4))
    resources = [
        Resource(id=f"r{i}", name=f"Resource {i}", capacity=draw(st.integers(min_value=1, max_value=3)))
        for i in range(1, num_resources + 1)
    ]
    res_ids = [r.id for r in resources]

    num_tasks = draw(st.integers(min_value=3, max_value=15))
    tasks = []

    for i in range(1, num_tasks + 1):
        task_id = f"T{i}"
        name = f"Task {i}"
        duration = draw(st.integers(min_value=1, max_value=20))
        # Ensure DAG by picking predecessors strictly from earlier task IDs
        possible_preds = [t.id for t in tasks]
        pred_ids = (
            draw(st.sets(st.sampled_from(possible_preds), max_size=min(3, len(possible_preds))))
            if possible_preds
            else set()
        )

        # Assign 1 or 2 resources
        assigned_res = draw(st.sets(st.sampled_from(res_ids), min_size=1, max_size=min(2, len(res_ids))))

        tasks.append(
            Task(
                id=task_id,
                name=name,
                realistic_duration=duration,
                links=[Link(pred_id=p) for p in pred_ids],
                resource_ids=assigned_res,
            )
        )

    return Network(tasks=tasks, resources=resources)


@settings(max_examples=40, deadline=None)
@given(net=valid_networks(), method=st.sampled_from(list(BUFFER_METHODS)))
def test_scheduling_invariants(net, method):
    """Property test verifying core invariants on generated valid networks."""
    # 1. Validation must succeed for generated DAG networks
    report = validate_network(net)
    assert report.ok, f"Generated valid network failed validation: {[i.message for i in report.issues]}"

    # 2. Build schedule must succeed
    result = build_schedule(net, buffer_method=method)
    sched = result.schedule

    # 3. Invariant: Schedule verification check passes
    check_rep = check_schedule(sched, net)
    assert check_rep.ok, f"Built schedule failed check_schedule: {[i.message for i in check_rep.issues]}"

    # 4. Invariant: Task finish date >= start date + duration
    for r in sched.rows:
        assert r.finish >= r.start + r.duration

    # 5. Invariant: Resource daily utilization never exceeds capacity
    res_cap = {r.id: r.capacity for r in net.resources}
    daily_usage = defaultdict(lambda: defaultdict(int))

    for r in sched.rows:
        if r.type != "task" or not r.resource_ids:
            continue
        res_list = [res.strip() for res in r.resource_ids.split(";") if res.strip()]
        for res_id in res_list:
            for day in range(r.start, r.finish):
                daily_usage[res_id][day] += 1

    for res_id, days in daily_usage.items():
        cap = res_cap.get(res_id, 1)
        for day, usage in days.items():
            assert usage <= cap, f"Resource {res_id} over-allocated on day {day}: {usage} > {cap}"
