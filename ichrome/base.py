# -*- coding: utf-8 -*-
import re
import time
from pathlib import Path
from typing import List

import psutil
from torequests.utils import get_readable_size

from .logs import logger
"""
For base usage with sync utils.
"""


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
        except psutil.Error:
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
            logger.debug(
                f"[Killing] {proc}, port: {port}. {' '.join(proc.cmdline())}")
            try:
                proc.kill()
            except psutil._exceptions.NoSuchProcess:
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
    return sum(f.stat().st_size for f in Path(path).glob("**/*") if f.is_file())


def get_readable_dir_size(path):
    return get_readable_size(get_dir_size(path), rounded=1)
