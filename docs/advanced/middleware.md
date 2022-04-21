# Middleware

Middleware can be used into hook into several points of the Mognet application, like, for example:

- When tasks start / finish
- When the worker's status changes
- When the app starts or stops

It is therefore a good candidate for tasks like:

- Setting up and cleaning up resources
- Task tracking/logging (e.g., via Sentry)
- Metrics logging (e.g., via StatsD, or Prometheus)
- Notifications system for clients (e.g., using Socket.IO, see [python-socketio](https://python-socketio.readthedocs.io/en/latest/index.html))

## Creating Middleware

To create a Middleware, first you need to create a class that implements the [`Middleware`][mognet.Middleware] class. This class, by default, does nothing.

```python
from mognet import Middleware

class MyMiddleware(Middleware):
    async def on_running_task_count_changed(self, running_task_count: int):
        print(f"We currently have {running_task_count} tasks running!")
```

## Using Middleware in your app

To add middleware to a Mognet Worker's app, you use the [`add_middleware()`][mognet.App.add_middleware] function, ideally after creating the [`App`][mognet.App] object:

```python
from mognet import App

app = App(...)

app.add_middleware(MyMiddleware())
```

## A more concrete example

See [`AutoShutdownMiddleware`](https://github.ibm.com/CognitiveCore-Utilities/mognet-demo/blob/457dd98ebb284ae1e96bc30190c718b18ed5050d/mognet_demo/middleware/auto_shutdown.py#L28). This class implements a common pattern for long running applications: periodic restarts to release memory, due to Python's memory model.
