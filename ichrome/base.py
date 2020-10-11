# -*- coding: utf-8 -*-
import re
import time
from asyncio import get_running_loop
from inspect import isawaitable
from pathlib import Path
from typing import Awaitable, List

import psutil
from torequests.utils import get_readable_size

from .exceptions import ChromeValueError
from .logs import logger
"""
For base usage with sync utils.
"""

NotSet = object()
INF = float('inf')


class TagNotFound:

    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        return None

    def get(self, name, default=None):
        return default

    def to_dict(self):
        return {}

    def __str__(self):
        return "Tag(None)"

    def __repr__(self):
        return self.__str__()

    def __bool__(self):
        return False


class Tag:
    """Handle the element's tagName, innerHTML, outerHTML, textContent, text, attributes, and the action result."""

    def __init__(self, tagName, innerHTML, outerHTML, textContent, attributes,
                 result):
        self.tagName = tagName.lower()
        self.innerHTML = innerHTML
        self.outerHTML = outerHTML
        self.textContent = textContent
        self.attributes = attributes
        self.result = result

        self.text = textContent

    def get(self, name, default=None):
        return self.attributes.get(name, default)

    def to_dict(self):
        return {
            "tagName": self.tagName,
            "innerHTML": self.innerHTML,
            "outerHTML": self.outerHTML,
            "textContent": self.textContent,
            "attributes": self.attributes,
            "result": self.result,
        }

    def __str__(self):
        return f"Tag({self.tagName})"

    def __repr__(self):
        return self.__str__()


def get_proc_by_regex(regex, proc_names=None):
    # win32 and linux chrome proc_names
    procs = []
    for proc in psutil.process_iter():
        try:
            if (not proc_names or proc.name() in proc_names) and re.search(
                    regex, ' '.join(proc.cmdline())):
                procs.append(proc)
        except (psutil.Error, OSError):
            pass
    return procs


def get_proc(port=9222) -> List[psutil.Process]:
    regex = f"--remote-debugging-port={port or ''}"
    proc_names = {"chrome.exe", "chrome"}
    return get_proc_by_regex(regex, proc_names=proc_names)


def get_memory_by_port(port=9222, attr='uss', unit='MB'):
    """Only support local Daemon. `uss` is slower than `rss` but useful."""
    procs = get_proc(port=port)
    if procs:
        u = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3}
        if attr == 'uss':
            result = sum((proc.memory_full_info().uss for proc in procs))
        else:
            result = sum((getattr(proc.memory_info(), attr) for proc in procs))
        return result / u.get(unit, 1)


def clear_chrome_process(port=None, timeout=None, max_deaths=1, interval=0.5):
    """kill chrome processes, if port is not set, kill all chrome with --remote-debugging-port.
    set timeout to avoid running forever.
    set max_deaths and port, will return before timeout.
    """
    killed_count = 0
    start_time = time.time()
    if timeout is None:
        timeout = max_deaths or 3
    while 1:
        procs = get_proc(port)
        for proc in procs:
            try:
                logger.debug(
                    f"[Killing] {proc}, port: {port}. {' '.join(proc.cmdline())}"
                )
                proc.kill()
            except (psutil.NoSuchProcess, ProcessLookupError):
                continue
        if port:
            if procs:
                killed_count += 1
            if killed_count >= max_deaths:
                return
        if max_deaths == 0:
            return
        if timeout and time.time() - start_time < timeout:
            time.sleep(interval)
            continue
        return


def get_dir_size(path):

    def get_st_size(f):
        try:
            return f.stat().st_size
        except FileNotFoundError:
            return 0

    target_path = Path(path)
    if not target_path.is_dir():
        return 0
    return sum(get_st_size(f) for f in target_path.glob("**/*") if f.is_file())


def get_readable_dir_size(path):
    return get_readable_size(get_dir_size(path), rounded=1)


def install_chromium(path, platform_name=None, x64=True, max_threads=5):
    import os
    import platform
    import time
    import zipfile
    from io import BytesIO
    from pathlib import Path

    from torequests import tPool
    from torequests.utils import get_readable_size

    def slice_content_length(total, chunk=1 * 1024 * 1024):
        start = 0
        end = 0
        while 1:
            end = start + chunk
            if end > total:
                yield (start, total)
                break
            yield (start, end)
            start += chunk + 1

    # https://commondatastorage.googleapis.com/chromium-browser-snapshots/index.html
    # https://storage.googleapis.com/download/storage/v1/b/chromium-browser-snapshots/o/Linux_x64%2FLAST_CHANGE?alt=media
    # https://storage.googleapis.com/chromium-browser-snapshots/Linux_x64/798492/chrome-linux.zip
    req = tPool(max_threads)
    # os.environ['http_proxy'] = 'https://localhost:1080'
    proxy = os.getenv('HTTPS_PROXY') or os.getenv('https_proxy') or os.getenv(
        'http_proxy') or os.getenv('HTTP_PROXY')
    platform_name = platform_name or platform.system()
    platform_map = {
        'Linux': ['Linux', '_x64' if x64 else '', 'chrome-linux', 'chrome'],
        'Windows': ['Win', '_x64' if x64 else '', 'chrome-win', 'chrome.exe'],
        'Darwin': ['Mac', '', 'chrome-mac', 'chrome.app'],
    }
    # alias names
    platform_map['Mac'] = platform_map['Darwin']
    platform_map['Win'] = platform_map['Windows']
    _platform_name, _x64, zip_file_name, chrome_runner_name = platform_map[
        platform_name]
    version_api = f'https://storage.googleapis.com/download/storage/v1/b/chromium-browser-snapshots/o/{_platform_name}{_x64}%2FLAST_CHANGE?alt=media'
    r = req.get(version_api,
                timeout=3,
                retry=1,
                proxies={
                    'https': proxy,
                    'https': proxy
                })
    if not r.text.isdigit():
        print(f'check your network connect to {version_api}')
        return
    download_url = f'https://www.googleapis.com/download/storage/v1/b/chromium-browser-snapshots/o/{_platform_name}{_x64}%2F{r.text}%2F{zip_file_name}.zip?alt=media'
    print('Downloading zip file from:', download_url)
    with BytesIO() as f:
        r = req.head(download_url,
                     retry=1,
                     proxies={
                         'https': proxy,
                         'https': proxy
                     })
        total = int(r.headers['Content-Length'])
        start_time = time.time()
        responses = [
            req.get(
                download_url,
                proxies={
                    'https': proxy,
                    'https': proxy
                },
                retry=3,
                headers={'Range': f'bytes={range_start}-{range_end}'},
            ) for range_start, range_end in slice_content_length(
                total, 1 * 1024 * 1024)
        ]
        total_mb = round(total / 1024 / 1024, 2)
        proc = 0
        for r in responses:
            if not r.ok:
                raise ChromeValueError(f'Bad request {r!r}')
            i = r.content
            f.write(i)
            proc += len(i)
            print(
                f'{round(proc / total * 100): >3}% | {round(proc / 1024 / 1024, 2)}mb / {total_mb}mb | {get_readable_size(proc/(time.time()-start_time+0.001), rounded=0)}/s'
            )
        print('Downloading is finished, will unzip it to:', path)
        zf = zipfile.ZipFile(f)
        zf.extractall(path)
    install_folder_path = Path(path) / zip_file_name
    if _platform_name == 'Mac' and install_folder_path.is_dir():
        print('Install succeeded, check your folder:',
              install_folder_path.absolute())
        return
    chrome_path = install_folder_path / chrome_runner_name
    if chrome_path.is_file():
        chrome_abs_path = chrome_path.absolute()
        print('chrome_path:', chrome_abs_path)
        if _platform_name == 'Linux':
            print(f'chmod 755 {chrome_abs_path}')
            os.chmod(chrome_path, 755)
        print(f'check chromium version:\n{chrome_abs_path} --version')
        print('Install succeeded.')
    else:
        print('Mission failed.')


def async_run(func, *args, **kwargs):

    def function():
        return func(*args, **kwargs)

    return get_running_loop().run_in_executor(None, function)


async def ensure_awaitable(result):
    if isawaitable(result):
        return await result
    else:
        return result
