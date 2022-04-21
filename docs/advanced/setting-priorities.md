# Setting Priorities

The RabbitMQ broker configures it's queues with priority support. This means that you can send [`Request`][mognet.Request] objects with priorities set.

You can do so by setting the `priority` field, as an integer, from 0 to 10. The default is 5, and higher values mean higher priority.

```python
from mognet import Request

req = Request(
    ...,
    priority=6,
)
```

Bear in mind that messing with priorities may starve other tasks; if there are too many high-priority tasks running, they may heavily delay lower-priority tasks from running.
