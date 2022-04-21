from typing import TypedDict

from mognet import App


class CliState(TypedDict):
    app_instance: App


state = CliState(app_instance=None)  # type: ignore
