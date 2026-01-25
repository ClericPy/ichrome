# -*- coding: utf-8 -*-
from pathlib import Path


class DefaultConfig:
    port = 9222
    workers = 1
    chrome_path = ""
    host = "127.0.0.1"
    headless = False
    user_agent = ""
    proxy = ""
    user_data_dir = (Path.home() / "ichrome_user_data").as_posix()
    disable_image = False
    start_url = "about:blank"
    extra_config = ["--disable-gpu", "--no-first-run", "--window-size=1920,1080"]
    max_deaths = 1
    timeout = 3
    proc_check_interval = 5
    debug = False

    @classmethod
    def to_dict(cls):
        return {
            "port": cls.port,
            "workers": cls.workers,
            "chrome_path": cls.chrome_path,
            "host": cls.host,
            "headless": cls.headless,
            "user_agent": cls.user_agent,
            "proxy": cls.proxy,
            "user_data_dir": cls.user_data_dir,
            "disable_image": cls.disable_image,
            "start_url": cls.start_url,
            "extra_config": cls.extra_config,
            "max_deaths": cls.max_deaths,
            "timeout": cls.timeout,
            "proc_check_interval": cls.proc_check_interval,
            "debug": cls.debug,
        }
