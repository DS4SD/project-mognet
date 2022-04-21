# Metadata - Store Additional Information as Part of a Task

You can use metadata to store additional information on a [`Request`][mognet.Request] object. Mognet itself makes no use of it, but it can be used both by the tasks and by [Middleware](./middleware.md).

Metadata can be useful to store information like:

- Who was the User who launched the task
- Contextual information (e.g., in a multi-tenant application, the Tenant ID)
- Cross-system tracking information
- Storing task progress
- Etc.

Metadata is defined as a `dict[str, Any]`, and it is stored as JSON in the respective [`Result`][mognet.Result].

## Defining Metadata in a Request

To set metadata, you use the `metadata` field. As described before, this is a `dict[str, Any]`, so you can do it several ways:

```python
from mognet import App, Request

app = App(...)

# Approach 1: Create a Request object manually and set the metadata
# on the constructor
req1 = Request(
    ...,
    metadata={
        "user_id": "val",
    },
)

# Approach 2: Create a Request object, for example, 
# with the [`create_request()`][mognet.App.create_request] method,
# and set the metadata field afterwards
req2 = app.create_request(...)
req2.metadata["user_id"] = "cau"
```

Note that: 

- The values are serialized to JSON, so any specific type information is lost, so you need to re-read it yourself.
- You shouldn't store a lot of information in the metadata object, as it is then made part of the message sent to the Broker, and also copied to the [`Result`][mognet.Result]

## Getting Metadata in a Running Task

In case you need to get metadata in a running task, you can do so through the `context`, like this:

```python
from mognet import App, Context, task

app = App(...)

@task(name="demo.get_metadata")
def demo_get_metadata(context: Context):
    user_id = context.request.metadata["user_id"]

    print(f"This task was launched by @{user_id}")


async def main():
    req = app.create_request(demo_get_metadata)
    req.metadata["user_id"] = "dol"

    await app.run(req)
```

In this hypothetical example, the worker would print `This task was launched by @dol`.

## Setting Metadata in a Running Task

You can set the metadata in a running task by using the [`set_metadata()`][mognet.Context.set_metadata] method on the `context`:

```python
@task(name="demo.set_metadata")
async def demo_set_metadata(context: Context):
    await context.set_metadata(user_id="dkl")
```

Note that this method is asynchronous, because it is storing the values on the Result Backend (Redis). Also mind that the associated Request object does not get updated accordingly (it is anyway destroyed after the task completes).

## Getting Metadata Outside of a Task

To get metadata outside of a task, you get it's associated [`Result`][mognet.Result] and then call [`get_metadata()`][mognet.Result.get_metadata] on it:

```python
from uuid import UUID
from mognet import App

async def main():
    result_id = UUID(...)

    async with App(...) as app:
        res = await app.result_backend.get(result_id)

        assert res is not None

        metadata = await res.get_metadata()

        # Do what you need with it
```
