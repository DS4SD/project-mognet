import time
import requests
from pathlib import Path
from mognet_demo.models import Job, UploadJobResult
from mognet.model.result_state import READY_STATES, SUCCESS_STATES


_cwd = Path(__file__).parent


def test_full_a_to_z():
    """
    Test the "full A-Z", i.e., upload a file through the API, wait for the task,
    and get the result.
    """

    # 1. Upload the file.
    with (_cwd / "files.zip").open("rb") as files:
        submit_response = requests.post(
            "http://localhost:8000/jobs", files={"file": files}
        )

    assert submit_response.ok

    # 2. Get the job to wait for...
    job = Job.parse_obj(submit_response.json())

    # 3. Wait for it, through polling...
    while True:
        result_response = requests.get(
            f"http://localhost:8000/jobs/{job.job_id}/result?wait=10"
        )

        assert result_response.ok

        result = UploadJobResult.parse_obj(result_response.json())

        if result.job_status not in READY_STATES:
            time.sleep(1)

        break

    # 4 .And assert that it succeeds.
    assert result.job_status in SUCCESS_STATES

    assert result.result is not None

    assert len(result.result.documents) == 30
