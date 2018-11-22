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


def test():
    start_time = time.time()
    while time.time()- start_time< 2:
        # time.sleep(1)
        result = yield "还没有"
        
        print('result:', result)
        if result:
            time.sleep(1)
            return result
    print('超时了')
    return


g = test()
# print(next(g))
g.send(None)

# g.send('ssdf')
for i in g:
    # time.sleep(1)
    print(i)
#     try:
#         print(next(g))
#     except StopIteration:
#         break
#     if i > 1:
#         try:
#             print(g.send('有了'), 1111)
#         except StopIteration as e:
#             print(1222, e.value)
# # print(next(g))
# print(next(g))
# print(next(g))
# print(next(g))
# print(next(g))
