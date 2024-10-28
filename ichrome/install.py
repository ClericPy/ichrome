def install_chromium(
    path=None, platform_name=None, x64=True, max_threads=5, version=None
):
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
        r = req.get(
            "https://omahaproxy.appspot.com/all.json",
            proxies={"all": proxy},
            timeout=5,
        )
        try:
            if r.x and r.ok:
                rj = r.json()
                result = {}
                for o in rj:
                    for v in o["versions"]:
                        result[v["version"]] = [
                            v["channel"],
                            v["branch_base_position"],
                            v["current_reldate"],
                        ]
                items = [[v[2], v[1], k, v[0]] for k, v in result.items()]
                items.sort(key=lambda i: i[-1], reverse=True)
                print("Current Versions:")
                head = ["date", "version_code", "version", "channel"]
                print(*head, sep="\t")
                for item in items:
                    print(*item, sep="\t")
        except Exception:
            import traceback

            traceback.print_exc()
            return

    # https://commondatastorage.googleapis.com/chromium-browser-snapshots/index.html
    # https://storage.googleapis.com/download/storage/v1/b/chromium-browser-snapshots/o/Linux_x64%2FLAST_CHANGE?alt=media
    # https://storage.googleapis.com/chromium-browser-snapshots/Linux_x64/798492/chrome-linux.zip
    welcome = "Referer:\n  1. chromium build archives\n    https://commondatastorage.googleapis.com/chromium-browser-snapshots/index.html\n  2. latest releases\n    https://omahaproxy.appspot.com/\n    https://omahaproxy.appspot.com/all.json"
    print(welcome)
    req = tPool(max_threads)
    # os.environ['http_proxy'] = 'https://localhost:1080'
    proxy = (
        os.getenv("HTTPS_PROXY")
        or os.getenv("https_proxy")
        or os.getenv("http_proxy")
        or os.getenv("HTTP_PROXY")
    )
    show_versions()
    platform_name = platform_name or platform.system()
    platform_map = {
        "Linux": ["Linux", "_x64" if x64 else "", "chrome-linux", "chrome"],
        "Windows": ["Win", "_x64" if x64 else "", "chrome-win", "chrome.exe"],
        "Darwin": ["Mac", "", "chrome-mac", "chrome.app"],
    }
    # alias names
    platform_map["Mac"] = platform_map["Darwin"]
    platform_map["Win"] = platform_map["Windows"]
    _platform_name, _x64, zip_file_name, chrome_runner_name = platform_map[
        platform_name
    ]
    os_prefix = f"{_platform_name}{_x64}"
    if not version:
        version_api = f"https://storage.googleapis.com/download/storage/v1/b/chromium-browser-snapshots/o/{os_prefix}%2FLAST_CHANGE?alt=media"
        r = req.get(
            version_api, timeout=3, retry=1, proxies={"https": proxy, "https": proxy}
        )
        if not r.text.isdigit():
            print(f"check your network connect to {version_api}")
            return
        version = r.text
    version = int(version)
    download_url = f"https://www.googleapis.com/download/storage/v1/b/chromium-browser-snapshots/o/{os_prefix}%2F{version}%2F{zip_file_name}.zip?alt=media"
    print("Downloading zip file from:", download_url)
    with BytesIO() as f:
        r = req.head(download_url, retry=1, proxies={"https": proxy, "https": proxy})
        if r.status_code == 404:
            _prefix = f"{os_prefix}/{version-1}/".encode("utf-8")
            pageToken = b64encode(b"\n\x0f" + _prefix).decode("utf-8")
            api = f"https://www.googleapis.com/storage/v1/b/chromium-browser-snapshots/o?delimiter=/&prefix={os_prefix}/&fields=items(kind,mediaLink,metadata,name,size,updated),kind,prefixes,nextPageToken&pageToken={pageToken}"
            r = req.get(api, retry=1, proxies={"https": proxy, "https": proxy})
            _items = [re.search(r".*/(\d+)/$", i) for i in r.json()["prefixes"]]
            version_list = [int(i.group(1)) for i in _items if i]
            version_list.sort()
            nearby_versions = []
            for v in version_list:
                if len(nearby_versions) > 5:
                    break
                elif v > version:
                    nearby_versions.append(v)
            raise ValueError(
                f"Downloading failed {download_url}.\n{version} not found, maybe you can use a nearby version: {nearby_versions}?"
            )
        if not path:
            print("path is null, skip downloading")
            return
        total = int(r.headers["Content-Length"])
        start_time = time.time()
        responses = [
            req.get(
                download_url,
                proxies={"all": proxy},
                retry=3,
                headers={"Range": f"bytes={range_start}-{range_end}"},
            )
            for range_start, range_end in slice_content_length(total, 1 * 1024 * 1024)
        ]
        total_mb = round(total / 1024 / 1024, 2)
        proc = 0
        for r in responses:
            if not r.ok:
                raise ValueError(f"Bad request {r!r}")
            i = r.content
            f.write(i)
            proc += len(i)
            print(
                f"{round(proc / total * 100): >3}% | {round(proc / 1024 / 1024, 2)}mb / {total_mb}mb | {get_readable_size(proc/(time.time()-start_time+0.001), rounded=0)}/s"
            )
        print("Downloading is finished, will unzip it to:", path)
        zf = zipfile.ZipFile(f)
        zf.extractall(path)
    install_folder_path = Path(path) / zip_file_name
    if _platform_name == "Mac" and install_folder_path.is_dir():
        print(
            "Install succeeded, check your folder:",
            install_folder_path.absolute().as_posix(),
        )
        return
    chrome_path = install_folder_path / chrome_runner_name
    if chrome_path.is_file():
        chrome_abs_path = chrome_path.absolute().as_posix()
        print("chrome_path:", chrome_abs_path)
        if _platform_name == "Linux":
            print(f"chmod 755 {chrome_abs_path}")
            os.chmod(chrome_path, 755)
        print(f"check chromium version:\n{chrome_abs_path} --version")
        print("Install succeeded.")
    else:
        print("Mission failed.")
import platform

def get_system_architecture():
    return platform.machine()

print(get_system_architecture())
