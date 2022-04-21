"""
The API, responsible for receiving the files, submitting jobs, and getting their results.
"""

import asyncio
from contextlib import suppress
import os
from typing import Optional
from uuid import UUID, uuid4

from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Path,
    Query,
    Response,
    UploadFile,
)
from pydantic import confloat

from mognet_demo.config import DemoConfig
from mognet_demo.models import Job, Upload, UploadJobResult
from mognet_demo.mognet_app import app as mognet_app
from mognet_demo.s3 import get_s3_client
from mognet_demo.tasks import process_document_upload

app = FastAPI(
    title="Mognet Demo API",
    description='API to demonstrate how to use Mognet in a "real world" application.',
)


# We need to connect the Mognet application
# to the backends (Redis and RabbitMQ) before we can use it.
#
# Here we leverage FastAPI (or rather, Starlette)'s event system
# to do this.
@app.on_event("startup")
async def connect_mognet_app_on_startup():
    await mognet_app.connect()


# And for completeness, we close it here too.
@app.on_event("shutdown")
async def close_mognet_app_on_shutdown():
    await mognet_app.close()


@app.post("/jobs", response_model=Job)
async def upload_document(
    file: UploadFile = File(...),
    config: DemoConfig = Depends(DemoConfig.instance),
):
    """
    Upload a file to have it be processed in the background.

    This will return an object with a `job_id` which can be used to then get the result.
    """

    # Upload the file to S3
    upload = Upload(
        upload_id=uuid4(),
        file_name=os.path.basename(os.path.normpath(file.filename)),
    )

    async with get_s3_client(config) as s3:
        await s3.put_object(
            Bucket=config.s3.bucket_name,
            Key=f"uploads/{upload.upload_id}",
            Body=await file.read(),
        )

    # Here, we create a Request to run the task.
    # This will create an object holding:
    #
    # - It's ID
    # - The task to run
    # - The arguments
    #
    # It is possible to configure this object
    # with more parameters (check the mognet.Request class),
    # either through it's constructor or through it's fields.
    req = mognet_app.create_request(process_document_upload, upload=upload)

    # Here we _submit_ the Request to be run on the background.
    # This returns a Result object.
    # Each submitted Request has a corresponding Result on the Result Backend.
    # If one were to await `res`, then the caller would wait until the task finished
    # running, and the result would hold either the result, or it would raise an exception
    # (in case of failure).
    res = await mognet_app.submit(req)

    # Here, we return an object that can be used for client-side tracking.
    # We don't store this in a database, as that's beyond the scope of this demo.
    #
    # However, if you need to store this information (for auditing purposes),
    # you can create a database table / collection that holds information about each Request
    # that was submitted.
    return Job(job_id=res.id)


JobWaitTime = confloat(gt=0, le=30)


@app.get("/jobs/{job_id}/result", response_model=UploadJobResult)
async def get_job_result(
    job_id: UUID = Path(...),
    wait: Optional[JobWaitTime] = Query(
        None,
        description="**ADVANCED**: Optionally delay the return of this endpoint, in case the job isn't yet finished.",
    ),
) -> UploadJobResult:
    """
    Get the result of a job.

    This endpoint can be used to poll for the result of a job.

    A good way to see the `wait` parameter in action is to stop the Mognet Worker before launching a task (because they are very fast).
    """

    # To get the Result for a job, one should do so via the app's
    # `result_backend.get()` method. This will fetch the result from it.
    #
    # Note that there's no guarantee of the persistence of the Result Backend, assuming
    # you're using Redis (due to key eviction policies and TTLs).
    # By default, Mognet will keep results for 7 days.
    # See the mognet.AppConfig class for more details.
    #
    # Therefore, this method may return None, and we should handle it accordingly.
    res = await mognet_app.result_backend.get(job_id)

    if res is None:
        raise HTTPException(404, f"Job {job_id} not found")

    # **ADVANCED**: We can do a small optimization: instead of the client polling with high frequency,
    # we can instead delay the return of this endpoint for a few seconds, in case the job isn't done.
    # We can use the `wait()` function for this. This results in less HTTP traffic, at the expense of
    # more Redis traffic. You can use the poll argument to slow down the polling period (default is 0.1s, which
    # is optimized for performance-sensitive scenarios).
    #
    # Note that we must handle `asyncio.TimeoutError` ourselves, which happens if the job didn't finish
    # during the wait period.
    #
    # Bear in mind that this also has higher resource and timeout requirements for the server, because you are keeping
    # connections open for long periods of time. You should take care not to allow flooding of your server.
    if not res.done and wait is not None:
        with suppress(asyncio.TimeoutError):
            await res.wait(timeout=wait, poll=1)

    # We use a wrapper class that represents both the job and it's return value.
    # That way, it's easier to represent with OpenAPI schemas, and also easier
    # to handle for the client.
    if not res.done:
        return UploadJobResult(job_id=res.id, job_status=res.state, result=None)

    # If this is False, it means that the job's result holds an Exception.
    # We decide not to retrieve it here, and instead just tell the client that the job failed.
    if not res.successful:
        return UploadJobResult(job_id=res.id, job_status=res.state, result=None)

    # If we get here, the job finished successfully, so get the value
    # and return it to the client.
    value = await res.get()

    return UploadJobResult(job_id=res.id, job_status=res.state, result=value)


@app.post("/jobs/{job_id}/revoke", status_code=204, response_class=Response)
async def revoke_job(job_id: UUID = Path(...)):
    """Revoke (abort) a job, preventing it from running."""

    # Revoking a job is done via the `revoke()` method on the Mognet app.
    # It will do the following:
    #
    # - Mark the result as REVOKED on the Result Backend (Redis)
    # - Tell the Mognet Workers to cancel the running task, if any
    # - Do the same for the subtasks
    #
    # If a revoked task is received by a Worker, it is discarded. Likewise,
    # if a subtask of a revoked task is received, it is also revoked.
    #
    # If you call the `get_job_result` endpoint after calling this,
    # you will see that it is stored as REVOKED, unless it already finished.
    # You can pass `force=True` to this method if you really want to enforce it.
    await mognet_app.revoke(job_id)
