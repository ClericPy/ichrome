# import aiohttp
import websocket
from threading import Thread
from queue import Queue
import time


# # q = Queue()

# # def test(ws):
# #     while ws.connected:
# #         try:
# #             print(ws.recv())
# #         except websocket._exceptions.WebSocketConnectionClosedException:
# #             break
# #     print('stop')

# # url = "ws://localhost:9222/devtools/page/7F34509F1831E6F29351784861615D1C"
# # ws = websocket.WebSocket()
# # ws.connect(url)
# # t = Thread(target=test, args=[ws], daemon=1)
# # t.start()
# # ws.send('{"method": "Page.enable", "id": 1}')
# # ws.send('{"method": "Page.navigate", "params": {"url": "http://p.3.cn"}, "id": 2}')
# # ws.send('{"method": "Runtime.evaluate", "params": {"expression": "window.location.href"}, "id": 3}')
# # time.sleep(.1)
# # ws.close()
# import traceback

qq = Queue(1)
import traceback
qq.a = 32
print(qq.a)

try:
    qq.get(timeout=1)
except Exception as e:
    traceback.print_exc()
    print(e)