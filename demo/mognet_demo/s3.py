"""
Simple communication to an S3 backend.
"""

from contextlib import asynccontextmanager

from aiobotocore.session import get_session
from botocore.exceptions import ClientError
from mognet_demo.config import DemoConfig


@asynccontextmanager
async def get_s3_client(config: DemoConfig):
    session = get_session()

    client_kwargs = dict(
        use_ssl=config.s3.ssl,
        verify=config.s3.verify,
        endpoint_url=config.s3.endpoint_url,
        aws_access_key_id=config.s3.aws_access_key_id,
        aws_secret_access_key=config.s3.aws_secret_access_key,
    )

    if config.s3.region:
        client_kwargs["region_name"] = config.s3.region

    _c = session.create_client(
        service_name="s3",
        **client_kwargs,
    )

    async with _c as client:
        await _ensure_bucket_exists(client)

        yield client


async def _ensure_bucket_exists(s3):
    config = DemoConfig.instance()

    try:
        await s3.head_bucket(
            Bucket=config.s3.bucket_name,
        )
    except ClientError:
        await s3.create_bucket(
            Bucket=config.s3.bucket_name,
        )
