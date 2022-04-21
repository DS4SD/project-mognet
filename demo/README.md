# Mognet Demo

This is a demo application for [Mognet](https://github.ibm.com/CognitiveCore-Utilities/project-mognet). It consists of a REST API, implemented with [FastAPI](https://fastapi.tiangolo.com/), that receives files to process, and a Mognet backend, that will process the files.

## Installing

### Requirements

You will need a few things to run this demo:

- An S3 bucket
- A Redis database
- An AMQP broker
- Optionally, [Poetry](https://python-poetry.org/)

If you have Docker, and Docker Compose, you can use the provided [docker-compose.yaml](./docker-compose.yaml) file to run a small example, that you can use for running the demo. It will set you up with:

- A MinIO instance running on port 9000 (console on port 9010)
  - Credentials: `ACCESS` / `SuperS3cret`
- A Redis on port 6379
  - Credentials: none
- A RabbitMQ on port 5672 (management UI on port 15672)
  - Credentials: `guest` / `guest`

You can launch them with:

```bash
docker-compose up -d
```

And you can stop them with:

```bash
docker-compose down  # Or, docker-compose stop
```

### Python Dependencies

To install the dependencies, either:

- If you have Poetry, run `poetry install`
- Otherwise, a `requirements.txt` has been generated for you that includes all necessary dependencies. We still recommend using a Python Virtual Environment beforehand (run `python -m venv venv`).

## Running This

After installing the dependencies, and having the required backend components running, open two terminals.

On one, you will launch the API, with:

```
uvicorn mognet_demo.api:app
```

On the other, you will launch the Mognet Worker, with:

```
mognet mognet_demo.mognet_app:app run
```

## The Components

As said before, the app has two components. We recommend reading each component's files to learn more about them.

### The API

The files are saved into an S3 bucket, for temporary storage, and tasks are sent to a Mognet worker to have them processed on the background.

The API is implemented as a single file, [api.py](./mognet_demo/api.py). We decided to keep everything together here, since going into the details of FastAPI is beyond the scope of this demo.

The API has 3 endpoints:

1. `POST /jobs`: this is used to upload a document, and start a background job to process it. You get an object with a `job_id`, which you can use to track it's status.
2. `GET /jobs/{job_id}`: this is used to check the status of a job. It will output an object containing the job's status, and the result, if available.
3. `POST /jobs/{job_id}/revoke`: this is used in case you want to revoke (abort) a job.

You can run the API with:

```bash
uvicorn mognet_demo.api:app
```

You can access the OpenAPI Documentation at [http://localhost:8000/docs](http://localhost:8000/docs).

### The Mognet Worker

The Mognet Worker receives the tasks, downloads the file, and, depending on the file type, it will:

- If it's a text (`.txt`) file, it's text contents are read
- If it's an archive file, it is unpacked, and each separate file is uploaded to S3. Then, the task will recurse to process each separate file.
- Otherwise, the task will raise an error indicating that the file was not valid.

The Mognet Worker is implemented as two files, [mognet_app.py](./mognet_demo/mognet_app.py) and [tasks.py](./mognet_demo/tasks.py). We chose to do this in two files to also demonstrate the ability to split an app into multiple files.

You can run the Mognet worker with:

```bash
mognet mognet_demo.mognet_app run
```

## The tests

Some tests for the Mognet worker and for the API have been implemented in the [test](./test/) folder. You can run them with pytest using:

```bash
pytest test/
```

## Running This With a Debugger

A [launch.json](./.vscode/launch.json) file has already been set up for you, with two targets:

- One, for the FastAPI server
- Other, for the Mognet Worker

To debug the Mognet Worker, you should debug the Python Module `mognet.cli.main`, the same arguments you use to run the demo app, i.e., `mognet_demo.mognet_app run`.
