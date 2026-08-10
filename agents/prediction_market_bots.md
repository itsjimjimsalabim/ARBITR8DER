# Prediction Market Bots — Research Reference (Kalshi + Polymarket)

**Scope:** Existing prediction-market trading bots, systems, SDKs, and academic evidence on whether any claim consistent safe profits. Maps findings onto the Kalshi 15-min BTC/ETH binaries desk (`KXBTC15M-*` / `KXETH15M-*`) and the planned Rust Polymarket 5-min desk (`polymarket_desk`).

**Verified as of:** 2026-08-10. All repo names/star counts pulled live from GitHub topic pages (`prediction-market`, `kalshi`). Star counts are popularity, not profitability.

---

## 1. Bottom Line

1. **No public repo shows an audited, live-verified consistent-profit record.** The highest-star "bots" are marketing/SEO projects; claimed P&L is almost always paper/simulation.
2. **The two real, replicable edges with academic backing are:**
   - **Favorite-longshot bias (FLB) on Kalshi:** contracts priced >70¢ earn statistically significant *small positive* post-fee returns; contracts ≤10¢ lose >60% of capital. Average contract on Kalshi returns ≈ −20%. → The profit is on the *favorite side*, not the longshot side.
   - **Persistent cross-venue arbitrage (Kalshi ↔ Polymarket):** statistically significant price gaps persist (p<.001) because capital lockup, fiat↔crypto friction, and regulatory segmentation block elimination. Max single-day gap: 24.07% (legislative), 6.35% (monetary policy).
3. **Makers beat Takers.** Kalshi's quote-driven microstructure means posted-limit-order liquidity providers earn higher returns than price-takers. Supports market-making / spread-capture strategies over market-order directional flow.
4. **Directional ML on short-window BTC/ETH binaries has no published edge proof.** Open-source repos that trade them (weather/5-min bot, BTC-arb repos) either run paper-only or show small/undisclosed results.

---

## 2. Academic / Empirical Evidence

| Paper | Venue / Date | Finding | Relevance |
|---|---|---|---|
| "Makers and Takers: The Economics of the Kalshi Prediction Market" — Bürgi, Deng, Whelan (UCD + GWU) | GWU CER Working Paper 2026-001, Feb 2026 | Transaction-level data: 46,282 contracts / 12,403 events / 313,972 prices (2021→Apr 2025). Prices informative, accuracy rises near close. **FLB:** ≤10¢ lose >60%; >70¢ statistically significant small positive post-fee returns; overall avg return ≈ −20%. Takers worse than Makers. Bias slowly diminishing. Fee then: `$0.07·P(1−P)` per contract to Takers only. | Directly about our venue. Validates buying high-priced favorites near close (short-window binaries settle at near-certainty); warns against longshot chasing. |
| "From Forecasting Tool to Financial Asset: Evidence of Persistent Arbitrage in Prediction Markets" — David Krause (Marquette) | SSRN 6905683, Jun 2026 | Persistent Kalshi↔Polymarket arbitrage; both results p<.001; max single-day 24.07% (legislative) / 6.35% (monetary policy). Structural barriers (capital lockup, fiat↔crypto friction, regulatory segmentation) prevent elimination. | Directly validates the cross-venue "buy basket <$1" arb thesis. |
| "The Temporal Evolution of Mispricing in Prediction Markets" | Finance Research Letters, 2019 | FLB persists; level evolves with time-to-close; consistent with herding. | Mispricing timing matters — last-day favorites most mispriced. |

Secondary coverage (unverified vendor/blogs, flag as such):
- Indexbox: "40m in free money" Polymarket mispricing claims — references the Krause-style research; blog, not primary evidence.
- `polymarkettrader.com/blog/prediction-markets-academic-research-trading-insights` — accuracy studies + trader checklist roundup.
- `botforkalshi.com/blog/open-source-kalshi-bot-ecosystem` — "30+ projects (2026)" roundup; **vendor blog, conflict-of-interest**.

---

## 3. Repo & Software Table (curated, most relevant first)

### 3a. Data & Backtest Infrastructure

| Repo | Stars | Lang | What it is | Notes / evidence |
|---|---|---|---|---|
| `Jon-Becker/prediction-market-analysis` | 3.7k | Python | Collection + analysis framework; **largest public Kalshi + Polymarket market/trade dataset** | Critical for backtesting our 15-min strategies. Not a trading bot. |
| `betcode-org/flumine` | 240 | Python | Battle-tested betting-trading framework (Betfair ecosystem); now tagged kalshi/polymarket | Mature, event-driven, proven in production sports betting. |

### 3b. Unified SDKs (CCXT-for-prediction-markets)

| Repo | Stars | Lang | What it is | Notes |
|---|---|---|---|---|
| `pmxt-dev/pmxt` | 2.1k | TypeScript | "CCXT for prediction markets" — unified trading API across Polymarket, Kalshi, more | Active (Jul 2026); swap exchange class, keep logic. |
| `guzus/dr-manhattan` | 196 | Python/Jupyter | CCXT-style unified API; market-making focus | Precursor lineage to the two dr-manhattan ports below. |
| `gtg7784/dr-manhattan-ts` | 55 | TypeScript | CCXT-style unified API (Polymarket, Limitless, Opinion, Kalshi, Predict.fun) | |
| `gtg7784/dr-manhattan-rust` | 53 | Rust | Same unified API, **Rust** | Directly relevant to the Rust `polymarket_desk` plan. |
| `ashercn97/predmarket` | 94 | Python | Unified SDK (Kalshi + Polymarket) | Simpler alternative. |

### 3c. Rust Clients (Polymarket desk performance reference)

| Repo | Stars | What it is | Notes |
|---|---|---|---|
| `floor-licker/polyfill-rs` | 220 | "Fastest Polymarket Rust client", V2-native | Benchmarks (Jun 2026): 4.2× faster than official Python client; ~69.6µs per 1000 orderbook ops; zero-alloc warmed hot paths; HTTP/2 tuning + connection pre-warming. |
| `Polymarket/rs-clob-client-v2` | — | Official Polymarket Rust SDK (`polymarket_client_sdk_v2`) | Use before rolling our own; polyfill-rs benchmarks against it. |

### 3d. Strategy Bots (the "claims" tier)

| Repo | Stars | Lang | Strategy | Profitability evidence | Risk / trust |
|---|---|---|---|---|---|
| `suislanchez/polymarket-kalshi-weather-bot` | 584 | Python | BTC 5-min microstructure (RSI/momentum/VWAP/SMA, Coinbase/Kraken/Binance) + weather ensembles (GFS 31-member, KXHIGH) | Topic claim "highest profits $1.8k" — **README states simulation/paper only**. Edge gates: 2% BTC, 8% weather; 15% fractional Kelly; $300 daily-loss breaker. | Paper-only; useful as architecture reference for our BTC 5-min desk. |
| `alsk1992/CloddsBot` | 652 | TS | AI agent across 1000+ markets (PM + CEX + Solana), "agent commerce" | No audited P&L | Marketing-heavy; built on Claude (our toolchain, but no track record). |
| `ryanfrigo/kalshi-ai-trading-bot` | 570 | Python | AI-automated Kalshi strategies + risk mgmt + portfolio optimization | No audited P&L | Toolkit, not a verified performer. |
| `OctagonAI/kalshi-trading-bot-cli` | 370 | TS | AI-native CLI: deep research → probability estimate → edge vs live book → Kelly sizing, 5-gate risk engine | No audited P&L | Interesting risk-engine design. |
| `HarrierOnChain/Prediction-Markets-Trading-Bot-Toolkits` | 373 | Rust | 10 strategies on one engine: **BTC 5m/15m/1hr arb (~42ms FAK)**, cross-market arb, resolution sniper, spread farming, orderbook imbalance, market making, copy trading, whale signal | 7 live venues; dry-run default; **managed/copy service is paper-mode only** until custody+audit | Closest match to our Rust plan; study their venue adapters + safety layer (circuit breaker, depth guard). |
| `YichengYang-Ethan/oracle3` | 265 | Python | Wang-Transform pricing on 291K+ contracts, Kelly sizing, Kalshi+Polymarket+Solana DFlow | Paper-traded; 633 tests | Research-grade; strong testing culture. |
| `CarlosIbCu/polymarket-kalshi-btc-arbitrage-bot` | 234 | Python | Real-time BTC **1-hour** cross-venue arb (Poly down + Kalshi yes etc., basket <$1) | No P&L published; includes arb-thesis doc | Directly validates our cross-venue concept; monitoring-only in practice. |
| `braedonsaunders/homerun` | 168 | Python | Platform: 25+ strategies, backtest → paper → live, copy trading, AI scoring | No audited P&L | Broad but unproven. |
| `Drakkar-Software/OctoBot-Prediction-Market` | 105 | Python | OctoBot extension: free copy-trading + arbitrage | No audited P&L | Established OSS bot brand (crypto), PM add-on newer. |
| `Benjam1nCup/Polymarket-trading-bot-python-V2` | 129 | Python | Arb / market-making / TWAP | None published | SEO-keyword-saturated repo description; low credibility. |
| `ThePolyscripts/polymarket-trading-bot-pack` | 138 | — | Polymarket 5-min / 15-min market markers | None published | Same SEO-spam pattern; treat as low-trust. |
| `Jon-Becker/prediction-market-analysis` (see 3a) | 3.7k | Python | — | — | Reuse for data, not for strategy. |

### 3e. Client Libraries (Kalshi auth / data reference)

| Repo | Stars | Lang | What it is | Notes |
|---|---|---|---|---|
| `arshka/pykalshi` | 120 | Python | Unofficial Kalshi REST+WS client | RSA-PSS auth reference. |
| `Reddimus/kalshi-cpp` | 97 | C++23 | Kalshi SDK: typed REST + WS, RSA-PSS, `std::expected` | Latency-conscious alternative if we ever leave Python. |
| `TexasCoding/kalshi-python-sdk` (`kalshi-sdk` on PyPI, v7.1.0) | 3 | Python | Spec-first MIT SDK: 102 ops / 19 resources, sync+async parity, FIX + 12 WS channels, `Decimal` price safety | Only high-grade community Kalshi SDK found. |

---

## 4. Official SDKs & API References

### Polymarket
- **New unified SDK (recommended):** `Polymarket/py-sdk`. The original `py-clob-client` is **archived / no longer functional** — do not build on it.
- CLOB v2 clients (all support full CLOB incl. auth): `py-clob-client-v2` (Python), `@polymarket/clob-client-v2` (TS), `Polymarket/rs-clob-client-v2` → crate `polymarket_client_sdk_v2` (Rust).
- Gasless trading relayer: `py-builder-relayer-client` (TS: `@polymarket/builder-relayer-client`).
- Docs: `docs.polymarket.com` (also `llms.txt` index). Gamma market-data API: `gamma-api.polymarket.com`.

### Kalshi
- SDK overview: `docs.kalshi.com/sdks/overview` — Python `kalshi_python_sync` / `kalshi_python_async`, TypeScript SDK on PyPI/npm.
- **Source of truth (per Kalshi):** REST `docs.kalshi.com/openapi.yaml` + WebSocket `docs.kalshi.com/asyncapi.yaml`. SDKs lag the API; generate our own client for production control.
- Endpoints: prod `https://api.elections.kalshi.com/trade-api/v2`, demo `https://demo-api.kalshi.co/trade-api/v2`.
- Latency: REST ~50–200ms; **FIX protocol available for lower-latency order entry** (relevant to our <5ms execution goal). Public endpoints ~10 rps; authenticated ~5 rps (per Alphascope guide; confirm against docs).
- Official repo: `Kalshi/exchange-infra` (older `kalshi-python`, proprietary license).

---

## 5. Strategy Taxonomy — What Actually Shows Edge

| Strategy | Evidence quality | Structure | Risk |
|---|---|---|---|
| **Cross-venue arb (basket <$1)** | Academic (Krause 2026, p<.001) | Buy Yes on one venue + No on the other for same event, total <$1 | Thin, latency+fees, capital lockup across venues, resolution-timing risk |
| **Buy favorites near close (>70¢, >50¢)** | Academic (GWU 2026): small positive post-fee returns for high-price contracts | Hold near-certainty contracts to settlement | Low per-trade edge; needs volume; competitive |
| **Resolution sniper (95¢→$1)** | Anecdotal (Harrier etc.); consistent with GWU >70¢ finding | Scan near-resolved contracts, hold to payout | Sniper-style competition, thin books |
| **Market making / spread capture** | GWU: Makers earn more than Takers | Post two-sided GTD orders, skew inventory | Inventory + adverse selection; needs depth guard |
| **Directional ML on 15-min/5-min binaries** | No published proof | Our dual-horizon ML + <5ms execution | Untested edge; GWU's −20% avg return shows most participants lose |
| **Copy trading / on-chain whale signal** | Anecdotal | Mirror proven wallets; 3–30s lead via block subscription | Tracking error, mirror-lag, wallet quality |

---

## 6. Mapping to Our Desks

**Kalshi 15-min desk (KXBTC15M-* / KXETH15M-*):**
- GWU FLB says: our edge should be *favorite-side* (buy near-certainty contracts close to settlement), not longshot-chasing. Score every trade against post-fee break-even using `$0.07·P(1−P)`-style fee math (fees changed Apr 2025 — verify current maker/taker schedule).
- Execution goal <5ms → consider Kalshi **FIX** over REST (50–200ms).
- Data for backtesting: `Jon-Becker/prediction-market-analysis` dataset (largest public Kalshi+Polymarket trade history).
- Reference architecture: `suislanchez` bot (BTC 5-min signals, Kelly 15%, daily-loss breaker) and `OctagonAI` CLI (5-gate risk engine).

**Polymarket 5-min Rust desk (`polymarket_desk`):**
- Start from official `rs-clob-client-v2`; benchmark against `floor-licker/polyfill-rs` (4.2× faster than official Python; zero-alloc orderbook hot paths).
- Study `HarrierOnChain` adapter stack (BTC 5m/15m/1hr arb, ~42ms FAK, circuit breaker, depth guard) — closest prior art for a Rust 5-min desk.
- Cross-venue arb with Kalshi is academically supported (Krause); implement as basket-cost scan first, monitor-only (like `CarlosIbCu` bot), before live size.

---

## 7. Risk & Skepticism Notes

1. GitHub stars ≠ profitability. Topic pages for these repos are SEO-saturated (repeated keyword descriptions); treat star counts as marketing signal.
2. The only repos publishing specific dollar claims (e.g. weather bot "$1.8k") explicitly state **simulation/paper trading**.
3. `HarrierOnChain` managed/copy service is in **paper mode** until custody + security audit + licensing. No OSS project we found custody-lives real PM capital with an audited record.
4. Academic data says most participants lose ~20% on average (GWU). Safe-profit claims without arb/fee/edge accounting should be assumed wrong.
5. Fee schedule matters more than signal: post-Apr-2025 maker fees on Kalshi change the maker-vs-taker calculus from the GWU sample period. Re-verify before copying any GWU-derived sizing.

---

## 8. Sources

- GWU CER WP 2026-001 (PDF, 45pp): `www2.gwu.edu/~forcpgm/2026-001.pdf` (extracted via pypdf; abstract + sec.1–3 read in full)
- Krause, SSRN 6905683 abstract: `papers.ssrn.com/.../6905683`
- EconPapers record + RePEc for GWU paper
- GitHub topics: `github.com/topics/prediction-market` (383 repos), `github.com/topics/kalshi` (311 repos)
- `docs.polymarket.com/developers/CLOB/clients`, `docs.kalshi.com/sdks/overview`
- Repo READMEs fetched raw: CarlosIbCu BTC-arb, HarrierOnChain toolkits, suislanchez weather bot, floor-licker polyfill-rs
- Secondary (vendor/blog, flagged): botforkalshi.com ecosystem roundup; indexbox.io Polymarket mispricing article; polymarkettrader.com research roundup
