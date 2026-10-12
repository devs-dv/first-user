"""Tests for "Understand this website": page discovery, the brief's checks and the run's lifecycle.

Usage: python -m unittest test_understand -v

Nothing here touches the job queue or the database, and no model is called: the brief's model call is
a stand-in that returns whatever a test wants (including things a model must not be believed about). The
sites are small servers on loopback; 127.0.0.1 is treated as public for them (as in test_egress.py),
while 127.0.0.2 and the metadata address stay private. One live test drives a real Chrome behind the
guard for a page that needs JavaScript; SKIP_LIVE_TESTS=1 skips it.
"""

import test_support  # noqa: F401  (first: keeps tests from sending traces to neatlogs)

import asyncio
import ipaddress
import os
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import urljoin

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import egress  # noqa: E402
import site_reader  # noqa: E402
import understand  # noqa: E402
from site_reader import PageRead, SiteRead  # noqa: E402

REAL_IS_BLOCKED = egress.is_blocked_address
TEST_ORIGIN = ipaddress.ip_address("127.0.0.1")


def origin_is_public(address):
    return False if address == TEST_ORIGIN else REAL_IS_BLOCKED(address)


FILLER = ("This sentence is here so the page has enough visible text to count as a real page and not a shell "
          "that scripts fill in later. ")


def html(title: str, body: str, links: str = "") -> str:
    return (f"<html><head><title>{title}</title><meta name='description' content='{title} description'></head>"
            f"<body><nav>{links}</nav><main><h1>{title}</h1><p>{body}</p><p>{FILLER * 4}</p></main></body></html>")


class Site:
    """A tiny web server: path -> html (or (status, content type, body, extra headers)); counts requests."""

    def __init__(self, routes: dict, host: str = "127.0.0.1"):
        self.routes, self.host, self.requests, self.port = routes, host, [], 0

    async def __aenter__(self):
        async def handle(reader, writer):
            try:
                head = await reader.readuntil(b"\r\n\r\n")
                path = head.split(b" ", 2)[1].decode()
                self.requests.append(path)
                route = self.routes.get(path)
                if route is None:
                    status, ctype, body, extra = 404, "text/html", "not found", ""
                elif isinstance(route, str):
                    status, ctype, body, extra = 200, "text/html; charset=utf-8", route, ""
                else:
                    status, ctype, body, extra = route
                data = body.encode() if isinstance(body, str) else body
                writer.write(f"HTTP/1.1 {status} X\r\nContent-Type: {ctype}\r\nContent-Length: {len(data)}\r\n"
                             f"{extra}Connection: close\r\n\r\n".encode() + data)
                await writer.drain()
            except (ConnectionError, asyncio.IncompleteReadError, OSError):
                pass
            finally:
                writer.close()

        self.server = await asyncio.start_server(handle, self.host, 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc):
        self.server.close()
        await self.server.wait_closed()

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def pages_requested(self) -> list[str]:
        return [path for path in self.requests if path != "/robots.txt"]


class FakeRenderer:
    def __init__(self, text: str = ""):
        self.text, self.rendered, self.closed = text, [], False

    async def render(self, url: str) -> str:
        self.rendered.append(url)
        return f"<html><head><title>Rendered</title></head><body><main><p>{self.text}</p></main></body></html>"

    async def close(self) -> None:
        self.closed = True


class FakeModel:
    def __init__(self, raw: dict):
        self.raw, self.prompts = raw, []

    async def __call__(self, prompt: str) -> dict:
        self.prompts.append(prompt)
        return self.raw


def raw_brief(**overrides) -> dict:
    brief = {
        "one_liner": "Acme tracks invoices.", "what_it_does": "Acme tracks invoices for small shops.",
        "who_its_for": "Small shops.", "how_it_works": "Connect your bank; it matches invoices.",
        "primary_value": "Never chase a late invoice again.",
        "pricing": {"status": "unclear", "note": "", "tiers": []},
        "business_model": {"model": "unknown", "evidence": []},
        "claims": [], "unknowns": [], "suggested_journeys": [],
    }
    brief.update(overrides)
    return brief


def small_site(extra: dict | None = None) -> dict:
    routes = {
        "/": html("Acme", "Acme tracks invoices for small shops. Start your free trial today.",
                  "<a href='/about'>About</a> <a href='/features'>Features</a>"),
        "/about": html("About Acme", "We are a team of six who hate late invoices."),
        "/features": html("Features", "Bank sync, reminders and reports."),
    }
    routes.update(extra or {})
    return routes


async def understand_with(site: Site, model: FakeModel, **kwargs) -> dict:
    kwargs.setdefault("delay", 0)
    kwargs.setdefault("renderer", FakeRenderer())
    with mock.patch("egress.is_blocked_address", origin_is_public):
        return await understand.understand_site(site.url, "test-run", model_call=model, **kwargs)


class NoPricingPage(unittest.IsolatedAsyncioTestCase):
    async def test_a_site_with_no_pricing_page_says_not_published_and_has_no_prices(self):
        # The model is wrong on purpose: it "published" a price that is on no page.
        model = FakeModel(raw_brief(pricing={"status": "published", "note": "", "tiers": [
            {"name": "Pro", "price": "$29/month", "what_you_get": "Everything", "source_url": "{home}"}]}))
        async with Site(small_site()) as site:
            model.raw["pricing"]["tiers"][0]["source_url"] = site.url
            result = await understand_with(site, model)
        pricing = result["brief"]["pricing"]
        self.assertEqual(pricing["status"], "not_published")
        self.assertEqual(pricing["tiers"], [])
        self.assertIn("No pricing page", pricing["note"])
        self.assertIn("What it costs.", result["brief"]["unknowns"])

    async def test_a_price_that_is_not_in_the_cited_page_is_dropped_even_with_a_pricing_page(self):
        routes = small_site({
            "/": html("Acme", "Invoices.", "<a href='/pricing'>Pricing</a>"),
            "/pricing": html("Pricing", "Starter is $9 per month. Team is $29 per month."),
        })
        async with Site(routes) as site:
            tiers = [
                {"name": "Starter", "price": "$9 per month", "what_you_get": "One shop", "source_url": site.url + "pricing"},
                {"name": "Team", "price": "$29 per month", "what_you_get": "Five shops", "source_url": site.url + "pricing"},
                {"name": "Enterprise", "price": "$499 per month", "what_you_get": "Invented", "source_url": site.url + "pricing"},
            ]
            model = FakeModel(raw_brief(pricing={"status": "published", "note": "", "tiers": tiers}))
            result = await understand_with(site, model)
        pricing = result["brief"]["pricing"]
        self.assertEqual(pricing["status"], "published")
        self.assertEqual([t["name"] for t in pricing["tiers"]], ["Starter", "Team"])

    async def test_a_pricing_page_with_no_figures_is_unclear_not_not_published(self):
        routes = small_site({
            "/": html("Acme", "Invoices.", "<a href='/pricing'>Pricing</a>"),
            "/pricing": html("Pricing", "Talk to our sales team for a quote."),
        })
        async with Site(routes) as site:
            model = FakeModel(raw_brief(pricing={"status": "not_published", "note": "", "tiers": []}))
            result = await understand_with(site, model)
        self.assertEqual(result["brief"]["pricing"]["status"], "unclear")
        self.assertEqual(result["brief"]["pricing"]["tiers"], [])


class PrivateAddressesAreRefused(unittest.IsolatedAsyncioTestCase):
    async def test_a_homepage_on_a_private_address_is_refused_and_never_contacted(self):
        async with Site(small_site(), host="127.0.0.2") as private:
            model = FakeModel(raw_brief())
            with mock.patch("egress.is_blocked_address", origin_is_public):
                with self.assertRaises(understand.SiteUnreadable) as caught:
                    await understand.understand_site(private.url, "t", model_call=model, delay=0,
                                                     renderer=FakeRenderer())
        self.assertEqual(private.requests, [])
        self.assertIn("private, local or cloud-metadata", str(caught.exception))
        self.assertEqual(model.prompts, [], "no model call is made for a site that was not read")

    async def test_the_cloud_metadata_address_is_refused(self):
        with self.assertRaises(understand.SiteUnreadable):
            await understand.understand_site("http://169.254.169.254/latest/meta-data/", "t",
                                             model_call=FakeModel(raw_brief()), delay=0, renderer=FakeRenderer())

    async def test_loopback_by_name_and_by_address_is_refused(self):
        for url in ("http://localhost/", "http://127.0.0.1:9/", "http://[::1]/", "http://10.0.0.5/"):
            with self.subTest(url=url):
                with self.assertRaises(understand.SiteUnreadable):
                    await understand.understand_site(url, "t", model_call=FakeModel(raw_brief()), delay=0,
                                                     renderer=FakeRenderer())

    async def test_a_redirect_from_the_site_to_a_private_address_is_refused(self):
        async with Site({"/secret": "secret"}, host="127.0.0.2") as private:
            routes = {"/": (302, "text/html", "", f"Location: http://127.0.0.2:{private.port}/secret\r\n")}
            async with Site(routes) as origin:
                with mock.patch("egress.is_blocked_address", origin_is_public):
                    with self.assertRaises(understand.SiteUnreadable):
                        await understand.understand_site(origin.url, "t", model_call=FakeModel(raw_brief()),
                                                         delay=0, renderer=FakeRenderer())
        self.assertEqual(private.requests, [], "the private redirect target must never be contacted")
        self.assertGreaterEqual(len(origin.requests), 1)

    async def test_a_link_to_a_private_address_is_not_followed(self):
        async with Site({"/pricing": html("Pricing", "$1 per month")}, host="127.0.0.2") as private:
            routes = small_site({"/": html(
                "Acme", "Invoices.",
                f"<a href='http://127.0.0.2:{private.port}/pricing'>Pricing</a> <a href='/about'>About</a>")})
            async with Site(routes) as site:
                result = await understand_with(site, FakeModel(raw_brief()))
        self.assertEqual(private.requests, [])
        self.assertEqual([p["kind"] for p in result["brief"]["pages"]], ["home", "about"])


class PageCap(unittest.IsolatedAsyncioTestCase):
    def crowded_routes(self) -> dict:
        links = "".join(f"<a href='/{kind}-{n}'>{kind} {n}</a>"
                        for kind in ("product", "features", "about", "docs", "faq", "customers", "pricing")
                        for n in range(4))
        links += "".join(f"<a href='/blog'>Blog</a><a href='/blog/post-{n}'>Post {n}</a>" for n in range(10))
        routes = {"/": html("Acme", "Invoices.", links), "/blog": html("Blog", "News.")}
        for kind in ("product", "features", "about", "docs", "faq", "customers", "pricing"):
            for n in range(4):
                routes[f"/{kind}-{n}"] = html(f"{kind} {n}", f"The {kind} page {n}.")
        return routes

    async def test_no_more_than_nine_pages_are_read_whatever_the_site_links(self):
        async with Site(self.crowded_routes()) as site:
            result = await understand_with(site, FakeModel(raw_brief()))
        self.assertEqual(len(result["brief"]["pages"]), 9)
        self.assertLessEqual(len(site.pages_requested()), 9)
        self.assertEqual(site.pages_requested()[0], "/")
        # One of each kind comes first, so a crowded site is not read as nine product pages.
        kinds = [p["kind"] for p in result["brief"]["pages"]]
        for kind in ("home", "pricing", "product", "features", "about", "docs", "faq", "customers", "blog"):
            self.assertIn(kind, kinds)

    async def test_a_smaller_cap_holds_and_a_blog_post_is_never_taken_for_the_index(self):
        async with Site(self.crowded_routes()) as site:
            result = await understand_with(site, FakeModel(raw_brief()), max_pages=3)
        self.assertEqual(len(result["brief"]["pages"]), 3)
        self.assertLessEqual(len(site.pages_requested()), 3)
        self.assertNotIn("/blog/post-0", site.requests)

    async def test_a_page_is_read_only_up_to_the_byte_cap(self):
        big = html("Big", "Lots of text. " * 20000)
        async with Site(small_site({"/": big})) as site:
            result = await understand_with(site, FakeModel(raw_brief()), max_bytes=5000)
        home = result["brief"]["pages"][0]
        self.assertLessEqual(home["bytes"], 5000)

    async def test_the_time_cap_stops_discovery_after_the_homepage(self):
        async with Site(small_site()) as site:
            result = await understand_with(site, FakeModel(raw_brief()), max_seconds=0.0)
        self.assertEqual(len(result["brief"]["pages"]), 1)
        self.assertTrue(any("time limit" in s["reason"] for s in result["brief"]["skipped"]))


class Politeness(unittest.IsolatedAsyncioTestCase):
    async def test_robots_txt_is_honoured(self):
        routes = small_site({
            "/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /features\n", ""),
        })
        async with Site(routes) as site:
            result = await understand_with(site, FakeModel(raw_brief()))
        self.assertNotIn("/features", site.requests)
        self.assertIn("/about", site.requests)
        skipped = result["brief"]["skipped"]
        self.assertEqual([(s["kind"], "robots.txt" in s["reason"]) for s in skipped], [("features", True)])

    async def test_a_homepage_robots_txt_disallows_is_not_read(self):
        routes = small_site({"/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /\n", "")})
        async with Site(routes) as site:
            with mock.patch("egress.is_blocked_address", origin_is_public):
                with self.assertRaises(understand.SiteUnreadable) as caught:
                    await understand.understand_site(site.url, "t", model_call=FakeModel(raw_brief()), delay=0,
                                                     renderer=FakeRenderer())
        self.assertEqual(site.pages_requested(), [])
        self.assertIn("robots.txt", str(caught.exception))

    async def test_a_wait_separates_requests_and_crawl_delay_raises_it(self):
        waits: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            waits.append(round(seconds, 3))

        ticks = iter(range(0, 1000))
        routes = small_site({"/robots.txt": (200, "text/plain", "User-agent: *\nCrawl-delay: 3\n", "")})
        async with Site(routes) as site:
            guard = egress.EgressGuard()
            with mock.patch("egress.is_blocked_address", origin_is_public):
                await guard.start()
                try:
                    discovery = site_reader.SiteDiscovery(
                        site.url, guard, renderer=FakeRenderer(), delay=1.0, sleep=fake_sleep,
                        clock=lambda: next(ticks) * 0.01)
                    read = await discovery.run()
                finally:
                    await guard.close()
        # robots.txt, home, about, features: three gaps, each (almost) the crawl delay of 3 s.
        self.assertEqual(len(read.pages), 3)
        self.assertEqual(len(waits), 3)
        self.assertTrue(all(2.9 <= wait <= 3.0 for wait in waits), waits)

    async def test_a_site_that_cannot_serve_robots_txt_is_left_alone(self):
        routes = small_site({"/robots.txt": (503, "text/plain", "busy", "")})
        async with Site(routes) as site:
            with mock.patch("egress.is_blocked_address", origin_is_public):
                with self.assertRaises(understand.SiteUnreadable):
                    await understand.understand_site(site.url, "t", model_call=FakeModel(raw_brief()), delay=0,
                                                     renderer=FakeRenderer())
        self.assertEqual(site.pages_requested(), [])


class TheBrowserIsTheLastResort(unittest.IsolatedAsyncioTestCase):
    async def test_a_page_with_plenty_of_text_never_uses_the_browser(self):
        renderer = FakeRenderer("x" * 1000)
        async with Site(small_site()) as site:
            result = await understand_with(site, FakeModel(raw_brief()), renderer=renderer)
        self.assertEqual(renderer.rendered, [])
        self.assertTrue(all(p["method"] == "http" for p in result["brief"]["pages"]))
        self.assertTrue(renderer.closed)

    async def test_a_thin_page_is_rendered_and_the_richer_text_is_used(self):
        shell = "<html><head><title>App</title></head><body><div id='app'></div><script>x()</script></body></html>"
        renderer = FakeRenderer("Acme tracks invoices for small shops. " * 20)
        async with Site(small_site({"/": shell})) as site:
            model = FakeModel(raw_brief())
            result = await understand_with(site, model, renderer=renderer)
        self.assertEqual(len(renderer.rendered), 1)
        self.assertEqual(result["brief"]["pages"][0]["method"], "browser")
        self.assertIn("Acme tracks invoices", model.prompts[0])

    async def test_the_number_of_browser_reads_is_capped(self):
        shell = "<html><head><title>T</title></head><body><a href='/about'>About</a><a href='/features'>F</a>" \
                "<a href='/docs'>Docs</a><a href='/faq'>FAQ</a><a href='/pricing'>Pricing</a></body></html>"
        routes = {path: shell for path in ("/", "/about", "/features", "/docs", "/faq", "/pricing")}
        renderer = FakeRenderer("")
        async with Site(routes) as site:
            await understand_with(site, FakeModel(raw_brief()), renderer=renderer)
        self.assertLessEqual(len(renderer.rendered), site_reader.MAX_RENDERS)

    @unittest.skipIf(os.environ.get("SKIP_LIVE_TESTS"), "SKIP_LIVE_TESTS is set")
    async def test_a_real_browser_reads_a_page_drawn_by_javascript(self):
        script = ("document.getElementById('app').innerHTML = '<h1>Acme</h1><p>' + 'Acme tracks invoices for "
                  "small shops. '.repeat(30) + '</p>';")
        shell = f"<html><head><title>Acme</title></head><body><div id='app'></div><script>{script}</script></body></html>"
        async with Site({"/": shell}) as site:
            model = FakeModel(raw_brief())
            result = await understand_with(site, model, renderer=site_reader.BrowserRenderer())
        self.assertEqual(result["brief"]["pages"][0]["method"], "browser")
        self.assertIn("Acme tracks invoices", model.prompts[0])


class EveryClaimHasASource(unittest.IsolatedAsyncioTestCase):
    async def test_claims_without_a_page_that_was_read_are_dropped(self):
        async with Site(small_site()) as site:
            raw = raw_brief(claims=[
                {"claim": "Matches invoices to bank payments", "source_url": site.url + "features",
                 "status": "confirmed", "quote": "Bank sync, reminders and reports."},
                {"claim": "Used by 10,000 shops", "source_url": "", "status": "confirmed", "quote": ""},
                {"claim": "SOC 2 certified", "source_url": "https://elsewhere.example/security",
                 "status": "confirmed", "quote": "SOC 2"},
                {"claim": "Works offline", "source_url": site.url + "never-read", "status": "inferred", "quote": ""},
                {"claim": "No source key at all"},
                "not even an object",
                {"claim": "Built by six people", "source_url": site.url + "about", "status": "inferred", "quote": ""},
            ])
            result = await understand_with(site, FakeModel(raw))
        brief = result["brief"]
        read = {page["url"] for page in brief["pages"]}
        self.assertEqual([c["claim"] for c in brief["claims"]],
                         ["Matches invoices to bank payments", "Built by six people"])
        for claim in brief["claims"]:
            self.assertIn(claim["source_url"], read)
            self.assertTrue(claim["source_url"].startswith("http"))

    async def test_confirmed_needs_words_that_are_on_the_page(self):
        async with Site(small_site()) as site:
            raw = raw_brief(claims=[
                {"claim": "Has bank sync", "source_url": site.url + "features", "status": "confirmed",
                 "quote": "Bank sync, reminders and reports."},
                {"claim": "Has a mobile app", "source_url": site.url + "features", "status": "confirmed",
                 "quote": "Download our iOS app"},
                {"claim": "Has a free trial", "source_url": site.url + "features", "status": "confirmed", "quote": ""},
                {"claim": "Might do payroll", "source_url": site.url + "features", "status": "unknown", "quote": ""},
            ])
            result = await understand_with(site, FakeModel(raw))
        by_claim = {c["claim"]: c for c in result["brief"]["claims"]}
        self.assertEqual(by_claim["Has bank sync"]["status"], "confirmed")
        self.assertEqual(by_claim["Has a mobile app"]["status"], "inferred")
        self.assertEqual(by_claim["Has a mobile app"]["quote"], "")
        self.assertEqual(by_claim["Has a free trial"]["status"], "inferred")
        self.assertEqual(by_claim["Might do payroll"]["status"], "unknown")

    async def test_a_source_url_is_matched_across_a_trailing_slash_and_a_fragment(self):
        async with Site(small_site()) as site:
            raw = raw_brief(claims=[
                {"claim": "A", "source_url": site.url + "about/", "status": "inferred", "quote": ""},
                {"claim": "B", "source_url": site.url + "about#team", "status": "inferred", "quote": ""},
            ])
            result = await understand_with(site, FakeModel(raw))
        self.assertEqual({c["source_url"] for c in result["brief"]["claims"]}, {site.url + "about"})


class BusinessModelAndJourneys(unittest.IsolatedAsyncioTestCase):
    async def test_business_model_is_always_labelled_inferred_and_needs_evidence(self):
        async with Site(small_site()) as site:
            with_evidence = raw_brief(business_model={"model": "Subscription after a free trial", "evidence": [
                {"quote": "Start your free trial today.", "source_url": site.url},
                {"quote": "A quote that is on no page", "source_url": site.url}]})
            without = raw_brief(business_model={"model": "Advertising", "evidence": []})
            first = (await understand_with(site, FakeModel(with_evidence)))["brief"]["business_model"]
            second = (await understand_with(site, FakeModel(without)))["brief"]["business_model"]
        self.assertEqual(first["label"], "inferred")
        self.assertEqual(first["model"], "Subscription after a free trial")
        self.assertEqual([e["quote"] for e in first["evidence"]], ["Start your free trial today."])
        self.assertEqual(second["label"], "inferred")
        self.assertEqual(second["model"], "unknown")

    async def test_journeys_come_from_the_site_and_are_capped(self):
        async with Site(small_site()) as site:
            def journey(goal, text, source=None, basis="call_to_action"):
                return {"goal": goal, "success": "A confirmation appears", "source_url": source or site.url,
                        "basis": basis, "basis_text": text}

            raw = raw_brief(suggested_journeys=[
                journey("Start a free trial", "Start your free trial today"),
                journey("Read what the team is like", "a team of six", site.url + "about", "claim"),
                journey("Connect a bank", "Bank sync", site.url + "features", "claim"),
                journey("Invented goal", "A button that is not on the page"),
                journey("Another", "Start your free trial today", site.url + "nowhere"),
                journey("Start a free trial", "Start your free trial today"),
                journey("Goal 4", "Start your free trial"), journey("Goal 5", "Start your free trial"),
                journey("Goal 6", "Start your free trial"),
            ])
            brief = (await understand_with(site, FakeModel(raw)))["brief"]
        journeys = brief["suggested_journeys"]
        self.assertEqual(len(journeys), 5)
        self.assertNotIn("Invented goal", [j["goal"] for j in journeys])
        self.assertEqual(len({j["goal"] for j in journeys}), 5)
        self.assertEqual([j["claim_to_test"] for j in journeys[:3]], [False, True, True])
        read = {p["url"] for p in brief["pages"]}
        self.assertTrue(all(j["source_url"] in read and j["success"] for j in journeys))

    async def test_goals_that_do_not_quote_the_pages_get_one_more_try_and_no_more(self):
        async with Site(small_site()) as site:
            bad = raw_brief(suggested_journeys=[{"goal": "G", "success": "S", "source_url": site.url,
                                                 "basis": "claim", "basis_text": "not on the page"}])
            good = raw_brief(suggested_journeys=[
                {"goal": f"G{n}", "success": "S", "source_url": site.url, "basis": "call_to_action",
                 "basis_text": "Start your free trial"} for n in range(3)])
            replies = iter([bad, good])
            prompts = []

            async def model(prompt):
                prompts.append(prompt)
                return next(replies)

            brief = (await understand_with(site, model))["brief"]
            self.assertEqual(len(prompts), 2)
            self.assertIn("word for word", prompts[1])
            self.assertEqual(len(brief["suggested_journeys"]), 3)

            always_bad = FakeModel(bad)
            await understand_with(site, always_bad)
            self.assertEqual(len(always_bad.prompts), 2, "one retry at most")

    async def test_missing_fields_are_unknown_not_filled_in(self):
        async with Site(small_site()) as site:
            raw = raw_brief(who_its_for="", how_it_works="Unknown", primary_value="   ")
            brief = (await understand_with(site, FakeModel(raw)))["brief"]
        self.assertEqual((brief["who_its_for"], brief["how_it_works"], brief["primary_value"]),
                         ("unknown", "unknown", "unknown"))
        self.assertEqual(brief["suggested_journeys"], [])
        self.assertTrue(any("goal(s) could be tied" in u for u in brief["unknowns"]))

    async def test_an_unusable_model_reply_still_gives_a_brief_of_unknowns(self):
        async with Site(small_site()) as site:
            brief = (await understand_with(site, FakeModel(["not", "a", "dict"])))["brief"]  # type: ignore[arg-type]
        self.assertEqual(brief["what_it_does"], "unknown")
        self.assertEqual(brief["pricing"]["status"], "not_published")
        self.assertEqual(brief["claims"], [])


class IncompleteReplies(unittest.IsolatedAsyncioTestCase):
    async def test_a_reply_that_stopped_early_is_asked_for_again_not_taken_as_unknowns(self):
        replies = iter([{"one_liner": "x"}, {"one_liner": "x", "claims": []}, raw_brief()])
        calls = []

        async def fake(prompt, usage):
            calls.append(prompt)
            return next(replies)

        with mock.patch.object(understand, "_one_reply", fake):
            raw = await understand._ask_model("p", understand.TokenTally())
        self.assertEqual(len(calls), 3)
        self.assertEqual(understand.missing_fields(raw), [])

    async def test_it_gives_up_after_three_tries_and_the_run_fails(self):
        async def fake(prompt, usage):
            return {"one_liner": "x"}

        with mock.patch.object(understand, "_one_reply", fake):
            with self.assertRaises(understand.BriefIncomplete):
                await understand._ask_model("p", understand.TokenTally())


class ClippingText(unittest.TestCase):
    def test_long_text_is_cut_at_a_word_with_an_ellipsis(self):
        clipped = understand._clip("Everything in Business. " * 30, 100)
        self.assertLessEqual(len(clipped), 100)
        self.assertTrue(clipped.endswith("Business…") or clipped.endswith("in…") or clipped.endswith("Everything…"))
        self.assertEqual(understand._clip("short   text", 100), "short text")


class ReadingHtml(unittest.TestCase):
    def test_text_headings_links_and_what_is_left_out(self):
        page = site_reader.parse_html(
            "<html><head><title> My  Site </title><meta property='og:description' content='A site'>"
            "<script>var secret = 1;</script><style>.a{}</style></head><body><nav><a href='/pricing'>Pricing</a></nav>"
            "<h1>Hello</h1><p>One <b>two</b></p><script>bad()</script><noscript>enable js</noscript>"
            "<a href='mailto:a@b.c'>mail</a><a href='/docs#x' aria-label='Docs'>read</a>"
            "<footer><a href='/pricing'>Pricing</a></footer></body></html>",
            "https://example.com/")
        self.assertEqual(page.title, "My Site")
        self.assertEqual(page.description, "A site")
        self.assertEqual(page.headings, ["Hello"])
        self.assertIn("One two", page.text)
        self.assertNotIn("secret", page.text)
        self.assertNotIn("bad()", page.text)
        self.assertNotIn("enable js", page.text)
        self.assertEqual(page.text.count("Pricing"), 1, "a menu repeated in header and footer is read once")
        self.assertIn(("https://example.com/pricing", "Pricing"), page.links)
        self.assertIn(("https://example.com/docs#x", "Docs read"), page.links)

    def test_an_unclosed_head_does_not_hide_the_page(self):
        page = site_reader.parse_html("<html><head><title>T</title><body><p>Visible words here</p></body>", "https://e.com/")
        self.assertIn("Visible words here", page.text)

    def test_broken_markup_does_not_raise(self):
        site_reader.parse_html("<div><p>unclosed <a href=>x</a><<>>&&;", "https://e.com/")


class ChoosingPages(unittest.TestCase):
    HOME = "https://www.example.com/"

    def test_kinds_come_from_link_text_and_path(self):
        links = [("/about-us", "Our company"), ("https://www.example.com/pricing", "Plans"), ("/p/x", "Pricing"),
                 ("/docs", "Developers"), ("/customers/acme", "Case studies"), ("/blog", "Blog"),
                 ("/blog/2024/launch", "Launch post"), ("/login", "Pricing login"), ("/brochure.pdf", "Features"),
                 ("https://other.com/pricing", "Pricing"), ("mailto:hi@example.com", "About"),
                 ("https://docs.example.com/", "Docs")]
        absolute = [(urljoin(self.HOME, url), text) for url, text in links]
        chosen = {url.removeprefix("https://www.example.com"): kind
                  for url, kind in site_reader.choose_pages(self.HOME, absolute, 20)}
        self.assertEqual(chosen.get("/about-us"), "about")
        self.assertEqual(chosen.get("/pricing"), "pricing")
        self.assertEqual(chosen.get("/p/x"), "pricing")
        self.assertEqual(chosen.get("/blog"), "blog")
        self.assertNotIn("/blog/2024/launch", chosen)
        self.assertNotIn("/login", chosen)
        self.assertNotIn("/brochure.pdf", chosen)
        self.assertNotIn("https://other.com/pricing", chosen)
        self.assertEqual(chosen.get("https://docs.example.com/"), "docs")

    def test_a_changelog_is_not_taken_for_the_product_page(self):
        links = [("https://www.example.com/changelog", "Product updates"),
                 ("https://www.example.com/product", "Product")]
        self.assertEqual(site_reader.choose_pages(self.HOME, links, 5),
                         [("https://www.example.com/product", "product")])

    def test_same_site_allows_www_and_subdomains_only(self):
        self.assertTrue(site_reader.same_site("https://example.com/a", "https://www.example.com/"))
        self.assertTrue(site_reader.same_site("https://docs.example.com/", "https://example.com/"))
        self.assertFalse(site_reader.same_site("https://example.com.evil.io/", "https://example.com/"))
        self.assertFalse(site_reader.same_site("https://notexample.com/", "https://example.com/"))
        self.assertFalse(site_reader.same_site("http://example.com:8080/", "http://example.com/"))


class RunLifecycle(unittest.IsolatedAsyncioTestCase):
    """execute_understand with a stand-in for the database and for the reading."""

    def setUp(self):
        import understand_run

        self.understand_run = understand_run
        self.updates: list[dict] = []

    async def _update(self, run_id, update):
        self.updates.append({"id": run_id, **update})

    async def test_a_brief_is_saved_on_the_run_as_done(self):
        async def fake(url, run_id):
            return {"brief": {"claims": [], "suggested_journeys": []}, "usage": {"calls": 1}, "cost_usd": 0.002}

        await self.understand_run.execute_understand(
            {"id": "r1", "url": "https://x.example/"}, "v", understand=fake, update=self._update)
        (saved,) = self.updates
        self.assertEqual((saved["status"], saved["cost_usd"]), ("done", 0.002))
        self.assertIn("brief", saved)

    async def test_an_unreadable_site_fails_the_run_with_a_message_for_the_page(self):
        async def fake(url, run_id):
            raise understand.SiteUnreadable("The homepage could not be read: the site answered 404.")

        await self.understand_run.execute_understand(
            {"id": "r2", "url": "https://x.example/"}, "v", understand=fake, update=self._update)
        (saved,) = self.updates
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["brief"]["status"], "could_not_read")
        self.assertIn("404", saved["brief"]["message"])

    async def test_the_worker_hands_understand_runs_to_the_brief_path(self):
        import worker_run

        with mock.patch("understand_run.execute_understand", new=mock.AsyncMock()) as handler:
            await worker_run.execute({"id": "r3", "kind": "understand", "url": "https://x.example/"}, "v")
        handler.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
