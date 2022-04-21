# Overriding Queues

Sometimes you want to have different tasks routed to different queues. To do so, you can use the following properties on the [`AppConfig`][mognet.AppConfig] class:

- `task_routes`: This allows to set the queue name for each task. Tasks which are not set here default to the default queue name (`tasks`)
- `task_queues`: This allows you to only listen on a specific set of queues

Combining the two allows you to have workers that respond to a specific set of task types. This is useful in case you have tasks that require specific resources (such as GPUs, storage, CPU, etc.), or because you want these tasks to be processable even if other queues are busy.

## Setting the Default Task Queue Name

You can override the default task queue name (`tasks`) by setting the field `default_task_route` on the [`AppConfig`][mognet.AppConfig].
