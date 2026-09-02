"""Tests for the Kalshi REST orderbook snapshot fallback.

The authenticated Kalshi WebSocket may be unavailable (e.g. 401 from a
rotated API key), but the public REST ``/markets/{ticker}/orderbook``
endpoint needs no auth. These tests lock in the dollars-to-cents parsing
and the NOR bid/ask derivation used to feed the snapshot merger so paper
trading can still get a ``kalshi_midpoint_cents``.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from kalshi_desk_package.data_sources.kalshi_rest_market_discovery_client import (
    KalshiRestMarketDiscoveryClient,
)


def _make_client() -> KalshiRestMarketDiscoveryClient:
    return KalshiRestMarketDiscoveryClient(api_key=None)


def _ok_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    return resp


def test_parses_nor_book_into_bid_ask():
    payload = {
        "orderbook": {
            "yes": [["0.55", "100.00"], ["0.54", "80.00"]],
            "no": [["0.40", "50.00"], ["0.39", "20.00"]],
            "seq": 42,
        }
    }
    mock_http = AsyncMock()
    mock_http.get.return_value = _ok_response(payload)

    book = asyncio.run(_make_client().get_orderbook_snapshot("KXBTC15M-TEST", client=mock_http))

    assert book is not None
    assert book["ticker"] == "KXBTC15M-TEST"
    assert book["yes_bid"] == 55
    assert book["no_bid"] == 40
    assert book["yes_ask"] == 60  # 100 - no_bid(40)
    assert book["no_ask"] == 45  # 100 - yes_bid(55)
    assert book["last_sequence"] == 42
    assert (book["yes_bid"] + book["yes_ask"]) // 2 == 57  # midpoint


def test_empty_book_returns_none_levels():
    payload = {"orderbook": {"yes": [], "no": [], "seq": None}}
    mock_http = AsyncMock()
    mock_http.get.return_value = _ok_response(payload)

    book = asyncio.run(_make_client().get_orderbook_snapshot("KXBTC15M-TEST", client=mock_http))

    assert book is not None
    assert book["yes_bid"] is None
    assert book["yes_ask"] is None
    assert book["no_bid"] is None
    assert book["no_ask"] is None


def test_non_200_returns_none():
    resp = MagicMock()
    resp.status_code = 403
    mock_http = AsyncMock()
    mock_http.get.return_value = resp

    book = asyncio.run(_make_client().get_orderbook_snapshot("KXBTC15M-TEST", client=mock_http))
    assert book is None
