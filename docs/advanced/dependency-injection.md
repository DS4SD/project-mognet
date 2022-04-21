# Dependency Injection via Services

For decoupling your app's tasks from their dependencies, you can use Services. These are functions that return a value.

## Creating a service

To create a service, declare a function that receives a [`Context`][mognet.Context], an optional list of arguments, and returns a value.

For example, you can use a Service to create a temporary directory for a task:

```python
import tempfile
from mognet import Context
from pathlib import Path

def temp_dir(context: Context) -> Path:
    task_name = context.request.name
    task_id = str(context.request.id)

    return Path(tempfile.mkdtemp(prefix=task_name, suffix=task_id))
```

## Using a service in a task

To use a service in a task, use [`get_service`][mognet.Context.get_service] as follows:

```python
from mognet import Context, task
from example.services import temp_dir

@task(name="test.use_temp_dir")
async def use_temp_dir(context: Context):
    
    my_temp_dir = context.get_service(temp_dir)

    # Use my_temp_dir
```

The result of the function call is not stored, meaning that every time you call [`get_service`][mognet.Context.get_service], you will get a new temporary directory.

## Parametrized Services

To create a Service that accepts parameters, add the parameters to the Service function, and pass the values via the [`get_service`][mognet.Context.get_service] call.

```python
from mognet import Context, task

class Counter:
    def __init__(self, n: int):
        self.n = n

    def increment(self, n: int):
        self.n += n

def counter(context: Context, start: int):
    return Counter(start)

@task(name="example.use_counter")
async def use_counter(context: Context):
    my_counter = context.get_service(counter, 5)

    # my_counter is a Counter that starts with 5
    counter.increment(1)

    assert counter.n == 6
```

## Using a class as a Service

Classes can be used as services, too, provided they extend the [`ClassService`][mognet.service.class_service.ClassService] class.

Class Services are different from their function counterparts, because:

* The class is initialized only once, meaning that they are singletons;
* They have access to ``__enter__`` and ``__exit__`` methods for setup and teardown:
 
  * Initialization, unless done explicitly (see :ref:`overriding-a-service`), is lazy
  * Tear down is done at app shutdown

* They act as factories, and the ``__call__`` method must be overriden in order to return the value.
* To get the value from a Class Service, the ``get_service`` method is called with the class. Argument passing is still allowed.

Class Services are ideal for managed, long-lived resources, such as database connections.

## Async Services

Some services require some asyncio-based setup. Their functions can be ``async def`` (coroutines), however, since ``get_service`` is sync, your app's code must ``await`` the returned coroutine itself.

## Using context managers

It's on the roadmap 😉

## Overriding a service

To override Services, you can use the `services` dictionary on the [`App`][mognet.App] class. The keys are the functions/classes that represent your services,
and the values are callables (i.e., either a function, an object with a ``__call__`` or a [`ClassService`][mognet.service.class_service.ClassService] instance.

Let's assume we want to override the ``counter`` Service we created previously. To do it, we would do the following:

```python

from mognet import Context

# Get the reference to the original service
from example.services import counter, MyClassService

# Assume that this has the same interface 
# as Counter
from counter_lib import NoDecrementCounter

app = App(...)

def different_counter(context: Context, n: int):
    return NoDecrementCounter(n)

app.services[counter] = different_counter
```

This effectively redirects the call to a different function, allowing for decoupling your app's components. You can use this technique in your unit tests, in order to inject different objects into your tasks for testing purposes.
