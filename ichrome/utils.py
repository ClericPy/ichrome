import asyncio


class ForwardedConnection(asyncio.Protocol):

    def __init__(self, peer):
        self.peer = peer
        self.transport = None
        self.buff = []

    def connection_made(self, transport):
        self.transport = transport
        if self.buff:
            self.transport.writelines(self.buff)
            self.buff.clear()

    def data_received(self, data):
        self.peer.write(data)

    def connection_lost(self, e):
        if self.peer:
            self.peer.close()


class PortForwarder(asyncio.Protocol):

    def __init__(self, src, dst):
        self.src_host, self.src_port = src
        self.dst_host, self.dst_port = dst
        self.fc = None
        self.server = None

    async def __aenter__(self):
        self.server = await asyncio.get_running_loop().create_server(
            lambda: self, self.dst_host, self.dst_port)
        return self

    async def __aexit__(self, *_):
        self.close()

    def close(self):
        if self.fc:
            self.fc.peer.close()
        if self.server:
            self.server.close()

    async def connection_daemon(self):
        try:
            return await asyncio.get_running_loop().create_connection(
                lambda: self.fc, self.src_host, self.src_port)
        except Exception:
            return

    def connection_made(self, transport):
        self.transport = transport
        self.fc = ForwardedConnection(self.transport)
        asyncio.ensure_future(self.connection_daemon())

    def data_received(self, data):
        if self.fc.transport is None:
            self.fc.buff.append(data)
        else:
            self.fc.transport.write(data)

    def connection_lost(self, e):
        if self.fc.transport:
            self.fc.transport.close()
