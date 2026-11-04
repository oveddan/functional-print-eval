"""run_python: the model's code sees only its own folder and the installed libraries, and
whatever it does comes back as text, without ending the trial.

Each sandbox test runs in the sandbox a trial would use here (`conftest.sandbox`), and in
every sandbox with --all-sandboxes."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
import yaml

from pbe.runner import agent, code_sandbox, python_tool, tasks
from pbe.runner.code_sandbox import Limits
from pbe.runner.python_tool import PythonTool

ROOT = Path(__file__).resolve().parents[1]
HIDDEN = ROOT / "tasks/m5-spacer/hidden_facts.yaml"


@pytest.fixture
def tool(sandbox, tmp_path):
    workdir = tmp_path / "work"
    workdir.mkdir()
    return PythonTool(sandbox, workdir, Limits(timeout_s=60))


def test_it_cannot_read_a_hidden_file(tool):
    secret = HIDDEN.read_text().splitlines()[-1].strip()
    assert secret and secret in HIDDEN.read_text()  # a line that would show the file was read
    reply = tool.run(f"print(open({str(HIDDEN)!r}).read())")
    assert "FileNotFoundError" in reply and secret not in reply


def test_it_cannot_read_this_repository(tool):
    # the repository isn't mounted, so no file in it is there: a task's answer, the eval's code, a saved run
    paths = ["tasks/m5-spacer/reference.yaml", "pbe/runner/agent.py", "results/runs/pilot-spacer/summary.csv"]
    assert all((ROOT / path).exists() for path in paths)
    reply = tool.run("import os\n" + "\n".join(
        f"print(os.path.exists({str(ROOT / path)!r}), os.path.exists('../' * 12 + {path!r}))" for path in paths))
    assert reply.count("False False") == len(paths), reply


def files_in_home(limit=40):
    """Up to `limit` of this user's own files near the top of their home folder, with their hashes,
    leaving out the Python install (bwrap mounts that, read-only, at its own path)."""
    python_install = Path(sys.base_prefix).resolve()
    home = Path.home()
    found = {}
    for here, folders, names in os.walk(home):
        here = Path(here)
        near_top = len(here.relative_to(home).parts) < 2
        folders[:] = [folder for folder in folders
                      if near_top and not python_install.is_relative_to((here / folder).resolve())]
        for name in names:
            path = here / name
            if len(found) < limit and _small_ordinary_file(path):
                found[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def _small_ordinary_file(path):
    """Not a link, readable, and between 1 byte and 1 MB: an empty file's hash would match one in the sandbox."""
    try:
        return path.is_file() and not path.is_symlink() and 0 < path.stat().st_size < 2**20 and os.access(path, os.R_OK)
    except OSError:
        return False


def test_it_cannot_read_outside_its_folder(tool, tmp_path):
    beside = tmp_path / "beside.txt"  # next to the working folder, on the host
    beside.write_text("not for the model")
    reply = tool.run(f"import os\nprint(os.path.exists({str(beside)!r}), os.path.exists('../beside.txt'))")
    assert "False False" in reply and "not for the model" not in reply


def test_it_cannot_read_the_users_home_folder(tool):
    home = files_in_home()
    assert home  # on this machine there's something to hide
    reply = tool.run(f"""
import hashlib
for path in {sorted(home)!r}:
    try:
        print(hashlib.sha256(open(path, "rb").read()).hexdigest())
    except OSError:
        pass
""")
    assert not set(home.values()) & set(reply.split()), "a file from the home folder was readable"


def test_it_can_import_pbe_never(tool):
    reply = tool.run("import pbe")
    assert "ModuleNotFoundError" in reply  # so it can't run a check or read one


def test_it_cannot_reach_the_network(tool):
    reply = tool.run("""
import socket
for attempt in (lambda: socket.getaddrinfo("example.com", 443), lambda: socket.create_connection(("1.1.1.1", 443), timeout=3)):
    try:
        attempt()
        print("reached")
    except OSError as e:
        print("refused", type(e).__name__)
""")
    assert "reached" not in reply and reply.count("refused") == 2, reply


def test_it_sees_no_environment_from_this_process(tool, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sentinel-not-a-key")
    monkeypatch.setenv("HTTPS_PROXY", "http://sentinel-proxy:1")
    reply = tool.run("import os, json\nprint(json.dumps(dict(os.environ)))")
    seen = json.loads(reply.split("stdout:\n")[1].splitlines()[0])
    assert "sentinel" not in reply
    assert set(seen) <= set(code_sandbox.ENVIRONMENT) | {"PWD"}, seen  # bwrap sets PWD


def test_it_can_write_only_its_own_folder(tool):
    reply = tool.run("""
for path in ("/usr/x", "/etc/x", "/x"):
    try:
        open(path, "w")
        print("wrote", path)
    except OSError as e:
        print("refused", type(e).__name__)
open("mine.txt", "w").write("ok")
""")
    assert "wrote" not in reply and reply.count("refused") == 3
    assert (tool.workdir / "mine.txt").read_text() == "ok"
    assert "Files written: mine.txt" in reply


def test_a_crash_comes_back_as_text(tool):
    reply = tool.run("def f():\n    raise ValueError('boom')\nf()")
    assert "Exit code 1" in reply and "ValueError: boom" in reply and 'line 2, in f' in reply
    assert "wrapper" not in reply and "exec(compile" not in reply  # only the model's own frames


def test_it_cannot_start_another_process(tool):
    reply = tool.run("import subprocess\nsubprocess.run(['true'])")
    assert "PermissionError" in reply and "isn't allowed" in reply


def test_a_fork_bomb_through_ctypes_is_bounded(sandbox, tmp_path):
    # ctypes calls libc's fork directly, past the audit hook, so the kernel has to stop it:
    # the container's --pids-limit caps how many, and under bwrap seccomp refuses every one
    tool = PythonTool(sandbox, tmp_path, Limits(processes=32))
    reply = tool.run("""
import ctypes, os, time
libc = ctypes.CDLL(None, use_errno=True)
started = 0
for _ in range(1000):
    pid = libc.fork()
    if pid == 0:
        time.sleep(30)  # stays alive, so each one counts against the cap
        os._exit(0)
    started += pid > 0
print("started", started)
""")
    started = int(reply.split("started ")[1].split()[0])
    assert started <= 32, reply
    if isinstance(sandbox, code_sandbox.Bubblewrap):
        assert started == 0, reply  # one process only, so RLIMIT_AS caps its memory in all


def test_memory_is_capped_in_all(sandbox, tmp_path):
    tool = PythonTool(sandbox, tmp_path, Limits(memory_mb=1024))
    reply = tool.run("""
try:
    hog = bytearray(2 * 2**30)
    print("allocated")
except MemoryError:
    print("refused")
""")
    assert "allocated" not in reply, reply


def test_a_thread_bomb_is_bounded(sandbox, tmp_path):
    tool = PythonTool(sandbox, tmp_path, Limits(processes=32))
    reply = tool.run("""
import threading
threading.stack_size(64 * 1024)
started = 0
try:
    for _ in range(5000):
        threading.Thread(target=threading.Event().wait, daemon=True).start()
        started += 1
except RuntimeError as error:
    print("refused:", error)
print("started", started)
""")
    started = int(reply.split("started ")[1].split()[0])
    assert started <= 32 and "refused" in reply, reply


def test_threads_still_work(tool):
    reply = tool.run("""
import threading
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(8) as pool:
    print("sum", sum(pool.map(lambda n: n * n, range(100))))
""")
    assert "sum 328350" in reply, reply


def test_a_timeout_is_enforced(sandbox, tmp_path, monkeypatch):
    monkeypatch.setattr(code_sandbox.uuid, "uuid4", lambda: uuid.UUID("feedface" + "0" * 24))  # its container's name
    tool = PythonTool(sandbox, tmp_path, Limits(timeout_s=3))
    t0 = time.monotonic()
    reply = tool.run("print('started', flush=True)\nwhile True:\n    pass")
    assert time.monotonic() - t0 < 30
    assert "Stopped: it ran longer than 3 s" in reply and "started" in reply
    if isinstance(sandbox, code_sandbox.Container):  # killing the docker client alone would leave it running
        running = subprocess.run([sandbox.engine, "ps", "--all", "-q", "--filter", "name=pbe-run-python-feedface"], capture_output=True, text=True)
        assert running.stdout.strip() == ""


def test_a_file_cannot_fill_the_disk(sandbox, tmp_path):
    tool = PythonTool(sandbox, tmp_path, Limits(file_mb=1))
    reply = tool.run("open('big.bin', 'wb').write(b'x' * 3 * 2**20)")
    assert "File too large" in reply and (tmp_path / "big.bin").stat().st_size <= 2**20


def test_many_files_cannot_fill_the_disk(sandbox, tmp_path):
    # each file is under the per-file limit; together they pass the folder's
    tool = PythonTool(sandbox, tmp_path, Limits(file_mb=1, workspace_mb=4, timeout_s=60))
    t0 = time.monotonic()
    reply = tool.run("i = 0\nwhile True:\n    open(f'f{i}.bin', 'wb').write(b'x' * 2**19)\n    i += 1")
    assert time.monotonic() - t0 < 30
    assert "Stopped: its folder passed 4 MB" in reply, reply


PREALLOCATE = """
import ctypes, os
libc = ctypes.CDLL(None, use_errno=True)
libc.fallocate.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_long, ctypes.c_long]
FALLOC_FL_KEEP_SIZE = 1
i = 0
while True:
    fd = os.open(f"p{i}.bin", os.O_CREAT | os.O_WRONLY)
    if libc.fallocate(fd, FALLOC_FL_KEEP_SIZE, 0, 2**19) != 0:
        print("fallocate unsupported", ctypes.get_errno())
        break
    os.close(fd)
    i += 1
"""


def test_space_held_without_size_counts_toward_the_folder(sandbox, tmp_path):
    """fallocate with FALLOC_FL_KEEP_SIZE holds disk blocks while each file's size stays 0
    (Codex's review of PR 21): the folder's cap counts the blocks. The file cap is low so that, if
    the blocks weren't counted, the test would stop at 25 MB instead of filling the disk."""
    tool = PythonTool(sandbox, tmp_path, Limits(file_mb=1, workspace_mb=4, workspace_files=50, timeout_s=60))
    reply = tool.run(PREALLOCATE)
    if "fallocate unsupported" in reply:
        pytest.skip(f"this filesystem can't preallocate: {reply}")
    assert "Stopped: its folder passed 4 MB" in reply, reply


def test_disk_use_is_the_larger_of_size_and_blocks():
    from types import SimpleNamespace
    assert code_sandbox._disk_use(SimpleNamespace(st_size=0, st_blocks=1024)) == 2**19
    assert code_sandbox._disk_use(SimpleNamespace(st_size=10**9, st_blocks=8)) == 10**9  # a sparse file


@pytest.mark.parametrize("make_one", ["os.mkdir(f'd{i}')", "os.symlink('.', f'l{i}')"], ids=["folders", "links"])
def test_folders_and_links_count_as_entries(sandbox, tmp_path, make_one):
    tool = PythonTool(sandbox, tmp_path, Limits(workspace_files=200, timeout_s=60))
    reply = tool.run(f"import os\ni = 0\nwhile True:\n    {make_one}\n    i += 1")
    assert "Stopped: its folder passed 200 files" in reply, reply


def test_a_folder_that_cannot_be_counted_stops_the_run(tmp_path, monkeypatch):
    # code running as a non-root host user could chmod 000 a subfolder, and os.walk skips what
    # it can't read; the count has to fail closed. As root nothing is unreadable, so fake the error
    def walk_that_hits_a_locked_folder(top, onerror=None, followlinks=False):
        onerror(PermissionError(13, "Permission denied", str(top / "locked")))
        yield str(top), [], []
    monkeypatch.setattr(code_sandbox.os, "walk", walk_that_hits_a_locked_folder)
    assert "couldn't be counted" in code_sandbox.folder_too_full(tmp_path, Limits())


def test_too_many_files_are_stopped(sandbox, tmp_path):
    tool = PythonTool(sandbox, tmp_path, Limits(workspace_files=200, timeout_s=60))
    reply = tool.run("i = 0\nwhile True:\n    open(f'f{i}', 'w').close()\n    i += 1")
    assert "Stopped: its folder passed 200 files" in reply, reply


def test_a_full_folder_runs_nothing_until_it_is_cleared(sandbox, tmp_path):
    tool = PythonTool(sandbox, tmp_path, Limits(workspace_files=3))
    for i in range(5):
        (tmp_path / f"f{i}").write_text("x")
    assert "passed 3 files" in tool.run("print('ran')") and "ran" not in tool.run("print('ran')")


def test_tmp_is_capped_under_bwrap(tmp_path):
    sandbox = code_sandbox.Bubblewrap()
    if problem := sandbox.problem():
        pytest.skip(f"bwrap: {problem}")
    tool = PythonTool(sandbox, tmp_path, Limits(file_mb=1024))
    reply = tool.run("open('/tmp/big', 'wb').write(b'x' * 600 * 2**20)")
    assert "No space left" in reply, reply


def test_all_calls_in_a_trial_share_one_code_time_budget(sandbox, tmp_path):
    # a reply can hold several run_python calls; each one mustn't get a fresh 120 s
    tool = PythonTool(sandbox, tmp_path, Limits(timeout_s=60, trial_s=4))
    t0 = time.monotonic()
    first = tool.run("import time\nprint('started', flush=True)\ntime.sleep(30)")
    second = tool.run("print('ran')")
    assert time.monotonic() - t0 < 20
    assert "Stopped" in first and "started" in first
    assert "Not run: this trial's 4 s of code time is used up" in second and "ran" not in second.split("\n", 1)[0]


def test_output_is_capped(tool):
    reply = tool.run("print('a' * 2_000_000)\nimport sys\nprint('b' * 2_000_000, file=sys.stderr)\nprint('the end', file=sys.stderr)")
    assert len(reply) < tool.limits.output_chars + 500
    assert "characters cut" in reply and "the end" in reply  # a traceback's end is kept


def test_opencv_cadquery_and_trimesh_import(tool):
    reply = tool.run("""
import cv2, numpy as np, trimesh, cadquery as cq
image = np.zeros((20, 20), np.uint8)
cv2.circle(image, (10, 10), 5, 255, -1)
cv2.imwrite("dot.png", image)
cq.exporters.export(cq.Workplane().box(10, 10, 2), "plate.stl")
print("volume", round(trimesh.load("plate.stl").volume))
print("dot", int(cv2.imread("dot.png", 0).sum() > 0))
""")
    assert "Exit code 0" in reply and "volume 200" in reply and "dot 1" in reply, reply
    assert "Files written: dot.png, plate.stl" in reply


def test_files_stay_for_the_next_call(tool):
    tool.run("open('note.txt', 'w').write('kept')")
    assert "kept" in tool.run("print(open('note.txt').read())")


def test_no_sandbox_means_no_code_even_with_pbe_no_sandbox(monkeypatch):
    monkeypatch.setenv("PBE_NO_SANDBOX", "1")
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(code_sandbox.SandboxUnavailable, match="PBE_NO_SANDBOX doesn't apply"):
        code_sandbox.find()
    with pytest.raises(code_sandbox.SandboxUnavailable):
        agent.run_trial(tasks.load("m5-spacer"), "fake", condition="can_run_code", chat=lambda *a, **k: pytest.fail("no call"))


def test_a_sandbox_named_but_broken_isnt_swapped_for_another(monkeypatch):
    monkeypatch.setenv("PBE_CODE_SANDBOX", "container")
    monkeypatch.setattr(code_sandbox.Container, "problem", lambda self: "broken on purpose")
    with pytest.raises(code_sandbox.SandboxUnavailable, match="broken on purpose"):
        code_sandbox.find()


def test_a_task_hands_its_provided_files_and_nothing_else(sandbox, tmp_path, monkeypatch):
    task_dir = tmp_path / "tasks/fake"
    (task_dir / "files").mkdir(parents=True)
    (task_dir / "files/datasheet.png").write_bytes(b"png")
    (task_dir / "hidden_facts.yaml").write_text("secret: 1")
    monkeypatch.setattr(python_tool, "ROOT", tmp_path)
    tool = PythonTool.for_trial("fake", tmp_path / "work")
    assert "Files you're given: datasheet.png" in tool.prompt_line()
    reply = tool.run("import os\nprint(sorted(os.listdir('.')), os.path.exists('../hidden_facts.yaml'))")
    assert "['datasheet.png'] False" in reply


# the runner, with a fake model

def tool_call(call_id, name, arguments):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def scripted(*turns):
    """A fake chat that answers with each turn's tool calls in order, and records the tools it was offered."""
    offered = []

    def chat(model, messages, tools=None, max_tokens=None):
        offered.append([t["function"]["name"] for t in tools])
        calls = turns[len(offered) - 1]
        return {"choices": [{"message": {"role": "assistant", "tool_calls": calls}}], "usage": {"cost": 0.001}}
    return chat, offered


def test_a_trial_runs_code_and_carries_on_after_a_crash(sandbox, tmp_path):
    task = tasks.load("m5-spacer")
    reference = yaml.safe_load(task.reference)
    del reference["task"]  # the runner fills it in
    chat, offered = scripted(
        [tool_call("a", "run_python", {"code": "import math\nprint(math.pi)\nraise RuntimeError('oops')"})],
        [tool_call("b", "run_python", {"code": f"print(open({str(HIDDEN)!r}).read())"})],
        [tool_call("c", "submit_design", reference)],
    )
    record, messages, sub = agent.run_trial(task, "fake", condition="can_run_code", max_turns=5, chat=chat, workdir=tmp_path / "work")
    assert sub is not None and record.outcome == "submitted" and record.turns == 3
    replies = [m["content"] for m in messages if m["role"] == "tool"]
    assert "3.14159" in replies[0] and "RuntimeError: oops" in replies[0]
    assert "FileNotFoundError" in replies[1]
    assert offered[0] == ["measure", "submit_design", "report_limitation", "run_python"]
    assert "run_python(code)" in messages[0]["content"] and "at most 5 turns" in messages[0]["content"]
    assert record.settings.max_turns == 5 and record.settings.run_python.sandbox == sandbox.describe()
    saved = record.as_saved()["settings"]["run_python"]
    assert saved == {"sandbox": sandbox.describe(), "timeout_s": 120, "trial_s": 1200, "output_chars": 8000}


@pytest.mark.parametrize("condition", ["can_ask", "all_given"])
def test_the_other_conditions_have_no_run_python(condition, monkeypatch):
    monkeypatch.setattr(code_sandbox, "find", lambda: pytest.fail("no sandbox needed"))
    chat, offered = scripted([tool_call("a", "run_python", {"code": "print(1)"})])
    record, messages, sub = agent.run_trial(tasks.load("m5-spacer"), "fake", condition=condition, max_turns=1, chat=chat)
    assert offered == [["measure", "submit_design", "report_limitation"]]
    assert messages[-1]["content"] == "There's no tool called run_python."
    assert "run_python" not in messages[0]["content"]
    assert "run_python" not in record.as_saved()["settings"]


def test_can_ask_has_the_same_prompt_as_the_saved_trials():
    saved = json.loads((ROOT / "results/runs/pilot-wheel/bearing-wheel/can_ask/openai__gpt-6.1-sol/t1/transcript.json").read_text())
    assert agent.system_prompt(8) == saved[0]["content"]


def test_only_can_run_code_gets_more_turns():
    assert agent.DEFAULT_MAX_TURNS == {"can_ask": 8, "all_given": 8, "can_run_code": 20, "can_ask_datasheet": 8}
