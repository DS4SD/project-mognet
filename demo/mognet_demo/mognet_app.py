"""
The Mognet app.

It can be used both for submitting jobs and for launching the worker process via the CLI
"""

from mognet import App

from mognet_demo.config import DemoConfig
from mognet_demo.middleware.auto_shutdown import AutoShutdownMiddleware

_mognet_config = DemoConfig.instance().mognet

# The `imports` part of the configuration tells Mognet
# where to look for tasks.
_mognet_config.imports.append("mognet_demo.tasks")

app = App(name="mognet_demo", config=_mognet_config)

# Add some middleware to the Mognet Worker App.
# This one can be used to automatically shut down the Worker,
# which can be combined with auto-restart mechanisms (external to Mognet),
# such as Kubernetes Pod reboots, or supervisord.
#
# This is commented out by default, because it would break unit tests,
# but you can test it yourself by uncommenting this and booting the Mognet worker.
#
# app.add_middleware(AutoShutdownMiddleware(app))
