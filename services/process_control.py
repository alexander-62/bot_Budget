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
