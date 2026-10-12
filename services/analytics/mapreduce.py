"""A miniature MapReduce engine (Unit 4: Apache Hadoop).

Same programming model as Hadoop, run on a pool of worker processes:

    input split -> MAP (per split) -> COMBINE (local pre-aggregation) ->
    SHUFFLE (partition by hash(key) % reducers) -> REDUCE -> output

Mapper/combiner/reducer must be top-level functions so they can be pickled
and shipped to the worker processes - exactly the constraint Hadoop places
on its Mapper and Reducer classes.
"""

import time
from collections import defaultdict
from concurrent.futures import Executor
from typing import Callable, Iterable


def _map_task(args):
    mapper, combiner, split = args
    grouped: dict = defaultdict(list)
    emitted = 0
    for record in split:
        for key, value in mapper(record):
            grouped[key].append(value)
            emitted += 1
    if combiner is not None:
        combined = {k: [combiner(k, v)] for k, v in grouped.items()}
    else:
        combined = dict(grouped)
    return combined, emitted, len(split)


def _reduce_task(args):
    reducer, items = args
    return [(key, reducer(key, values)) for key, values in items]


def _split(records: list, n: int) -> list[list]:
    n = max(1, min(n, len(records) or 1))
    size = -(-len(records) // n)
    return [records[i:i + size] for i in range(0, len(records), size)] or [[]]


def run_mapreduce(
    records: list,
    mapper: Callable,
    reducer: Callable,
    combiner: Callable | None = None,
    num_mappers: int = 4,
    num_reducers: int = 2,
    executor: Executor | None = None,
) -> tuple[dict, dict]:
    t0 = time.perf_counter()
    splits = _split(records, num_mappers)

    map_args = [(mapper, combiner, s) for s in splits]
    t_map = time.perf_counter()
    map_results = list(executor.map(_map_task, map_args)) if executor else [_map_task(a) for a in map_args]
    map_ms = (time.perf_counter() - t_map) * 1000

    # SHUFFLE: group every mapper's output by key, then partition keys across reducers.
    t_shuffle = time.perf_counter()
    merged: dict = defaultdict(list)
    emitted = pairs_after_combine = 0
    for combined, n_emitted, _n_records in map_results:
        emitted += n_emitted
        for key, values in combined.items():
            merged[key].extend(values)
            pairs_after_combine += len(values)
    partitions: list[list] = [[] for _ in range(max(1, num_reducers))]
    for key, values in merged.items():
        partitions[hash(str(key)) % len(partitions)].append((key, values))
    shuffle_ms = (time.perf_counter() - t_shuffle) * 1000

    reduce_args = [(reducer, part) for part in partitions]
    t_reduce = time.perf_counter()
    reduce_results = list(executor.map(_reduce_task, reduce_args)) if executor else [_reduce_task(a) for a in reduce_args]
    reduce_ms = (time.perf_counter() - t_reduce) * 1000

    output = {key: value for part in reduce_results for key, value in part}
    stats = {
        "input_records": len(records),
        "map_tasks": len(splits),
        "reduce_tasks": len(partitions),
        "pairs_emitted_by_mappers": emitted,
        "pairs_shuffled_after_combiner": pairs_after_combine,
        "shuffle_reduction_pct": round(100 * (1 - pairs_after_combine / emitted), 1) if emitted else 0.0,
        "distinct_keys": len(output),
        "keys_per_reducer": [len(p) for p in partitions],
        "map_ms": round(map_ms, 1), "shuffle_ms": round(shuffle_ms, 1), "reduce_ms": round(reduce_ms, 1),
        "total_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
    return output, stats
