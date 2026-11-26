"""Run registration browser checks on the host, outside the agent sandbox."""
import os
import shutil
import subprocess
import time
from pathlib import Path


def verify(office, cwd, runtime, story_id, minimum=12):
    office.check_stop()
    if cwd.resolve() != (runtime / f'story-{story_id}').resolve():
        raise RuntimeError('Kiểm thử trình duyệt cần checkout riêng của Story.')
    node = shutil.which('node')
    chrome = next((path for path in (
        Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe',
        Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe',
    ) if path.is_file()), None)
    if not node or not chrome:
        raise RuntimeError('Máy chưa có Node.js hoặc Chrome/Edge để chạy kiểm thử trình duyệt.')
    tools = runtime / 'browser-tools'
    if not (tools / 'node_modules/playwright-core/package.json').is_file():
        npm = shutil.which('npm.cmd') or shutil.which('npm')
        if not npm:
            raise RuntimeError('Thiếu npm để chuẩn bị bộ kiểm thử trình duyệt.')
        subprocess.run([npm, 'install', '--prefix', str(tools), '--no-audit', '--no-fund',
                        'playwright-core@1.65.1'], check=True, capture_output=True, timeout=120)
    fingerprint = office.fingerprint(cwd)
    output = runtime / f'{time.time_ns()}-story-{story_id}-browser'
    output.mkdir()
    log_path = output / 'browser.log'
    with log_path.open('wb') as log:
        process = subprocess.Popen(
            [node, str(Path(__file__).with_suffix('.cjs')), str(cwd), str(output), str(chrome), str(minimum)],
            cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
            env={**os.environ, 'SQLSERVER_DRIVER':'odbc',
                 'DATABASE_URL':'Driver={ODBC Driver 17 for SQL Server};Server=lpc:localhost;'
                                'Database=ClubEquipmentLending_Test;Trusted_Connection=yes;'
                                'Encrypt=yes;TrustServerCertificate=yes;'},
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
        try:
            deadline = time.monotonic() + 120
            while process.poll() is None:
                office.check_stop()
                if time.monotonic() > deadline:
                    raise TimeoutError('Bài kiểm thử trình duyệt trên máy quá thời gian.')
                time.sleep(.25)
        finally:
            from controller import Service
            Service.terminate(office, process)
    if office.fingerprint(cwd) != fingerprint:
        raise RuntimeError('Code thay đổi trong lúc kiểm thử trình duyệt.')
    return dict(passed=process.returncode == 0, fingerprint=fingerprint,
                log=str(log_path), screenshots=[str(p) for p in output.glob('*.png')],
                output=log_path.read_text(encoding='utf-8', errors='replace')[-5000:],
                scope='Registration UI, real backend and isolated SQL Server test schema with synthetic data.')
