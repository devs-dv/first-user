"""Egress guard: a local proxy that every browser request must go through.

Chrome is launched with this proxy and with its implicit localhost bypass turned
off, so every navigation, redirect, subresource and websocket reaches it first.
For each new host the guard resolves the name itself, refuses it if any address
is private, loopback, link-local, cloud metadata or otherwise not public, and
then connects only to an address it vetted. Connecting to the vetted address
(not re-resolving) is what stops DNS rebinding.

A refusal is recorded on the guard; the agent loop ends the run as blocked.
"""

import asyncio
import contextvars
import ipaddress
import socket
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import neatlogs

CONNECT_TIMEOUT_SECONDS = 15
HEADER_TIMEOUT_SECONDS = 30
MAX_HEADER_BYTES = 64 * 1024
PIPE_CHUNK = 64 * 1024
NAT64 = ipaddress.ip_network("64:ff9b::/96")

# Chrome flags that go with the proxy: "<-loopback>" removes Chrome's built-in
# rule that sends localhost and 127.0.0.1 around the proxy, and WebRTC may not
# open UDP connections that would skip it.
CHROME_PROXY_BYPASS = "<-loopback>"
CHROME_EXTRA_ARGS = ["--force-webrtc-ip-handling-policy=disable_non_proxied_udp"]


def is_blocked_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True for anything a public visitor's browser should never reach."""
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return is_blocked_address(address.ipv4_mapped)
        if address in NAT64:
            return is_blocked_address(ipaddress.IPv4Address(int(address) & 0xFFFFFFFF))
    # is_global is False for private, loopback, link-local (169.254.169.254, the
    # cloud metadata address), carrier-grade NAT, unique-local, documentation
    # and reserved ranges.
    return not address.is_global or address.is_multicast


@dataclass
class Decision:
    allowed: bool
    addresses: list[str]
    reason: str = ""
    private: bool = False  # refused for safety, as opposed to simply not resolving


@dataclass
class EgressGuard:
    blocks: list[dict] = field(default_factory=list)
    _decisions: dict[str, Decision] = field(default_factory=dict)
    _locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    _server: asyncio.AbstractServer | None = None
    _context: contextvars.Context | None = None
    # True while the guard belongs to an active neatlogs run (see start()).
    _traced: bool = False
    # One task per open browser connection, so close() can cancel the ones still piping.
    _connections: set[asyncio.Task] = field(default_factory=set)
    port: int = 0
    # Chrome's own DevTools port. Stagehand's extension, running inside Chrome,
    # connects to it, so that one tunnel is allowed, but only for an extension.
    devtools_port: int | None = None

    @property
    def proxy_server(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    async def start(self) -> None:
        # Refusal spans are created in this context, so they nest under the run's trace. With
        # no neatlogs run active (tests, scripts), the guard creates no spans at all.
        self._context = contextvars.copy_context()
        self._traced = neatlogs.inject_trace_context({})
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def close(self) -> None:
        """Stop accepting connections, then cancel and await the ones still open.

        Cancelled connections create no spans: host checks are not traced, and a refusal
        span is created and ended in one synchronous call.
        """
        if self._server is None:
            return
        self._traced = False
        self._server.close()
        connections = list(self._connections)
        for task in connections:
            task.cancel()
        await asyncio.gather(*connections, return_exceptions=True)
        await self._server.wait_closed()
        self._server = None

    def summary(self) -> dict:
        """Hosts checked and refused during the run, for one summary on the run's trace."""
        refused = sorted({block["host"] for block in self.blocks})
        return {
            "hosts_checked": len(self._decisions),
            "hosts_allowed": sum(d.allowed for d in self._decisions.values()),
            "hosts_unresolved": sum(not d.allowed and not d.private for d in self._decisions.values()),
            "hosts_refused": refused,
            "refusals": len(self.blocks),
        }

    def _refused(self, record: dict) -> None:
        """Record a refusal, with a GUARDRAIL span in the run's trace while the run is active."""
        self.blocks.append(record)
        if self._traced and self._context is not None:
            self._context.copy().run(_refusal_span, record)

    def block_reason(self) -> str | None:
        """A visitor-facing reason for the first refused request, or None."""
        if not self.blocks:
            return None
        first = self.blocks[0]
        return (
            f"Stopped for safety: the site sent the browser to {first['host']}, which is a private, local or "
            f"cloud-metadata address ({', '.join(first['addresses'])}). "
            "First User never visits those, so the visit ended here."
        )

    async def _vet(self, host: str, port: int, url: str) -> Decision:
        key = host.lower()
        if key in self._decisions:
            decision = self._decisions[key]
        else:
            lock = self._locks.setdefault(key, asyncio.Lock())
            async with lock:
                if key not in self._decisions:
                    result = await _check_host(key, port)
                    self._decisions[key] = Decision(
                        result["allowed"], result["addresses"], result["reason"], result["private"]
                    )
            decision = self._decisions[key]
        if decision.private:
            self._refused({"host": host, "port": port, "url": url, "addresses": decision.addresses,
                           "reason": decision.reason})
        return decision

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        self._connections.add(task)
        upstream: asyncio.StreamWriter | None = None
        try:
            try:
                head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), HEADER_TIMEOUT_SECONDS)
            except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError):
                return
            if len(head) > MAX_HEADER_BYTES:
                return await _reply(writer, 431, "Request Header Fields Too Large")
            request_line, *header_lines = head.decode("latin-1").split("\r\n")
            parts = request_line.split(" ")
            if len(parts) != 3:
                return await _reply(writer, 400, "Bad Request")
            method, target, version = parts

            if method == "CONNECT":
                host, port = _split_host_port(target, default_port=443)
                url = f"https://{target}"
                if port == self.devtools_port and host.lower() in ("127.0.0.1", "localhost"):
                    return await self._devtools_tunnel(reader, writer, host, port)
            else:
                split = urlsplit(target)
                if split.scheme != "http" or not split.hostname:
                    return await _reply(writer, 400, "Bad Request")
                host, port = split.hostname, split.port or 80
                url = target

            decision = await self._vet(host, port, url)
            if decision.private:
                return await _reply(writer, 403, "Forbidden by First User egress guard")
            if not decision.allowed:
                return await _reply(writer, 502, "Bad Gateway")

            upstream_reader, upstream = await _open_vetted(decision.addresses, port)
            if upstream is None:
                return await _reply(writer, 502, "Bad Gateway")

            if method == "CONNECT":
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            else:
                # One request per connection: a reused client connection could name another host.
                path = urlsplit(target)._replace(scheme="", netloc="").geturl() or "/"
                headers = [
                    line for line in header_lines
                    if line and line.split(":", 1)[0].strip().lower()
                    not in ("proxy-connection", "connection", "keep-alive", "proxy-authorization")
                ]
                request = f"{method} {path} {version}\r\n" + "".join(f"{h}\r\n" for h in headers)
                upstream.write((request + "Connection: close\r\n\r\n").encode("latin-1"))
            await writer.drain()
            await asyncio.gather(_pipe(reader, upstream), _pipe(upstream_reader, writer))
        except (ConnectionError, OSError, ValueError):
            pass
        finally:
            self._connections.discard(task)
            for stream in (upstream, writer):
                if stream is not None:
                    stream.close()

    async def _devtools_tunnel(self, reader, writer, host: str, port: int) -> None:
        """Forward a tunnel to Chrome's DevTools port only if its first request comes from an extension.

        Stagehand launches Chrome with --remote-allow-origins=*, so DevTools itself
        would accept a websocket from any page. A DevTools websocket is plain HTTP
        inside the tunnel, and browsers always send an Origin header that pages
        cannot forge, so the guard checks it here instead.
        """
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), HEADER_TIMEOUT_SECONDS)
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError):
            return
        request_line, *header_lines = head.decode("latin-1").split("\r\n")
        origin = next(
            (line.split(":", 1)[1].strip() for line in header_lines if line.lower().startswith("origin:")), ""
        )
        # Only a browser extension (Stagehand's) may use the DevTools port.
        if not origin.startswith("chrome-extension://"):
            self._refused({"host": host, "port": port, "url": f"DevTools: {request_line[:200]}",
                           "addresses": [host], "reason": f"DevTools request from origin {origin or 'none'}"})
            return
        upstream_reader, upstream = await _open_vetted(["127.0.0.1"], port)
        if upstream is None:
            return
        try:
            upstream.write(head)
            await asyncio.gather(_pipe(reader, upstream), _pipe(upstream_reader, writer))
        finally:
            upstream.close()


@neatlogs.span(kind="GUARDRAIL", name="egress_refused")
def _refusal_span(record: dict) -> dict:
    """One span per refused request: synchronous, so it cannot be cut off by cancellation."""
    return {"refused": True, **record}


@neatlogs.span(kind="GUARDRAIL", name="egress_summary")
def summary_span(summary: dict) -> dict:
    """The guard's work for one run: how many hosts were checked, and which were refused."""
    return summary


async def _check_host(host: str, port: int) -> dict:
    """Resolve a host once per run and decide whether the browser may connect to it."""
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as error:
        # Not a safety block: the browser could not have loaded it either.
        return {"allowed": False, "private": False, "host": host, "addresses": [],
                "reason": f"could not resolve: {error}"}
    addresses = list(dict.fromkeys(info[4][0].split("%")[0] for info in infos))
    if not addresses:
        return {"allowed": False, "private": False, "host": host, "addresses": [], "reason": "no addresses"}
    blocked = [a for a in addresses if is_blocked_address(ipaddress.ip_address(a))]
    if blocked:
        # Refuse the whole host if any address is non-public, so it cannot be steered there.
        return {"allowed": False, "private": True, "host": host, "addresses": addresses,
                "reason": f"non-public address: {', '.join(blocked)}"}
    return {"allowed": True, "private": False, "host": host, "addresses": addresses, "reason": ""}


async def _open_vetted(addresses: list[str], port: int):
    for address in addresses:
        try:
            return await asyncio.wait_for(asyncio.open_connection(address, port), CONNECT_TIMEOUT_SECONDS)
        except (OSError, asyncio.TimeoutError):
            continue
    return None, None


async def _pipe(source: asyncio.StreamReader, sink: asyncio.StreamWriter) -> None:
    try:
        while data := await source.read(PIPE_CHUNK):
            sink.write(data)
            await sink.drain()
    except (ConnectionError, OSError):
        pass
    finally:
        if sink.can_write_eof():
            try:
                sink.write_eof()
            except (OSError, RuntimeError):
                pass


async def _reply(writer: asyncio.StreamWriter, status: int, message: str) -> None:
    body = message.encode()
    writer.write(
        f"HTTP/1.1 {status} {message}\r\nContent-Type: text/plain\r\nContent-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n".encode() + body
    )
    await writer.drain()


def _split_host_port(target: str, default_port: int) -> tuple[str, int]:
    if target.startswith("["):
        host, _, rest = target[1:].partition("]")
        return host, int(rest[1:]) if rest.startswith(":") else default_port
    host, _, port = target.rpartition(":")
    return (host, int(port)) if host else (target, default_port)
