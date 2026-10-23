"""Remember active workers across a code/dependency update; verify every restart."""
import json
import os
from pathlib import Path
import tempfile
import time

from services.bot_profiles import list_profiles
from services.desktop_status import read_health, read_int
from services.process_control import ProcessLock, is_direct_child, is_lock_held, is_process_running, recorded_process_identity

STATE_FILE = '.update-state.json'


def _write_state(path, state):
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.update-state-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(state, stream)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def wait_ready(profile, base_dir, host, expected_version, timeout=35):
    runtime = profile.runtime_dir(base_dir)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pid, port = read_int(runtime / '.bot.pid'), read_int(runtime / '.bot.port')
        if pid and not is_process_running(pid):
            raise RuntimeError(f'{profile.id}: процесс завершился; проверьте журнал профиля.')
        if pid and port:
            health = read_health(host, port)
            worker = health.get('pid')
            if (health.get('profile_id') == profile.id and health.get('version') == expected_version
                    and health.get('polling_ready') is True
                    and recorded_process_identity(runtime, pid, profile.id) is True
                    and isinstance(worker, int) and (worker == pid or is_direct_child(worker, pid))):
                return health
        time.sleep(.3)
    raise RuntimeError(f'{profile.id}: не подтверждён запуск версии {expected_version}; проверьте журнал профиля.')


def prepare(manager):
    base = manager.BASE_DIR
    path = base / STATE_FILE
    with ProcessLock(base / '.update.lock'):
        profiles = list_profiles(base_dir=base)
        active = []
        for profile in profiles:
            runtime = profile.runtime_dir(base)
            pid = read_int(runtime / '.bot.pid')
            if pid and is_process_running(pid):
                if recorded_process_identity(runtime, pid, profile.id) is not True:
                    raise RuntimeError(f'{profile.id}: принадлежность процесса не подтверждена; обновление отменено.')
                active.append(profile.id)
            elif (runtime / '.bot.lock').exists() and is_lock_held(runtime / '.bot.lock'):
                raise RuntimeError(f'{profile.id}: бот запускается без подтверждённого PID; повторите обновление позже.')
        if path.exists():
            state = json.loads(path.read_text(encoding='utf-8'))
            state['profiles'] = list(dict.fromkeys(state['profiles'] + active))
        else:
            state = {'profiles': active, 'panel': False, 'tray': False}
        panel_pid = read_int(manager.DESKTOP_PID_FILE)
        tray_pid = read_int(manager.TRAY_PID_FILE)
        panel_alive = bool(panel_pid and is_process_running(panel_pid))
        state['panel'] = state['panel'] or panel_alive
        state['tray'] = state['tray'] or bool(tray_pid and is_process_running(tray_pid))
        _write_state(path, state)
        print('Working profiles saved: ' + ', '.join(state['profiles']), flush=True)
        if panel_alive:
            manager.DESKTOP_SHOW_FILE.write_text('quit-for-update', encoding='utf-8')
            deadline = time.monotonic() + 10
            while is_process_running(panel_pid) and time.monotonic() < deadline:
                time.sleep(.2)
            if is_process_running(panel_pid):
                raise RuntimeError('Закройте панель кнопкой «Выйти из панели» и повторите обновление.')
        manager.stop_tray()
        for profile_id in state['profiles']:
            manager.configure_profile(profile_id)
            manager.stop_bot()
            if manager.EXIT_CODE:
                raise RuntimeError(f'{profile_id}: не удалось остановить бота; список восстановления сохранён.')
            # taskkill and SIGTERM may return before the runtime lock is released.
            lock_path = manager.BOT_LOCK_FILE
            deadline = time.monotonic() + 10
            while lock_path.exists() and is_lock_held(lock_path):
                if time.monotonic() >= deadline:
                    raise RuntimeError(f'{profile_id}: процесс ещё не завершился; обновление отменено.')
                time.sleep(.1)


def finish(manager):
    from version import __version__
    base = manager.BASE_DIR
    path = base / STATE_FILE
    with ProcessLock(base / '.update.lock'):
        if not path.exists():
            print('No pending update to restore.', flush=True)
            return
        state = json.loads(path.read_text(encoding='utf-8'))
        profiles = {profile.id: profile for profile in list_profiles(base_dir=base)}
        errors = []
        for profile_id in state['profiles']:
            try:
                if profile_id not in profiles:
                    raise RuntimeError(f'{profile_id}: профиль отсутствует в реестре.')
                manager.EXIT_CODE = 0
                manager.configure_profile(profile_id)
                manager.start_bot(background=True)
                if manager.EXIT_CODE:
                    raise RuntimeError(f'{profile_id}: команда запуска завершилась с ошибкой.')
                health = wait_ready(profiles[profile_id], base, manager.WEBAPP_HOST, __version__)
                print(f'{profile_id}: ready, version {health["version"]}', flush=True)
            except Exception as error:
                # Only app-authored exceptions leave the operation; no HTTP/key text.
                errors.append(profile_id)
                print(f'{profile_id}: запуск не подтверждён. Проверьте журнал профиля.', flush=True)
        manager.EXIT_CODE = 0
        if state['panel']:
            manager.start_desktop()
        elif state['tray']:
            manager.start_tray()
        if manager.EXIT_CODE:
            errors.append('panel/tray')
        if errors:
            raise RuntimeError('Не все профили запущены: ' + ', '.join(errors) + '. Список восстановления сохранён; повторите finish-update.')
        path.unlink()
