# Stateful Tasks and Resumeable Functions

You can have mechanisms similar to Azure's [Durable Functions](https://docs.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-overview?tabs=csharp) by making use of [`State`][mognet.state.state.State].

State acts like a `dict[str, Any]`, whose values must be JSON-serializable, and you access it through your task's `context` argument, and you can use it to store information that gets persisted across Worker reboots.

Some cases where it can be useful include:

- Storing a list of subtask IDs to check for, after launching them
- Storing an index, or some identifier, that allows the task function to resume from a certain point

## An example

```python
from typing import List

from mognet import task, Context

@task(name="demo.state")
async def use_state(context: Context, files: List[str]):
    # Let's assume that `files` is a list of file names, and each takes a long time to process.
    # We can use state to store what was the last file we were working on.
    #
    # Then, should the task restart, we can instead continue from there.

    # The first time this function gets called, "current_index" won't exist.
    # So, we put a default value of 0 (otherwise we would get None).
    last_processed_index: int = await context.state.get("current_index", 0)

    for i, file in enumerate(files):
        # Skip files already processed...
        if i < last_processed_index:
            continue

        await process_file(file)  # Implementation left to the reader...

        # Create a check point here in case the Worker reboots.
        await context.state.set(current_index=i)
```

## State Lifetime and Storage

State associated with a task is stored on Redis, hence the asynchronous interface. All values are stored as JSON, meaning that you will need to (de)serialize complex values (such as `BaseModel` classes from Pydantic) yourself.

All state has a TTL, you can set the default TTL in the [`RedisStateBackendSettings`][mognet.state.state_backend_config.RedisStateBackendSettings] class when you configure your Mognet App instance.

After your task's function is done (either because it finished successfully, failed, or got revoked), it's state is automatically cleared.

# Pause a Task

Task functions can also be paused (or rather, stopped, and them restarted).

Let's take the previous example, and assume that we don't want to process more than 5 files at a time, and after that, we want to stop processing files for a while. Let's assume that we want to do this because each file takes a long time to process, and it's processing cannot be done via subtasks.

For that, we can use the [`Pause`][mognet.exceptions.task_exceptions.Pause] exception. Raising this exception from a task function will:

- Mark it as `SUSPENDED` on the Result Backend
- Send the `Request` message back to the Task Broker
- Free the Mognet Worker to go do something else

Once the message is returned to the queue, it will eventually be picked up again, situation where the task will restart. Combining this with state allows the function to resume from where it left off

## An Example

```python
from typing import List

from mognet import task, Context
from mognet.exceptions.task_exceptions import Pause

@task(name="demo.state")
async def use_state(context: Context, files: List[str]):
    # Let's assume that `files` is a list of file names, and each takes a long time to process.
    # We can use state to store what was the last file we were working on.
    #
    # Then, should the task restart, we can instead continue from there.

    # The first time this function gets called, "current_index" won't exist.
    # So, we put a default value of 0 (otherwise we would get None).
    last_processed_index: int = await context.state.get("current_index", 0)

    processed_file_count = 0

    for i, file in enumerate(files):
        # Skip files already processed...
        if i < last_processed_index:
            continue

        await process_file(file)  # Implementation left to the reader...

        # Create a check point here in case the Worker reboots.
        await context.state.set(current_index=i)

        processed_file_count += 1

        if processed_file_count == 5:
            # Here, the task function will stop.
            #
            # Make sure you don't catch this exception yourself!
            #
            # When the Request for this task is picked up again, the state will allow it
            # to know where to resume from.
            raise Pause()
```
