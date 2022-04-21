## Contributing In General
Our project welcomes external contributions. If you have an itch, please feel
free to scratch it.

To contribute code or documentation, please submit a [pull request](https://github.com/IBM/project-mognet/pulls).

A good way to familiarize yourself with the codebase and contribution process is
to look for and tackle low-hanging fruit in the [issue tracker](https://github.com/IBM/project-mognet/issues).
Before embarking on a more ambitious contribution, please quickly [get in touch](#communication) with us.

For general questions or support requests, please refer to the [discussion section](https://github.com/IBM/project-mognet/discussions).

**Note: We appreciate your effort, and want to avoid a situation where a contribution
requires extensive rework (by you or by us), sits in backlog for a long time, or
cannot be accepted at all!**

### Proposing new features

If you would like to implement a new feature, please [raise an issue](https://github.com/IBM/project-mognet/issues)
before sending a pull request so the feature can be discussed. This is to avoid
you wasting your valuable time working on a feature that the project developers
are not interested in accepting into the code base.

### Fixing bugs

If you would like to fix a bug, please [raise an issue](https://github.com/IBM/project-mognet/issues) before sending a
pull request so it can be tracked.

### Merge approval

The project maintainers use LGTM (Looks Good To Me) in comments on the code
review to indicate acceptance. A change requires LGTMs from two of the
maintainers of each component affected.

For a list of the maintainers, see the [MAINTAINERS.md](MAINTAINERS.md) page.


## Legal

Each source file must include a license header for the MIT
Software. Using the SPDX format is the simplest approach.
e.g.

```
/*
Copyright IBM Inc. All rights reserved.

SPDX-License-Identifier: MIT
*/
```

We have tried to make it as easy as possible to make contributions. This
applies to how we handle the legal aspects of contribution. We use the
same approach - the [Developer's Certificate of Origin 1.1 (DCO)](https://github.com/hyperledger/fabric/blob/master/docs/source/DCO1.1.txt) - that the Linux® Kernel [community](https://elinux.org/Developer_Certificate_Of_Origin)
uses to manage code contributions.

We simply ask that when submitting a patch for review, the developer
must include a sign-off statement in the commit message.

Here is an example Signed-off-by line, which indicates that the
submitter accepts the DCO:

```
Signed-off-by: John Doe <john.doe@example.com>
```

You can include this automatically when you commit a change to your
local git repository using the following command:

```
git commit -s
```


## Communication

Please feel free to connect with us using the [discussion section](https://github.com/IBM/project-mognet/discussions).


## Setup

### Python and Poetry

We support Python 3.8 and above, and use [Poetry](https://python-poetry.org/) for dependency management.

We recommend creating the virtual environment like this:

```bash
poetry env use $(which python3.8)
```

To create an environment using Python 3.8.


### Requirements

- A Redis server
- A RabbitMQ server

Note: A default set up using Visual Studio Code Containers has already been set up for you, with the required dependencies.


## Testing

We use Pytest for running unit tests. To run the tests, do:

```
pytest test/
```

The tests are configured to point to the Redis and RabbitMQ configured in [docker-compose.yaml](.devcontainer/docker-compose.yaml). You may need to update them if you have a different setup.


## Coding style guidelines

We use the following tools to enforce code style:

- iSort, to sort imports
- Black, to format code
- Pylint, to lint code
- (TODO) Mypy

Please make sure to follow these tools's recommendations to help ensure good code quality.


## Documentation

We use [MkDocs](https://www.mkdocs.org/) to write documentation.

To run the documentation server, do:

```bash
mkdocs serve
```

The server will be available on [http://localhost:8000](http://localhost:8000).

### Pushing Documentation to GitHub pages

Run the following:

```bash
mkdocs gh-deploy
```
