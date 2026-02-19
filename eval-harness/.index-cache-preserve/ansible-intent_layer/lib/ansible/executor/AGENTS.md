# Executor

Core execution engine that runs plays, tasks, and manages workers.

## Key components

- `task_executor.py` — runs individual tasks: loads action plugin, handles loops, retries, async
- `play_iterator.py` — walks through play structure (pre_tasks, roles, tasks, post_tasks, handlers)
- `task_queue_manager.py` — manages worker processes via multiprocessing
- `module_common.py` — AnsiballZ: packages modules + module_utils for remote execution
- `playbook_executor.py` — top-level: iterates over plays in a playbook

## Execution flow

1. PlaybookExecutor iterates plays
2. StrategyPlugin (e.g., linear) uses PlayIterator to walk tasks
3. TaskQueueManager dispatches to worker processes
4. TaskExecutor loads the action plugin and runs it
5. Action plugin packages module via AnsiballZ and sends to target

## Contracts

- Workers communicate via multiprocessing queues
- Task results flow back through the queue to the strategy plugin
- Handler execution is deferred until all tasks in a block complete
- `rescue` and `always` blocks in block/rescue/always are handled by PlayIterator
