"""Install a Colab train_run helper that preserves the actual child traceback.

Upload this file to Colab, run ``%run -i /content/colab_train_with_logs.py``,
then run the existing Train cell. Importing/running this helper does not train.
It does not change AMP, crop lengths, epochs, or the extracted dataset.
"""
import collections as _trainlog_collections
import datetime as _trainlog_datetime
import os as _trainlog_os
from pathlib import Path as _TrainLogPath
import shlex as _trainlog_shlex
import shutil as _trainlog_shutil
import signal as _trainlog_signal
import subprocess as _trainlog_subprocess
import sys as _trainlog_sys
import uuid as _trainlog_uuid


class TrainRunError(RuntimeError):
    """Training failure with the real exit code and an intact local log."""

    def __init__(self, message, *, returncode, log_path, command):
        super().__init__(message)
        self.returncode = returncode
        self.log_path = str(log_path)
        self.command = command


def _trainlog_stop_child(child):
    if child.poll() is not None:
        if _trainlog_os.name == "posix":
            try:
                _trainlog_os.killpg(child.pid, _trainlog_signal.SIGKILL)
            except ProcessLookupError:
                pass
        return

    def signal_child(sig):
        try:
            if _trainlog_os.name == "posix":
                _trainlog_os.killpg(child.pid, sig)
            elif sig == _trainlog_signal.SIGTERM:
                child.terminate()
            else:
                child.kill()
        except ProcessLookupError:
            pass

    signal_child(_trainlog_signal.SIGTERM)
    try:
        child.wait(timeout=5)
    except _trainlog_subprocess.TimeoutExpired:
        signal_child(_trainlog_signal.SIGKILL)
        child.wait(timeout=5)
    finally:
        # A DataLoader descendant may outlive the main child after SIGTERM.
        if _trainlog_os.name == "posix":
            signal_child(_trainlog_signal.SIGKILL)


def train_run(kind, directory, epochs, lr, patience):
    """Stream training output, save each attempt, and expose its actual error."""
    if kind not in ("lite", "pretrained"):
        raise ValueError("kind phải là lite hoặc pretrained")
    if "PROJECT" not in globals() or "MANIFEST" not in globals():
        raise RuntimeError("Chạy cell ghi module và Audit trước: thiếu PROJECT hoặc MANIFEST.")
    project = _TrainLogPath(globals()["PROJECT"]).expanduser().resolve()
    if not (project / "audio_sep" / "train.py").is_file():
        raise FileNotFoundError(f"Không tìm thấy {project / 'audio_sep' / 'train.py'}")
    manifest = _TrainLogPath(globals()["MANIFEST"]).expanduser()
    if not manifest.is_absolute():
        manifest = project / manifest
    if not manifest.is_file():
        raise FileNotFoundError(f"Chưa có manifest: {manifest}. Chạy cell Audit trước.")
    directory = _TrainLogPath(directory).expanduser()
    if not directory.is_absolute():
        directory = project / directory
    command = [_trainlog_sys.executable, "-u", "-m", "audio_sep.train", "--manifest", str(manifest),
               "--run-dir", str(directory), "--kind", kind, "--epochs", str(epochs),
               "--batch-size", "1", "--accumulate", "4", "--segment", str(globals().get("TRAIN_SEGMENT", 6.0)),
               "--train-crops", str(globals().get("TRAIN_CROPS", 32)),
               "--val-crops", str(globals().get("VAL_CROPS", 8)),
               "--workers", str(globals().get("TRAIN_WORKERS", 2)), "--lr", str(lr), "--patience", str(patience)]
    if globals().get("TRAIN_NO_AMP", False):
        command.append("--no-amp")
    if (directory / "last.pth").exists():
        command.append("--resume")
    logs = project / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stamp = _trainlog_datetime.datetime.now(_trainlog_datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    log_path = logs / f"train_{kind}_{stamp}_{_trainlog_uuid.uuid4().hex[:8]}.log"
    tail = _trainlog_collections.deque(maxlen=50)
    environment = _trainlog_os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    child = None
    returncode = None
    print(f"Python: {_trainlog_sys.version.split()[0]} | executable: {_trainlog_sys.executable}", flush=True)
    print(f"cwd: {project}\nLog: {log_path}\nCommand: {_trainlog_shlex.join(command)}", flush=True)
    try:
        with log_path.open("w", encoding="utf-8", buffering=1) as log:
            log.write(f"cwd: {project}\nCommand: {_trainlog_shlex.join(command)}\n")
            try:
                child = _trainlog_subprocess.Popen(
                    command, cwd=str(project), env=environment,
                    stdout=_trainlog_subprocess.PIPE, stderr=_trainlog_subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                    start_new_session=_trainlog_os.name == "posix",
                )
                for line in child.stdout:
                    tail.append(line.rstrip("\n"))
                    log.write(line)
                    log.flush()
                    print(line, end="", flush=True)
                returncode = child.wait()
                log.write(f"\nChild exit code: {returncode}\n")
            except KeyboardInterrupt:
                log.write("\nInterrupted: stopping training child and its process group.\n")
                if child is not None:
                    _trainlog_stop_child(child)
                raise
            except BaseException:
                if child is not None:
                    _trainlog_stop_child(child)
                raise
            finally:
                if child is not None and child.stdout is not None:
                    child.stdout.close()
    finally:
        # Drive can be full/disconnected; retain the local log in either case.
        try:
            drive_logs = directory / "logs"
            drive_logs.mkdir(parents=True, exist_ok=True)
            _trainlog_shutil.copy2(log_path, drive_logs / log_path.name)
        except OSError as error:
            print(f"Chưa copy được log vào run-dir: {error}. Log local vẫn ở {log_path}", flush=True)
    if returncode:
        details = "\n".join(tail) or "Không có output từ tiến trình con; xem file log."
        raise TrainRunError(f"Train dừng với exit code {returncode}. Log: {log_path}\n"
                            f"--- 50 dòng cuối của tiến trình train ---\n{details}",
                            returncode=returncode, log_path=log_path, command=command)
    print(f"Train hoàn tất. Log: {log_path}", flush=True)
    return log_path


print("Đã cài train_run có log. Chạy tiếp cell Train; helper này chưa bắt đầu train.", flush=True)
