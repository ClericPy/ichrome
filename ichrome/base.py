# -*- coding: utf-8 -*-
import time

import psutil

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


def get_proc(port):
    port_args = f"--remote-debugging-port={port}"
    # win32 and linux chrome proc_names
    proc_names = {"chrome.exe", "chrome"}
    procs = []
    for proc in psutil.process_iter():
        try:
            pname = proc.name()
            if pname in proc_names and port_args in ' '.join(proc.cmdline()):
                procs.append(proc)
        except Exception:
            pass
    return procs


def clear_chrome_process(port=None, timeout=None, max_deaths=1, interval=0.5):
    """kill chrome processes, if port is not set, kill all chrome with --remote-debugging-port.
    set timeout to avoid running forever.
    set max_deaths and port, will return before timeout.
    """
    port = port or ""
    killed_count = 0
    start_time = time.time()
    if timeout is None:
        timeout = max_deaths or 3
    while 1:
        procs = get_proc(port)
        for proc in procs:
            logger.debug(f"killing {proc}, port: {port}")
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
