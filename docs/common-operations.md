# Common operations

## Getting an arbitrary task's result by it's ID

If you know the ID of a task that you spawned (you perhaps stored it on a database), you can retrieve it's associated [`Request`][mognet.Request] through the [`App`][mognet.App] 's `result_backend` property, as follows:

```python
from uuid import UUID
from example import app

async def main():
    task_id = UUID("bb9cc944-d1d7-4232-a90f-1a0362a632f4")

    result = await app.result_backend.get(task_id)

    # Use the result. It will be `None` if it doesn't exist.

asyncio.run(main())
```

Note that every [`Request`][mognet.Request] will always have an `id`. If you don't specify one, a random one will be generated for you.

## Revoking (cancelling) a task

A task can be revoked (cancelled) through the [`App`][mognet.App] class's [`revoke()`][mognet.App.revoke] method. It takes a task ID.

```python
from uuid import UUID
from example import app

async def main():
    task_id = UUID("bb9cc944-d1d7-4232-a90f-1a0362a632f4")

    aborted_result = await app.revoke(task_id)

    print(f"Aborted result {aborted_result.id!r}")

asyncio.run(main())
```

Revoking a task does the following:

* Marks the [`Result`][mognet.Result] as `REVOKED` on the Result Backend.
* Sends a **broadcast** message to the Worker nodes to request the task function to be stopped (if it is running).
* Recursively repeats the revoke process for every single child task.

The [`Result`][mognet.Result] associated with the ID is returned. If one did not previously exist, it is created. 
Note that if a Worker node receives a [`Request`][mognet.Request] with an aborted [`Result`][mognet.Result]'s ID, it will be ignored, and the task will not be run.
Similarly, if a [`Request`][mognet.Request] message is received and its parent was revoked, it is also ignored.
