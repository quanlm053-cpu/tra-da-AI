"""Run the Lending integration suite against the isolated local test DB."""
import os
import shutil
import subprocess
import time
import re
from pathlib import Path


def verify(office, cwd, runtime, story_id):
    office.check_stop()
    expected = (runtime / f'story-{story_id}').resolve()
    if cwd.resolve() != expected:
        raise RuntimeError('Kiểm thử SQL Server cần checkout riêng của Story.')
    test = expected / 'backend/test/sqlserver.test.js'
    if not test.is_file() or not test.resolve().is_relative_to(expected):
        raise RuntimeError('Thiếu bài kiểm thử tích hợp SQL Server của Story.')
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Máy chạy kiểm thử SQL Server chưa có Node.js.')

    driver = expected / 'node_modules/msnodesqlv8'
    if not (driver / 'package.json').is_file():
        npm = shutil.which('npm.cmd') or shutil.which('npm')
        if not npm or not (expected / 'package-lock.json').is_file():
            raise RuntimeError('Thiếu npm hoặc lockfile để chuẩn bị driver SQL Server.')
        install = subprocess.run([npm,'ci','--ignore-scripts','--no-audit','--no-fund'],
                                 cwd=cwd, capture_output=True, timeout=90)
        office.check_stop()
        if install.returncode:
            raise RuntimeError('Không cài được dependency SQL Server từ lockfile.')
    binary = 'build/Release/sqlserver.node'
    if not (driver / binary).is_file():
        npm = shutil.which('npm.cmd') or shutil.which('npm')
        if not npm:raise RuntimeError('Thiếu npm để dựng driver SQL Server.')
        build=subprocess.run([npm,'rebuild','msnodesqlv8'],cwd=cwd,capture_output=True,timeout=180)
        if build.returncode or not (driver/binary).is_file():
            raise RuntimeError('Không dựng được msnodesqlv8. Cài ODBC Driver 17 và C++ Build Tools rồi thử lại.')

    fingerprint = office.fingerprint(cwd)
    env = {key: os.environ[key] for key in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA') if key in os.environ}
    database = office.project_config.get('test_database','ClubEquipmentLending_Test')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,100}',database):
        raise RuntimeError('Tên database kiểm thử không hợp lệ.')
    env.update(SQLSERVER_DRIVER='odbc', NODE_ENV='test', TEST_DATABASE_URL=(
        'Driver={ODBC Driver 17 for SQL Server};Server=lpc:localhost;'
        f'Database={database};Trusted_Connection=yes;'
        'Encrypt=yes;TrustServerCertificate=yes;'))
    log_path = runtime / f'{time.time_ns()}-story-{story_id}-sqlserver.log'
    with log_path.open('wb') as log:
        process = subprocess.Popen([node, '--test', str(test)], cwd=cwd, env=env,
                                   stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 120
        try:
            while process.poll() is None:
                office.check_stop()
                if time.monotonic() >= deadline:
                    raise RuntimeError('Bài kiểm thử SQL Server quá thời gian.')
                time.sleep(.25)
        finally:
            from controller import Service
            Service.terminate(office, process)
    if office.fingerprint(cwd) != fingerprint:
        raise RuntimeError('Code thay đổi trong lúc chạy kiểm thử SQL Server.')
    return {'passed':process.returncode == 0, 'fingerprint':fingerprint,
            'log':log_path.name, 'output':log_path.read_text(encoding='utf-8', errors='replace')[-5000:]}
