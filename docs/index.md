# Mognet

![Mognet (Final Fantasy IX) Letter](https://static.wikia.nocookie.net/finalfantasy/images/4/4e/Moogle_Letter_FFIX_Art.jpg){ align=right }

Mognet is a fast, simple framework to build distributed applications using task queues.

## Getting Started

### Installation

Mognet can be installed via pip, with:

```
pip install mognet
```

### Defining an application and some tasks

Everything starts with the [`App`][mognet.App] class. From here, you can launch and revoke tasks, get their status, and so on.

Creating an [`App`][mognet.App] requires that you initialize it with a name. This is done for scoping objects on the Results Backend and the Task Broker instances.
We also need to tell the app to which Task Broker and to which Result Backend it should connect to. We can do it through the [`AppConfig`][mognet.AppConfig] class.

Then, to define a task, you use the [`@task`][mognet.task] decorator. Every task has to follow these rules:

* Each task must have a name. If not set, one will be set for you.
* The function receives, in its first argument, an object of type [`Context`][mognet.Context]. We will go into details of this object in future sections.

```python
from mognet import App, task, Context, AppConfig

# Please note that, for brevity reasons, we are showing parsing a raw dict rather
# than specifying all the intermediate types manually.
# We recommend looking into the contents of this class.
#
# Note that we also don't specify the URLs to the Redis and RabbitMQ themselves,
# opting instead for the defaults.
config = AppConfig.parse_obj({
    "result_backend": {
        # Assumes a Redis on localhost:6379 with no credentials
        "redis": {}  
    },
    "state_backend": {
        # Assumes a Redis on localhost:6379 with no credentials
        "redis": {}  
    },
    "broker": {
        # Assumes a RabbitMQ on localhost:5672 with no credentials
        "amqp": {}  
    }
})

app = App(name="example")

@task(name="example.add")
async def add(context: Context, n1: float, n2: float):
    return n1 + n2
```

### Running a Mognet application

A Mognet application is started using the ``mognet`` cli command, as follows

```bash
mognet your_app.mognet_app_module:app run
``` 

Where ``your_app.mognet_app_module`` is the module name that holds your Mognet application, much like when the ``python -m module_name`` command is used, and ``app`` represents the name of the variable that holds the application itself in the module.

Note that you can omit ``:app`` if your application is stored in a variable called ``app``. The CLI will, by default, look for such a variable, unless you override it.

This will start the application, connect it to the Task Broker and Result Backend, and make it start listening to tasks.

Sending a ``SIGINT`` (``Ctrl+C``) or ``SIGTERM`` will gracefully stop the application.

So, assuming the previous example file was saved into a file called ``example.py``, the application can be started as follows:

```bash
mognet example run
```

### Running a task

To run a task, we make use of [`Request`][mognet.Request] objects. They hold information on which function should be run, and what arguments to run it with.

```python
import asyncio
from mognet import Request

# We will be using the app we created on the previous example
from example import app

async def main():
    # Create a Request to run the task created on the previous example
    req = Request(name="example.add", args=(1, 2))

    # Using an `async with` block will cause the app to connect
    # to the broker instances, and clean up after leaving this block.
    # For information on how you can have the app connected in the background,
    # for example, on Web Applications, see examples
    async with app:
        # After the app is connected, we can send the request to the
        # worker nodes. Awaiting allows us to receive the return value from the task.
        result = await app.run(req)

        assert result == 3

asyncio.run(main())
```

The example above represents how to create a request, execute it (in a different process), and wait for the result.

Quite a few things happened in the background, however:

* Each [`Request`][mognet.Request] object has a UUID that identifies it. This ID is later used as the key to retrieve the result of the task execution.
* The app instance never connects automatically, so we must be explicit.
* When ``app.run(req)`` is called, it:
  1. Creates, on the Result Backend, a [`Result`][mognet.Result] entry for the ID of the [`Request`][mognet.Request]
  2. Submits the [`Request`][mognet.Request] to the Task Broker
  3. Waits for the previously created [`Result`][mognet.Result], which will either return the value, or raise the exception that was raised by the task's execution.
