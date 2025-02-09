# -*- coding: utf-8 -*-
"""
Base utils and configs for ichrome
"""

import re
import time
from inspect import isawaitable
from pathlib import Path
from typing import List

import psutil
from morebuiltins.utils import read_size

from .logs import logger

NotSet = ...
INF = float("inf")
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

    def __init__(self, tagName, innerHTML, outerHTML, textContent, attributes, result):
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
                if not proc_names or proc.name() in proc_names:
                    cmd_string = " ".join(proc.cmdline())
                    match_port = re.search(regex, cmd_string)
                    if match_port:
                        match_host = not host_regex or re.search(host_regex, cmd_string)
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
    return get_proc_by_regex(regex, proc_names=proc_names, host_regex=host_regex)


def get_memory_by_port(port=9222, attr="uss", unit="MB", host=None, proc_names=None):
    """get memory usage of chrome proc found with port and host.Only support local Daemon. `uss` is slower than `rss` but useful."""
    procs = get_proc(port=port, host=host, proc_names=proc_names)
    if procs:
        u = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
        if attr == "uss":
            result = sum((proc.memory_full_info().uss for proc in procs))
        else:
            result = sum((getattr(proc.memory_info(), attr) for proc in procs))
        return result / u.get(unit, 1)
    else:
        return 0


def clear_chrome_process(
    port=None, timeout=None, max_deaths=1, interval=0.5, host=None, proc_names=None
):
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
    return read_size(get_dir_size(path), rounded=1)


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


def kill_pid(pid: int):
    proc = psutil.Process(pid)
    try:
        proc.kill()
        try:
            return proc.wait(0.1)
        except psutil.TimeoutExpired:
            pass
    except (psutil.NoSuchProcess, ProcessLookupError):
        pass
