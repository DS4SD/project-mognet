# RabbitMQ

There a few things one needs to be aware of, when using Mognet with RabbitMQ.

## Implementation Details

### Queue Names

All queue names get the name of the Mognet application (i.e., what you pass on the constructor) as a prefix. This is to allow different Mognet applications to run on the same broker.

The default queue name is `tasks`, which gets mapped to `{app_name}.tasks`. You can set custom queue names through the [`AppConfig`][mognet.AppConfig] class's `task_routes` property. This is a mapping of `[task name] -> [queue]`. Again, the app's name is prefixed to what you set in `[queue]`.

### Queues Used

Mognet defines one default task queue, and one "control" queue is created per-worker. 

The task queues are are attached to a `direct` exchange, are durable, and have priority support (see [Priority Queue Support](https://www.rabbitmq.com/priority.html)). These queues, like the name implies, are used for passing the `Request` messages used for tasks.

The control queues are ephemeral (deleted when the Worker's consumer is closed), and are used for sending messages directly to Workers (like, for example, when you use the `mognet nodes status` command). More importantly, they are also used when you revoke a task. Revoking a task causes a **broadcast** message to be sent to all Worker nodes to tell them to cancel running a certain task.

## Gotchas

### RabbitMQ ``>=3.8.16`` and long-running tasks can cause disconnects

Version 3.8.16 (well, 3.8.15) of RabbitMQ introduced a backport where, by default, a consumer must acknowledge any message it receives within 15 minutes.

This will break any task that has to run for long periods of time.

See [https://github.com/celery/celery/issues/6760](https://github.com/celery/celery/issues/6760) for the issue on Celery.

An issue was created in RabbitMQ: [https://github.com/rabbitmq/rabbitmq-server/issues/3032](https://github.com/rabbitmq/rabbitmq-server/issues/3032), and it's by design, see [https://github.com/rabbitmq/rabbitmq-server/pull/2990](https://github.com/rabbitmq/rabbitmq-server/pull/2990) for reasoning.

You should, therefore, tune your RabbitMQ consumer timeouts, or ideally design your tasks such that they don't take too long. One such example is to use [Stateful Tasks](../advanced/stateful-tasks.md).

Alternatively, you can disable it altogether, or configure it to have a higher value, according to [Delivery Acknowledgement Timeout](https://www.rabbitmq.com/consumers.html#acknowledgement-timeout).
