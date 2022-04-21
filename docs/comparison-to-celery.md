# Comparison to Celery

There are some things to be aware of when using Mognet, if you're coming from Celery.

## Result Persistence

As of the time of writing this document (June 2021), in Celery, if you submit a task ``Signature`` for execution, its corresponding ``AsyncResult`` will only exist after the task started,
and attempting to retrieve a non-existing ``AsyncResult`` will instead result in a default instance being returned with ``PENDING`` status.

Mognet, on the other hand, will create a [`Result`][mognet.Result] instance on the Result Backend at the time the [`Request`][mognet.Request] gets sent to the Task Broker. This ensures that, unless the message gets lost in the Task Broker, a ``PENDING`` state really does mean that.

## No multi-worker concurrency

Mognet does not use a multi-worker architecture, be it via Threads, Processes, Greenlets, Eventlets, etc. Instead, it leverages only ``asyncio`` to run itself and the tasks you define.

By default, it is configured to only run one task at once. You can override this by setting `minimum_concurrency` on [AppConfig][mognet.AppConfig] to a value greater than ``1``.

Bear in mind that the higher the value, the more resources you will need on your worker. This value will vary greatly depending on the nature of your tasks.
For example, if your tasks are primarily CPU-bound, it is best to launch two separate ``mognet ... run`` processes instead.

To run multiple workers in production, we recommend:

* Using a tool like Supervisor, [http://supervisord.org/](http://supervisord.org/), to launch multiple processes (and much more)
* Clustering software like Kubernetes, which also gives you support for scaling horizontally across multiple machines (depending on your cluster)

## No early acknowledgements

For durability purposes, task messages received from the Broker are only acknowledged after the task finishes (either successfully or with failure).

This means that, should the ``mognet ... run`` process crash (e.g., a ``SIGKILL``), the task can still be picked up by a different worker and retried. Note that
this isn't done forever; if a task is retried too many times (default is 3, as set in `max_retries` on [`AppConfig`][mognet.AppConfig]), the task is marked as ``FAILURE`` and discarded.

This, however, has the drawback where long-running tasks can run into issues with RabbitMQ-based task brokers, see [RabbitMQ Disconnects](./vendor-specifics/rabbitmq.md#rabbitmq-3816-and-long-running-tasks-can-cause-disconnects). One alternative to this is using [Stateful Tasks](./advanced/stateful-tasks.md).
