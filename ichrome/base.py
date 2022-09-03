# -*- coding: utf-8 -*-
"""
Base utils and configs for ichrome
"""
import re
import time
from base64 import b64encode
from inspect import isawaitable
from pathlib import Path
from typing import List

import psutil
from torequests.utils import get_readable_size

from .exceptions import ChromeValueError
from .logs import logger

NotSet = ...
INF = float('inf')
CHROME_PROCESS_NAMES = {"chrome.exe", "chrome", "msedge.exe"}


class TagNotFound:
    "Same attributes like Tag, but return None"

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
        "get the attribute of the tag"
        return self.attributes.get(name, default)

    def to_dict(self):
        "convert Tag object to dict"
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


def get_proc_by_regex(regex, proc_names=None, host_regex=None):
    "find the procs with given proc_names and host_regex"
    proc_names = proc_names or CHROME_PROCESS_NAMES
    procs = []
    for _ in range(3):
        try:
            for proc in psutil.process_iter():
                if (not proc_names or proc.name() in proc_names):
                    cmd_string = ' '.join(proc.cmdline())
                    match_port = re.search(regex, cmd_string)
                    if match_port:
                        match_host = not host_regex or re.search(
                            host_regex, cmd_string)
                        if match_host:
                            procs.append(proc)
            return procs
        except (psutil.Error, OSError, TypeError, AttributeError):
            procs.clear()
    return procs


def get_proc(port=9222, proc_names=None, host=None) -> List[psutil.Process]:
    "find procs with given port and proc_names and host"
    regex = f"--remote-debugging-port={port or ''}"
    host_regex = f"--remote-debugging-address={host}" if host else None
    proc_names = proc_names or CHROME_PROCESS_NAMES
    return get_proc_by_regex(regex,
                             proc_names=proc_names,
                             host_regex=host_regex)


def get_memory_by_port(port=9222,
                       attr='uss',
                       unit='MB',
                       host=None,
                       proc_names=None):
    """get memory usage of chrome proc found with port and host.Only support local Daemon. `uss` is slower than `rss` but useful."""
    procs = get_proc(port=port, host=host, proc_names=proc_names)
    if procs:
        u = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3}
        if attr == 'uss':
            result = sum((proc.memory_full_info().uss for proc in procs))
        else:
            result = sum((getattr(proc.memory_info(), attr) for proc in procs))
        return result / u.get(unit, 1)


def clear_chrome_process(port=None,
                         timeout=None,
                         max_deaths=1,
                         interval=0.5,
                         host=None,
                         proc_names=None):
    """kill chrome processes, if port is not set, kill all chrome with --remote-debugging-port.
    set timeout to avoid running forever.
    set max_deaths and port, will return before timeout.
    """
    killed_count = 0
    start_time = time.time()
    if timeout is None:
        timeout = max_deaths or 2
    while 1:
        procs = get_proc(port, host=host, proc_names=proc_names)
        for proc in procs:
            try:
                logger.debug(
                    f"[Killing] {proc}, port: {port}. {' '.join(proc.cmdline())}"
                )
                proc.kill()
                try:
                    proc.wait(timeout)
                except psutil.TimeoutExpired:
                    pass
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
    "return the dir space usage of the given dir path"

    def get_st_size(f):
        try:
            return f.stat().st_size
        except FileNotFoundError:
            return 0

    result = 0
    target_path = Path(path)
    try:
        if not target_path.is_dir():
            return result
    except FileNotFoundError:
        pass
    try:
        for f in target_path.glob("**/*"):
            if f.is_file():
                result += get_st_size(f)
    except FileNotFoundError:
        pass
    return result


def get_readable_dir_size(path):
    "return the dir space usage of the given dir path with readable text."
    return get_readable_size(get_dir_size(path), rounded=1)


def install_chromium(path=None,
                     platform_name=None,
                     x64=True,
                     max_threads=5,
                     version=None):
    "download and unzip the portable chromium automatically"
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

    def show_versions():
        r = req.get('https://omahaproxy.appspot.com/all.json',
                    proxies={
                        'https': proxy,
                        'https': proxy
                    },
                    timeout=5)
        try:
            if r.x and r.ok:
                rj = r.json()
                result = {}
                for o in rj:
                    for v in o['versions']:
                        result[v['version']] = [
                            v['channel'],
                            v['branch_base_position'],
                            v['current_reldate'],
                        ]
                items = [[v[2], v[1], k, v[0]] for k, v in result.items()]
                items.sort(key=lambda i: i[-1], reverse=True)
                print('Current Versions:')
                head = ['date', 'version_code', 'version', 'channel']
                print(*head, sep='\t')
                for item in items:
                    print(*item, sep='\t')
        except Exception:
            import traceback
            traceback.print_exc()
            return

    # https://commondatastorage.googleapis.com/chromium-browser-snapshots/index.html
    # https://storage.googleapis.com/download/storage/v1/b/chromium-browser-snapshots/o/Linux_x64%2FLAST_CHANGE?alt=media
    # https://storage.googleapis.com/chromium-browser-snapshots/Linux_x64/798492/chrome-linux.zip
    welcome = 'Referer:\n  1. chromium build archives\n    https://commondatastorage.googleapis.com/chromium-browser-snapshots/index.html\n  2. latest releases\n    https://omahaproxy.appspot.com/\n    https://omahaproxy.appspot.com/all.json'
    print(welcome)
    req = tPool(max_threads)
    # os.environ['http_proxy'] = 'https://localhost:1080'
    proxy = os.getenv('HTTPS_PROXY') or os.getenv('https_proxy') or os.getenv(
        'http_proxy') or os.getenv('HTTP_PROXY')
    show_versions()
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
    os_prefix = f'{_platform_name}{_x64}'
    if not version:
        version_api = f'https://storage.googleapis.com/download/storage/v1/b/chromium-browser-snapshots/o/{os_prefix}%2FLAST_CHANGE?alt=media'
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
        version = r.text
    version = int(version)
    download_url = f'https://www.googleapis.com/download/storage/v1/b/chromium-browser-snapshots/o/{os_prefix}%2F{version}%2F{zip_file_name}.zip?alt=media'
    print('Downloading zip file from:', download_url)
    with BytesIO() as f:
        r = req.head(download_url,
                     retry=1,
                     proxies={
                         'https': proxy,
                         'https': proxy
                     })
        if r.status_code == 404:
            _prefix = f'{os_prefix}/{version-1}/'.encode('utf-8')
            pageToken = b64encode(b'\n\x0f' + _prefix).decode('utf-8')
            api = f'https://www.googleapis.com/storage/v1/b/chromium-browser-snapshots/o?delimiter=/&prefix={os_prefix}/&fields=items(kind,mediaLink,metadata,name,size,updated),kind,prefixes,nextPageToken&pageToken={pageToken}'
            r = req.get(api, retry=1, proxies={'https': proxy, 'https': proxy})
            _items = [re.search(r'.*/(\d+)/$', i) for i in r.json()['prefixes']]
            version_list = [int(i.group(1)) for i in _items if i]
            version_list.sort()
            nearby_versions = []
            for v in version_list:
                if len(nearby_versions) > 5:
                    break
                elif v > version:
                    nearby_versions.append(v)
            raise ValueError(
                f'Downloading failed {download_url}.\n{version} not found, maybe you can use a nearby version: {nearby_versions}?'
            )
        if not path:
            print('path is null, skip downloading')
            return
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
              install_folder_path.absolute().as_posix())
        return
    chrome_path = install_folder_path / chrome_runner_name
    if chrome_path.is_file():
        chrome_abs_path = chrome_path.absolute().as_posix()
        print('chrome_path:', chrome_abs_path)
        if _platform_name == 'Linux':
            print(f'chmod 755 {chrome_abs_path}')
            os.chmod(chrome_path, 755)
        print(f'check chromium version:\n{chrome_abs_path} --version')
        print('Install succeeded.')
    else:
        print('Mission failed.')


try:
    from asyncio import to_thread
except ImportError:
    from asyncio import get_running_loop
    from contextvars import copy_context
    from functools import partial

    async def to_thread(func, *args, **kwargs):
        """copy python3.9"""
        loop = get_running_loop()
        ctx = copy_context()
        func_call = partial(ctx.run, func, *args, **kwargs)
        return await loop.run_in_executor(None, func_call)


async_run = to_thread


async def ensure_awaitable(result):
    "avoid raising awaitable error while await something"
    if isawaitable(result):
        return await result
    else:
        return result
