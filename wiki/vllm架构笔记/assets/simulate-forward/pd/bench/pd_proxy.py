#!/usr/bin/env python3
"""Minimal P/D (prefill/decode disaggregation) proxy for `vllm bench serve`.

Exposes ONE OpenAI-compatible endpoint in front of an XpYd deployment and
implements the two-step vLLM disaggregated protocol that `vllm bench serve`
does not speak:

  1. forward the request to a prefill instance with
     ``kv_transfer_params={"do_remote_decode": true, "do_remote_prefill": false}``,
     ``max_tokens=1`` and ``stream=false``; read back ``kv_transfer_params``
     (remote_block_ids / remote_engine_id / remote_host / remote_port ...).
  2. forward the original request to a decode instance with those params
     (prefill's response already carries ``do_remote_prefill=true``) and
     stream the SSE response back to the client unchanged.

Usage:
  python tmp/pd_proxy.py --prefill 127.0.0.1:18001 --decode 127.0.0.1:18002 --port 18000
  python tmp/pd_proxy.py --prefill h1:8000 h2:8000 --decode d1:8000 d2:8000   # 2P2D

Then:
  vllm bench serve --base-url http://127.0.0.1:18000 ...
"""

import argparse
import asyncio
import itertools
import json
import logging
import sys
import time

from aiohttp import ClientSession, ClientTimeout, TCPConnector, web

log = logging.getLogger("pd_proxy")


class PDProxy:
    def __init__(self, prefills: list[str], decodes: list[str], verbose: bool = False):
        self.prefills = prefills
        self.decodes = decodes
        self._p = itertools.cycle(prefills)
        self._d = itertools.cycle(decodes)
        self.verbose = verbose
        self.session: ClientSession | None = None

    # ---------------------------------------------------------------- lifecycle
    async def on_startup(self, app: web.Application) -> None:
        self.session = ClientSession(
            timeout=ClientTimeout(total=None),
            connector=TCPConnector(limit=0, ttl_dns_cache=300),
        )

    async def on_cleanup(self, app: web.Application) -> None:
        if self.session is not None:
            await self.session.close()

    # ------------------------------------------------------------------ helpers
    async def _prefill(self, path: str, body: dict) -> tuple[dict, float]:
        pbody = dict(body)
        # max_tokens=1: the prefill leg must not generate; it only produces KV.
        pbody.pop("stream_options", None)
        pbody["stream"] = False
        pbody["max_tokens"] = 1
        if pbody.get("max_completion_tokens") is not None:
            pbody["max_completion_tokens"] = 1
        pbody["kv_transfer_params"] = {
            "do_remote_decode": True,
            "do_remote_prefill": False,
        }
        url = f"http://{next(self._p)}{path}"
        t0 = time.perf_counter()
        assert self.session is not None
        async with self.session.post(url, json=pbody) as r:
            text = await r.text()
            status = r.status
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if status != 200:
            raise web.HTTPBadGateway(
                text=f"prefill {url} -> {status}: {text[:800]}"
            )
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise web.HTTPBadGateway(text=f"prefill returned non-JSON: {text[:400]}") from e
        kv = data.get("kv_transfer_params")
        if not kv:
            raise web.HTTPBadGateway(
                text=(
                    "prefill response has no kv_transfer_params — check that the "
                    "prefill instance runs with a kv_producer role and "
                    "--simulation-config kv_transfer_timing"
                )
            )
        return kv, elapsed_ms

    async def _handle(self, request: web.Request, path: str) -> web.StreamResponse:
        try:
            body = await request.json()
        except json.JSONDecodeError as e:
            raise web.HTTPBadRequest(text=f"invalid JSON body: {e}") from e

        kv, prefill_ms = await self._prefill(path, body)

        dbody = dict(body)
        dbody["kv_transfer_params"] = kv
        # prefill already consumed one token; keep the client-visible total right.
        for key in ("max_completion_tokens", "max_tokens"):
            if dbody.get(key):
                dbody[key] = max(1, int(dbody[key]) - 1)
                break

        decode_url = f"http://{next(self._d)}{path}"
        if self.verbose:
            log.info(
                "prefill %.1fms engine=%s blocks=%s -> %s",
                prefill_ms,
                str(kv.get("remote_engine_id"))[:8],
                len(kv.get("remote_block_ids") or []),
                decode_url,
            )

        resp = web.StreamResponse(
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "X-Prefill-Ms": f"{prefill_ms:.1f}",
            }
        )
        await resp.prepare(request)

        assert self.session is not None
        async with self.session.post(decode_url, json=dbody) as r:
            if r.status != 200:
                err = await r.text()
                payload = json.dumps({"error": {"message": err[:800]}})
                await resp.write(f"data: {payload}\n\n".encode())
                await resp.write_eof()
                return resp
            async for chunk in r.content.iter_any():
                await resp.write(chunk)
        await resp.write_eof()
        return resp

    async def completions(self, request: web.Request) -> web.StreamResponse:
        return await self._handle(request, "/v1/completions")

    async def chat_completions(self, request: web.Request) -> web.StreamResponse:
        return await self._handle(request, "/v1/chat/completions")

    async def passthrough(self, request: web.Request) -> web.Response:
        """Forward /v1/models, /tokenize, /detokenize to the first prefill."""
        url = f"http://{self.prefills[0]}{request.path_qs}"
        payload = await request.read()
        headers = {}
        if request.headers.get("Content-Type"):
            headers["Content-Type"] = request.headers["Content-Type"]
        assert self.session is not None
        async with self.session.request(
            request.method, url, data=payload, headers=headers
        ) as r:
            data = await r.read()
            return web.Response(
                status=r.status,
                body=data,
                content_type=r.content_type or "application/json",
            )

    async def health(self, request: web.Request) -> web.Response:
        return web.json_response(
            {"status": "ok", "prefill": self.prefills, "decode": self.decodes}
        )

    def build_app(self) -> web.Application:
        app = web.Application(client_max_size=64 * 1024**2)
        app.on_startup.append(self.on_startup)
        app.on_cleanup.append(self.on_cleanup)
        app.router.add_post("/v1/completions", self.completions)
        app.router.add_post("/v1/chat/completions", self.chat_completions)
        app.router.add_route("*", "/v1/models", self.passthrough)
        app.router.add_route("*", "/tokenize", self.passthrough)
        app.router.add_route("*", "/detokenize", self.passthrough)
        app.router.add_get("/health", self.health)
        return app


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prefill", nargs="+", required=True, help="host:port [...]")
    p.add_argument("--decode", nargs="+", required=True, help="host:port [...]")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=18000)
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    proxy = PDProxy(args.prefill, args.decode, verbose=args.verbose)
    print(
        f"[pd_proxy] {len(args.prefill)}P{len(args.decode)}D "
        f"prefill={args.prefill} decode={args.decode} "
        f"listening on http://{args.host}:{args.port}",
        flush=True,
    )
    web.run_app(
        proxy.build_app(),
        host=args.host,
        port=args.port,
        print=None,
        access_log=None,
    )


if __name__ == "__main__":
    main()
