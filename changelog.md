


---
- 0.1.3
    - update readme

- 0.1.2
    - set default host as 127.0.0.1 instead of  localhost, avoid some bad hosts file.
    - add default path for Darwin.

- 0.1.1
    - clear future while timeout

- 0.1.0
    - set default user data dir path to home

- 0.0.9
    - fix linux test

- 0.0.8
    - add more windows default chrome path

- 0.0.7
    - remove nonsense tab.get_html and tab.content, use tab.html instead.
    - fix action result of Tag object; add Tag.to_dict

- 0.0.6
    - fix tab.querySelectorAll should have return one item if index is not None

- 0.0.5
    - add action arg for tab.click and tab.querySelectorAll

- 0.0.4
    - add tab.querySelectorAll & Tab class to make crawler simple.
    - add ichrome.__tips__ for doc urls.

- 0.0.3
    - add Tab.inject_js method
    - add some default User-Agent
    - add command line usage for ChromeDaemon 
        - see more: `python -m ichrome -h`
