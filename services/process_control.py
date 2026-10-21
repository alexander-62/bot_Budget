"""Non-destructive process checks and OS-owned single-instance locks."""

import errno
import os
from pathlib import Path


IS_WINDOWS = os.name == "nt"


def _windows_kernel32():
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if IS_WINDOWS:
        import ctypes

        kernel32 = _windows_kernel32()
        # SYNCHRONIZE is enough to observe termination, without sending signals.
        handle = kernel32.OpenProcess(0x00100000, False, pid)
        if not handle:
            # Access denied must not be mistaken for an absent process.
            return ctypes.get_last_error() == 5
        try:
            return kernel32.WaitForSingleObject(handle, 0) == 0x00000102  # WAIT_TIMEOUT
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except ProcessLookupError:
        return False


class AlreadyRunningError(RuntimeError):
    pass


class ProcessLock:
    """Lock a stable file; the OS releases the lock even after a crash/kill.

    Never delete lock files: replacing their inode can let two owners coexist.
    An unlocked file left on disk is normal and does not prevent a restart.
    """

    def __init__(self, path: Path):
        self.path = path
        self._file = None

    def acquire(self) -> bool:
        if self._file is not None:
            raise RuntimeError("This lock is already acquired")
        stream = self.path.open("a+b")
        try:
            if IS_WINDOWS:
                import msvcrt

                stream.seek(0, os.SEEK_END)
                if stream.tell() == 0:
                    stream.write(b"\0")
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            stream.close()
            if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                return False
            raise
        except BaseException:
            stream.close()
            raise
        self._file = stream
        return True

    def release(self) -> None:
        if self._file is not None:
            # Closing the sole handle releases both msvcrt and flock locks.
            self._file.close()
            self._file = None

    def __enter__(self):
        if not self.acquire():
            raise AlreadyRunningError(f"Lock is held: {self.path.name}")
        return self

    def __exit__(self, *args) -> None:
        self.release()


def is_lock_held(path: Path) -> bool:
    lock = ProcessLock(path)
    if not lock.acquire():
        return True
    lock.release()
    return False


def process_birth_identity(pid: int) -> str | None:
    """Non-secret process creation identity, stable across PID reuse."""
    if pid <= 0:
        return None
    if not IS_WINDOWS:
        try:
            # comm may contain spaces or parentheses; fields after its final )
            # begin with state (field 3), with starttime at field 22.
            fields = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()
            return f"{pid}:{fields[19]}"
        except (OSError, IndexError, ValueError):
            return None
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
        if not kernel32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)):
            return None
        return f"{pid}:{created.dwHighDateTime}:{created.dwLowDateTime}"
    finally:
        kernel32.CloseHandle(handle)


def recorded_process_identity(runtime_dir: Path, pid: int, profile_id: str) -> bool | None:
    """True/False for proven ownership/mismatch; None without usable evidence."""
    import json
    try:
        record = json.loads((runtime_dir / ".bot.identity.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return False
    if not isinstance(record, dict) or record.get("pid") != pid or record.get("profile_id") != profile_id or not record.get("birth"):
        return False
    current = process_birth_identity(pid)
    return current == record["birth"] if current is not None else None
