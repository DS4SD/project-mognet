# Best Practices

## Do NOT Block the Event Loop!

Mognet leverages Python's ``asyncio`` to run itself, the tasks, and for managing connections to the Task Broker and Result Backend, and, by design, it doesn't use processes or threads to run tasks or background work (unless you define a [`@task`][mognet.task] that isn't an `async def` function).

This results in a simpler architecture, but the result is that the code **must not** block for long periods of time (ideally, less than 15s).

This is because, ``async def`` s run pseudo-concurrently. If a function is designed in such a way that it blocks the CPU for too long (a CPU-bound intensive computation, for example), even if it is ``async def``, it will block the event loop, and prevent other coroutines from running.

If done for too long, it will prevent background tasks from running, which, in case of an AMQP-based Task Broker, stops connection keep-alives from being sent, which will result in disconnects.

If the task must do CPU-bound work for too long, consider using [`run_in_executor()`](https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.run_in_executor) from ``asyncio``, which allows executing such code in a ``ThreadPoolExecutor`` or ``ProcessPoolExecutor``.

Also, prefer using ``asyncio``-friendly libraries. See [https://github.com/timofurrer/awesome-asyncio](https://github.com/timofurrer/awesome-asyncio) for some examples.

If your task function code is fully CPU bound, consider making it a non `async def` function. This will make it run in the Event Loop's [default executor](https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.set_default_executor).


## AVOID Long Running Tasks

If you have a job that runs for a long period of time (think: hours), you may run into issues like [RabbitMQ disconnects](./vendor-specifics/rabbitmq.md#rabbitmq-3816-and-long-running-tasks-can-cause-disconnects). These tasks can also be considered to be more fragile to run, because they will have to restart fully from scratch, in the event of a Broker Disconnect, Node reboot (e.g., when running under Kubernetes). Long running tasks, especially if they don't yield to wait for other tasks, will also hold resources for longer periods of time, which can cause other tasks to not run, if the system is under pressure.

Therefore, it is a good idea to split the work into smaller chunks, and have each chunk be processed separately. If there is still a need to have a task orchestrating them all, you can use [State](./advanced/stateful-tasks.md) variables to create "checkpoints", which you can then use to know where your task should resume from.

It is also a good idea to, when possible, make use of the [`Pause`][mognet.exceptions.task_exceptions.Pause] exception to pause a task's function. This will cause the task message to be put back into the queue, so that it can be resumed at a later stage. See [Pause a Task](./advanced/stateful-tasks.md#pause-a-task).

Note: Currently it is not possible to "delay" the re-run of the task, though that is something to consider, provided there's a need for it.

## DO Set the Task's Name Yourself

When using the [`@task`][mognet.task] decorator, you can choose to omit `name`. In that case, the function's full name (i.e., ``__module__.__name__``) will be used instead. That is, if you have a function `my_task` in a module named `demo`, the default name would be `demo.my_task`.

While convenient, this is not something we recommend doing because, if you change the function's name, or move it to another file, especially during a rolling upgrade, tasks may break. That is because the name that is set on the decorator is also the name used for the `Request` object that is created.

Therefore, we recommend always setting the task's name manually to prevent breaking changes when the functions are moved around or renamed.
