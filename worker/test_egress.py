"""Tests for the egress guard.

Usage: python -m unittest test_egress -v

The redirect test opens a real Chrome window and goes through first_visit, but
stops before the first model call, so it costs nothing. It needs
ANTHROPIC_API_KEY in worker/.env only because Stagehand.create requires one.
Test servers listen on loopback, so 127.0.0.1 is treated as public for the
test origin; the redirect target 127.0.0.2 stays private.
"""

import asyncio
import ipaddress
import unittest
from pathlib import Path
from unittest import mock

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import egress  # noqa: E402

REAL_IS_BLOCKED = egress.is_blocked_address
TEST_ORIGIN = ipaddress.ip_address("127.0.0.1")


def origin_is_public(address):
    return False if address == TEST_ORIGIN else REAL_IS_BLOCKED(address)


class Server:
    """A tiny HTTP server that counts requests and answers with a fixed response."""

    def __init__(self, host: str, response: bytes):
        self.host, self.response, self.hits, self.port = host, response, 0, 0

    async def __aenter__(self):
        async def handle(reader, writer):
            await reader.readuntil(b"\r\n\r\n")
            self.hits += 1
            writer.write(self.response)
            await writer.drain()
            writer.close()

        self.server = await asyncio.start_server(handle, self.host, 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc):
        self.server.close()
        await self.server.wait_closed()


def http_response(status: str, headers: str = "", body: str = "") -> bytes:
    return (f"HTTP/1.1 {status}\r\n{headers}Content-Length: {len(body)}\r\nConnection: close\r\n\r\n{body}").encode()


async def proxy_request(guard: egress.EgressGuard, request: str) -> str:
    reader, writer = await asyncio.open_connection("127.0.0.1", guard.port)
    writer.write(request.encode())
    await writer.drain()
    status = (await reader.readline()).decode().strip()
    writer.close()
    return status


class AddressRules(unittest.TestCase):
    def test_non_public_addresses_are_blocked(self):
        for address in ["127.0.0.1", "10.0.0.5", "172.16.3.4", "192.168.1.1", "169.254.169.254", "100.64.0.1",
                        "0.0.0.0", "::1", "fd00::1", "fe80::1", "::ffff:127.0.0.1", "64:ff9b::a9fe:a9fe"]:
            with self.subTest(address=address):
                self.assertTrue(egress.is_blocked_address(ipaddress.ip_address(address)))

    def test_public_addresses_are_allowed(self):
        for address in ["8.8.8.8", "93.184.215.14", "2606:4700:4700::1111"]:
            with self.subTest(address=address):
                self.assertFalse(egress.is_blocked_address(ipaddress.ip_address(address)))


class ProxyRefusals(unittest.IsolatedAsyncioTestCase):
    async def test_private_targets_are_refused_and_never_contacted(self):
        async with Server("127.0.0.2", http_response("200 OK", body="secret")) as secret:
            guard = egress.EgressGuard()
            await guard.start()
            try:
                plain = await proxy_request(
                    guard, f"GET http://127.0.0.2:{secret.port}/ HTTP/1.1\r\nHost: 127.0.0.2\r\n\r\n")
                tunnel = await proxy_request(guard, "CONNECT localhost:443 HTTP/1.1\r\nHost: localhost:443\r\n\r\n")
                metadata = await proxy_request(
                    guard, "GET http://169.254.169.254/latest/meta-data/ HTTP/1.1\r\nHost: 169.254.169.254\r\n\r\n")
            finally:
                await guard.close()
        self.assertIn("403", plain)
        self.assertIn("403", tunnel)
        self.assertIn("403", metadata)
        self.assertEqual(secret.hits, 0)
        self.assertEqual([b["host"] for b in guard.blocks], ["127.0.0.2", "localhost", "169.254.169.254"])

    async def test_devtools_port_only_opens_for_an_extension(self):
        async with Server("127.0.0.1", http_response("101 Switching Protocols")) as devtools:
            guard = egress.EgressGuard(devtools_port=devtools.port)
            await guard.start()
            try:
                statuses = {}
                for origin in ("https://evil.example", "chrome-extension://abcdefghijklmnop"):
                    reader, writer = await asyncio.open_connection("127.0.0.1", guard.port)
                    writer.write(f"CONNECT 127.0.0.1:{devtools.port} HTTP/1.1\r\n\r\n".encode())
                    await reader.readuntil(b"\r\n\r\n")  # the proxy's 200 for the tunnel
                    writer.write(f"GET /devtools/browser/x HTTP/1.1\r\nOrigin: {origin}\r\n"
                                 "Upgrade: websocket\r\n\r\n".encode())
                    await writer.drain()
                    statuses[origin] = (await reader.readline()).decode().strip()
                    writer.close()
            finally:
                await guard.close()
        self.assertEqual(statuses["https://evil.example"], "", "a page must not reach DevTools")
        self.assertIn("101", statuses["chrome-extension://abcdefghijklmnop"])
        self.assertEqual(devtools.hits, 1)
        self.assertEqual(len(guard.blocks), 1)

    async def test_unresolvable_host_is_not_a_safety_block(self):
        guard = egress.EgressGuard()
        await guard.start()
        try:
            status = await proxy_request(
                guard, "GET http://no-such-host.invalid/ HTTP/1.1\r\nHost: no-such-host.invalid\r\n\r\n")
        finally:
            await guard.close()
        self.assertIn("502", status)
        self.assertEqual(guard.blocks, [])


class RedirectInRealBrowser(unittest.IsolatedAsyncioTestCase):
    async def test_redirect_to_private_address_is_refused_and_ends_run_as_blocked(self):
        from visit import first_visit

        async with Server("127.0.0.2", http_response("200 OK", body="secret")) as secret:
            redirect = http_response("302 Found", f"Location: http://127.0.0.2:{secret.port}/secret\r\n")
            async with Server("127.0.0.1", redirect) as origin:
                with mock.patch("egress.is_blocked_address", origin_is_public):
                    result = await first_visit(
                        f"http://127.0.0.1:{origin.port}/", "Look around.", "test-egress-redirect")

        self.assertGreaterEqual(origin.hits, 1, "the allowed origin should have been reached through the proxy")
        self.assertEqual(secret.hits, 0, "the private redirect target must never be contacted")
        self.assertEqual(result["outcome"], "blocked")
        self.assertIn("127.0.0.2", result["reason"])
        self.assertEqual(result["steps"], 0, "the run should end before any model call")


if __name__ == "__main__":
    unittest.main()
