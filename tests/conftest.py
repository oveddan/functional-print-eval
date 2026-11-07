"""What the tests share across files: the code sandbox each sandbox test runs in."""
from functools import cache

import pytest

from pbe.runner import code_sandbox


def pytest_addoption(parser):
    parser.addoption("--all-sandboxes", action="store_true",
                     help="run each sandbox test in every sandbox (the Docker container too), "
                          "not only the one this machine's trials would use")


def pytest_generate_tests(metafunc):
    """By default a sandbox test runs once, in the sandbox `code_sandbox.find()` picks here, the one a
    trial would use: the container where Docker runs, else bubblewrap. With --all-sandboxes it runs
    in each one, skipped where one doesn't work."""
    if "sandbox" not in metafunc.fixturenames:
        return
    if metafunc.config.getoption("--all-sandboxes"):
        names = list(code_sandbox.SANDBOXES)
    else:
        box, _ = _sandbox_here()
        names = [box.name if box else "none"]
    metafunc.parametrize("sandbox", names, indirect=True)


@cache
def _sandbox_here():
    """(the sandbox find() picks, None) or (None, why there's none), probed once per process."""
    try:
        return code_sandbox.find(), None
    except code_sandbox.SandboxUnavailable as e:
        return None, str(e)


@pytest.fixture
def sandbox(request, monkeypatch):
    """The sandbox for this test, which `code_sandbox.find()` also returns while the test runs."""
    here, why_none = _sandbox_here()
    if request.param == "none":
        pytest.skip(why_none)
    if here is not None and here.name == request.param:
        box = here  # find() has already checked it works
    else:
        box = code_sandbox.SANDBOXES[request.param]()
        if problem := box.problem():
            pytest.skip(f"{request.param}: {problem}")
    monkeypatch.setattr(code_sandbox, "find", lambda: box)
    return box
