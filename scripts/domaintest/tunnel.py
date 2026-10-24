"""Simulated "Iran server" for scripts/test-domain.sh (never used in production): a plain TCP
forwarder like Backhaul / GOST / a port forward. :443 → nginx:443 and :80 → nginx:80 as is;
:8443 → nginx:8843 with a PROXY protocol v1 header claiming client 198.51.100.9 (a tunnel
that sends PROXY protocol)."""
import asyncio
import socket

PROXY_CLIENT = "198.51.100.9"


async def pipe(r, w):
    try:
        while data := await r.read(65536):
            w.write(data)
            await w.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        try:
            w.close()
        except Exception:  # noqa: BLE001
            pass


def handler(target_port, proxy):
    async def handle(cr, cw):
        try:
            ur, uw = await asyncio.open_connection("nginx", target_port)
        except OSError:
            cw.close()
            return
        if proxy:
            peer, me = cw.get_extra_info("peername"), cw.get_extra_info("sockname")
            uw.write(f"PROXY TCP4 {PROXY_CLIENT} {socket.gethostbyname('nginx')} {peer[1]} {me[1]}\r\n".encode())
        await asyncio.gather(pipe(cr, uw), pipe(ur, cw))
    return handle


async def main():
    servers = [await asyncio.start_server(handler(443, False), "0.0.0.0", 443),
               await asyncio.start_server(handler(80, False), "0.0.0.0", 80),
               await asyncio.start_server(handler(8843, True), "0.0.0.0", 8443)]
    await asyncio.gather(*(s.serve_forever() for s in servers))


asyncio.run(main())
