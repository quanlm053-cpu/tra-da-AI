"""Keep the local demo on the latest main revision using dedicated checkouts."""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
RUNTIME = HERE.parent / 'runtime/lending'
REPO = HERE.parents[1] / 'club-equipment-lending'
DEPLOYMENT=HERE.parents[1]/'deployment.local.json'
if DEPLOYMENT.exists():
    config=json.loads(DEPLOYMENT.read_text(encoding='utf-8-sig'))
    REPO=Path(config['repo_path'])
    if not REPO.is_absolute():REPO=(HERE.parents[1]/REPO).resolve()
RELEASES = RUNTIME / 'preview-releases'


def command(args, cwd):
    result = subprocess.run(args, cwd=cwd, capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace')[-2000:]
                           or result.stdout.decode('utf-8', errors='replace')[-2000:])
    return result.stdout.decode('utf-8', errors='replace').strip()


def prepare(revision):
    release = RELEASES / revision
    if not release.exists():
        command(['git', 'worktree', 'add', '--detach', str(release), revision], REPO)
    if not (release / '.preview-ready').exists():
        npm = shutil.which('npm.cmd') or shutil.which('npm')
        command([npm, 'ci', '--ignore-scripts', '--no-audit', '--no-fund'], release)
        driver = release / 'node_modules/msnodesqlv8'
        if (driver/'package.json').is_file() and not (driver / 'build/Release/sqlserver.node').exists():
            sources = [RUNTIME / 'story-166/node_modules/msnodesqlv8',
                       RUNTIME / 'story-116/node_modules/msnodesqlv8',
                       HERE.parent / 'runtime/lending/story-166/node_modules/msnodesqlv8']
            version = json.loads((driver / 'package.json').read_text())['version']
            source = next((p for p in sources if (p / 'build/Release/sqlserver.node').is_file()
                           and json.loads((p / 'package.json').read_text())['version'] == version), None)
            if source is None:
                command([npm, 'rebuild', 'msnodesqlv8'], release)
            else:
                (driver / 'build/Release').mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / 'build/Release/sqlserver.node', driver / 'build/Release/sqlserver.node')
        command([npm, 'run', 'build'], release)
        (release / '.preview-ready').write_text(revision)
    return release


def stop(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def launch(release, revision):
    if os.name == 'nt':
        service = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
             "(Get-Service -Name MSSQLSERVER -ErrorAction Stop).Status.ToString()"],
            capture_output=True, timeout=10)
        if service.returncode == 0 and service.stdout.decode(errors='replace').strip() != 'Running':
            raise RuntimeError(
                'SQL Server (MSSQLSERVER) đang dừng. Mở PowerShell bằng Run as administrator '
                'và chạy: Start-Service MSSQLSERVER. Preview sẽ tự thử lại sau 30 giây.')
    env = {**os.environ, 'SQLSERVER_DRIVER': 'odbc',
           'DATABASE_URL': 'Driver={ODBC Driver 17 for SQL Server};Server=lpc:localhost;'
                           'Database=ClubEquipmentLending_Preview;Trusted_Connection=yes;'
                           'Encrypt=yes;TrustServerCertificate=yes;'}
    log = (RUNTIME / 'preview-server.log').open('ab')
    try:
        process = subprocess.Popen([shutil.which('node'), str(HERE / 'preview.mjs'),
                                    str(release), revision], env=env, stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    finally:
        log.close()
    try:
        deadline = time.monotonic() + 30
        while process.poll() is None and time.monotonic() < deadline:
            try:
                with urlopen('http://localhost:3102/__preview_version', timeout=2) as response:
                    if json.load(response)['revision'] == revision:
                        return process
            except (OSError, ValueError, KeyError):
                pass
            time.sleep(.5)
        raise RuntimeError('Preview mới chưa khởi động được. Xem preview-server.log.')
    except BaseException:
        stop(process)
        raise


def main():
    RELEASES.mkdir(parents=True, exist_ok=True)
    process = None
    current = None
    release = None
    try:
        while True:
            try:
                command(['git', 'fetch', 'origin', 'main'], REPO)
                revision = command(['git', 'rev-parse', 'origin/main'], REPO)
                if current != revision or process is None or process.poll() is not None:
                    candidate = prepare(revision)
                    stop(process)
                    try:
                        process = launch(candidate, revision)
                    except Exception:
                        if current:
                            process = launch(release, current)
                        raise
                    release, current = candidate, revision
                    print('Preview updated: ' + revision, flush=True)
            except Exception as exc:
                print('Preview update: ' + str(exc), flush=True)
            time.sleep(30)
    finally:
        stop(process)


if __name__ == '__main__':
    main()
