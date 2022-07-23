"""
Here we see an example of how we can test Mognet tasks with
pytest.

On conftest.py, we created a fixture called 'mognet_app', which
we can use on our test functions.
"""
from pathlib import Path
from uuid import uuid4

import pytest
from mognet_demo.config import DemoConfig
from mognet_demo.models import Upload, UploadResult
from mognet_demo.s3 import get_s3_client
from mognet_demo.tasks import InvalidFile

from mognet import App, Request

_cwd = Path(__file__).parent


@pytest.mark.asyncio
async def test_document_upload(mognet_app: App, config: DemoConfig):
    """
    This is a test that does some basic checks of the task, namely
    if it reads the uploaded file properly.
    """

    upload = Upload(upload_id=uuid4(), file_name="test.txt")

    async with get_s3_client(config) as s3:
        with (_cwd / "text-file.txt") as file:
            contents = file.read_text("utf-8")

            await s3.put_object(
                Bucket=config.s3.bucket_name,
                Key=f"uploads/{upload.upload_id}",
                Body=contents,
            )

    # Here we do the "manual" version of submitting a task.
    # This is when we either don't want to import the respective function,
    # or we cannot, because it's part of a separate codebase.
    #
    # Unfortunately, since we don't have the task function,
    # the IDE and tools like Mypy won't help us here.
    req = Request(
        name="mognet_demo.process_document_upload",
        kwargs=dict(upload=upload),
    )

    # Here we run the Request object.
    # This will cause the Request to be submitted to the Broker,
    # and the Result to be awaited until it's done.
    # Result values are deserialized.
    result: UploadResult = await mognet_app.run(req)

    assert len(result.documents) == 1

    assert result.documents[0].contents == contents


@pytest.mark.asyncio
async def test_document_upload_non_text_file(mognet_app: App, config: DemoConfig):
    """
    This is largely the same test as before, it tests that the
    task rejects certain files.
    """

    upload = Upload(upload_id=uuid4(), file_name="test.json")

    async with get_s3_client(config) as s3:
        with (_cwd / "not-a-text-file.json") as file:
            await s3.put_object(
                Bucket=config.s3.bucket_name,
                Key=f"uploads/{upload.upload_id}",
                Body=file.read_bytes(),
            )

    req = Request(
        name="mognet_demo.process_document_upload",
        kwargs=dict(upload=upload),
    )

    with pytest.raises(InvalidFile) as raised:
        await mognet_app.run(req)

    assert raised.match("File is not a text file or an archive")


@pytest.mark.asyncio
async def test_document_upload_archive(mognet_app: App, config: DemoConfig):
    """
    This tests recursion behaviour, using a zip file.

    Here, errors from the subtasks are handled and put into the errors.
    The test file used has a single invalid .json file and 30 valid .txt files.
    """

    upload = Upload(upload_id=uuid4(), file_name="files.zip")

    async with get_s3_client(config) as s3:
        with (_cwd / "files.zip") as files:
            await s3.put_object(
                Bucket=config.s3.bucket_name,
                Key=f"uploads/{upload.upload_id}",
                Body=files.read_bytes(),
            )

    req = Request(
        name="mognet_demo.process_document_upload",
        kwargs=dict(upload=upload),
    )

    result: UploadResult = await mognet_app.run(req)

    # There are 30 valid text files
    # and one (invalid) json file
    assert len(result.documents) == 30

    # The error should've been handled
    assert len(result.errors) == 1
