"""
This contains the tasks that are going to be run.
"""

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Set, List
from uuid import uuid4

from mognet import Context, Request, task

from mognet_demo.config import DemoConfig
from mognet_demo.models import Document, Upload, UploadResult
from mognet_demo.s3 import get_s3_client

_log = logging.getLogger(__name__)


# We define tasks using the @task decorator.
#
# This decorator requires us to set the name of the task,
# this identifies it across the entire Mognet application,
# and is used on the Request objects that are created and sent
# to the Broker, to run the task.
#
# A task function has one requirement: It must accept one argument, of type
# mognet.Context. This object allows for:
#
# - Introspection (of the current task, and of others)
# - Getting access to the Mognet app instance
# - Running subtasks, using context.run() and context.create_request()
# - Getting "services" (think of it as a poor man's Dependency Injection system),
#   using context.get_service()
#
# A task function can also have more arguments. They are parsed and validated using
# pydantic. In fact, if one were to create a request for a task which doesn't validate,
# the associated Result object will hold pydantic's ValidationError.
#
# The function's return value (or raised exception) is stored on the Result Backend,
# provided it is JSON-serializable. We recommend using pydantic models, as they
# serialize and deserialize from JSON transparently.
#
# Exceptions are serialized using pickle.
#
# Note that, if working with split code bases, the exception type (or return value type)
# must also exist on the codebase that reads the result value,
# if one is meant to interpret them. Otherwise, reading the result value,
# either by `await`ing the Result object, or calling `Result.get()`, will likely result
# in an ImportError, because the target type does not exist.
#
# For these cases, if code sharing is impossible, we recommend using bare types, such as dicts,
# to represent objects (much like what the `json` module does), and deserializing result values yourself,
# and only raising Exception classes from the Python Standard Library.
@task(name="mognet_demo.process_document_upload")
async def process_document_upload(context: Context, upload: Upload) -> UploadResult:
    """
    Process an upload.

    - If the upload is for a text file, the text is read and appended to the result.
    - If the upload is for an archive file, it is unpacked, and each file is processed separately
      (this uses recursion).
    - Otherwise, the upload is discarded.
    """

    config = DemoConfig.instance()

    documents: List[Document] = []
    errors: List[str] = []

    # Download the file from S3
    async with get_s3_client(config) as s3:
        obj = await s3.get_object(
            Bucket=config.s3.bucket_name,
            Key=f"uploads/{upload.upload_id}",
        )

        handle, file_name = tempfile.mkstemp(suffix=upload.file_name)

        async with obj["Body"] as body:
            with open(handle, "wb") as file_contents:
                file_contents.write(await body.read())

        file_name = Path(file_name)

        if file_name.suffix in _get_archive_extensions():
            # Unpack the archive and process each file separately.
            # Here we will see Mognet's recursion capabilities, where this task will
            # 'yield' to others it creates.

            tmp_dir = tempfile.mkdtemp()

            # shutil.unpack_archive() is a synchronous function,
            # one that would block the event loop if run directly.
            # This poses a performance penalty to the Mognet Worker,
            # because it can't handle other concurrent tasks, while this happens.
            #
            # So, one should use run_in_executor() to run this function.
            # See https://docs.python.org/3/library/asyncio-eventloop.html#executing-code-in-thread-or-process-pools
            #
            # Note that, if you block the event loop for long periods of time,
            # the task may get revoked, because the Broker disconnects the Worker
            # (the event loop is also used to send AMQP keep-alives).
            #
            # Mognet will print warnings to the console if it detects that
            # the event loop was blocked for long periods of time.
            await asyncio.get_event_loop().run_in_executor(
                None, shutil.unpack_archive, str(file_name), tmp_dir
            )

            subtasks: List[Request] = []

            for f in Path(tmp_dir).rglob("*"):
                # One could recurse into archives inside of archives...
                # Bear in mind that this should be done with caution in a real
                # production scenario, this is meant to illustrate Mognet's
                # recursion capabilities.

                if not f.is_file():
                    continue

                split_upload = Upload(upload_id=uuid4(), file_name=f.name)

                await s3.put_object(
                    Bucket=config.s3.bucket_name,
                    Key=f"uploads/{split_upload.upload_id}",
                    Body=f.read_bytes(),
                )

                # Here we create the Request object to run a subtask,
                # as part of this one.
                #
                # We can use the create_request() function as a shortcut,
                # which will also validate the arguments passed to it.
                subtasks.append(
                    context.create_request(process_document_upload, upload=split_upload)
                )

            # Here we wait for all the tasks that we created,
            # and aggregate the results.
            #
            # This is a poor-man's implementation, and does not do any
            # throttling to control how many tasks are at any given time
            # on the queue. Therefore, all tasks are sent at once to the broker.
            #
            # For that, one could use https://aiostream.readthedocs.io/en/latest/operators.html#aiostream.stream.map,
            # or one of the other primitives.
            #
            # as_completed() will return asyncio Future objects,
            # each representing the result of running the task.
            for subtask_result in asyncio.as_completed(
                [context.run(r) for r in subtasks]
            ):
                try:
                    result: UploadResult = await subtask_result
                    documents.extend(result.documents)
                    errors.extend(result.errors)
                except InvalidFile as exc:
                    errors.append(str(exc))

        elif file_name.suffix == ".txt":
            # Here we just read the file.
            doc = Document(
                upload_id=upload.upload_id,
                file_name=upload.file_name,
                contents=file_name.read_text("utf-8"),
            )

            documents.append(doc)
        else:
            # And here we raise an exception, for demonstration purposes.
            # Anyone awaiting this task's Result will get this exception object.
            raise InvalidFile(upload.file_name)

    return UploadResult(documents=documents, errors=errors)


def _get_archive_extensions() -> Set[str]:
    """Get a list of archive file extensions supported by shutil.unpack_archive()"""
    all_archive_extensions = set()

    for _format, extensions, _description in shutil.get_unpack_formats():
        all_archive_extensions.update(extensions)

    return all_archive_extensions


# A custom exception type.
#
# You can declare your own exception types,
# provided they call the super() constructor, as seen below.
# Otherwise, the exception value may not be properly serialized
# using pickle.
class InvalidFile(Exception):
    def __init__(self, file_name: str) -> None:
        super().__init__(file_name)
        self.file_name = file_name

    def __str__(self) -> str:
        return f"File is not a text file or an archive: {self.file_name!r}"
