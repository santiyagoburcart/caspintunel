"""
Host network facts for the monitoring page.

The host's /proc is bind-mounted read-only at /hostproc; PID 1 lives in the host
network namespace, so /hostproc/1/net/* reflects the *server*, not this
container. Everything degrades gracefully to the container's own /proc/net when
the mount is missing (dev without the mount, restricted kernels).
"""
from __future__ import annotations

import os
import socket
import struct

HOSTNET = "/hostproc/1/net" if os.path.isdir("/hostproc/1/net") else "/proc/net"


def _read(name: str) -> str:
    try:
        with open(f"{HOSTNET}/{name}", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def default_iface() -> str:
    for line in _read("route").splitlines()[1:]:
        f = line.split()
        if len(f) > 7 and f[1] == "00000000":  # default route
            return f[0]
    # fallback: busiest non-virtual iface
    best, best_bytes = "", -1
    for name, rx, tx in _iter_dev():
        if name == "lo" or name.startswith(("docker", "br-", "veth", "gre")):
            continue
        if rx + tx > best_bytes:
            best, best_bytes = name, rx + tx
    return best


def _iter_dev():
    for line in _read("dev").splitlines()[2:]:
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        cols = rest.split()
        if len(cols) >= 9:
            yield name.strip(), int(cols[0]), int(cols[8])  # rx_bytes, tx_bytes


def iface_counters(name: str | None = None) -> dict:
    name = name or default_iface()
    for n, rx, tx in _iter_dev():
        if n == name:
            return {"iface": n, "rx_bytes": rx, "tx_bytes": tx}
    return {"iface": name or "?", "rx_bytes": 0, "tx_bytes": 0}


def _count_sockets(files) -> int:
    total = 0
    for f in files:
        txt = _read(f)
        if txt:
            total += max(txt.count("\n") - 1, 0)  # minus the header row
    return total


def _sockstat_inuse(proto: str) -> int:
    """`TCP: inuse N ...` totals from sockstat + sockstat6 (fast, kernel-summed)."""
    total = 0
    found = False
    for f in ("sockstat", "sockstat6"):
        for line in _read(f).splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[0] == f"{proto}:" and parts[1] == "inuse":
                try:
                    total += int(parts[2])
                    found = True
                except ValueError:
                    pass
    return total if found else -1


def socket_counts() -> dict:
    tcp = _sockstat_inuse("TCP")
    udp = _sockstat_inuse("UDP")
    if tcp < 0:  # sockstat unavailable -> count table rows
        tcp = _count_sockets(["tcp", "tcp6"])
    if udp < 0:
        udp = _count_sockets(["udp", "udp6"])
    return {"tcp": tcp, "udp": udp}


def _hex_ip(h: str) -> str:
    try:
        return socket.inet_ntoa(struct.pack("<I", int(h, 16)))
    except (ValueError, struct.error):
        return ""


def local_ips() -> list[str]:
    """All non-loopback IPv4 addresses assigned on the host."""
    ips: list[str] = []
    trie = _read("fib_trie")
    if trie:
        prev = ""
        for line in trie.splitlines():
            s = line.strip()
            if s.endswith("host LOCAL") and "/32" in s and prev:
                ip = prev.split()[-1] if prev.split() else ""
                if ip and not ip.startswith("127.") and ip not in ips:
                    ips.append(ip)
            prev = s
    if not ips:  # container fallback
        try:
            ips = [socket.gethostbyname(socket.gethostname())]
        except OSError:
            pass
    return ips


def gateways() -> list[str]:
    out = []
    for line in _read("route").splitlines()[1:]:
        f = line.split()
        if len(f) > 3 and f[2] != "00000000" and f[1] == "00000000":
            gw = _hex_ip(f[2])
            if gw and gw != "0.0.0.0":
                out.append(gw)
    # docker bridge gateways (172.x .1)
    for ip in local_ips():
        if ip.startswith(("172.1", "172.2", "172.3")) and ip.endswith(".1"):
            out.append(ip)
    return sorted(set(out))
