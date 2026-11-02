# FinPulse

**Live site:** https://niraj0805.github.io/finpulse-data/

## What's here
| Path | What it is |
|---|---|
| `index.html` | FinPulse, a live finance news dashboard, password-protected (AES-256 encrypted; members only). It pulls 23 free RSS sources (Indian markets, global markets, central banks, commodities, crypto) through free CORS relays and adds impact scoring, sentiment, a breaking strip, watchlist alerts and a TradingView ticker. |
| `scripts/technicals.py` | A backup price engine. It downloads daily NSE prices (yfinance) for the Nifty 200 plus `config/symbols.txt`, then computes RSI, MACD, 20/50/200-DMA, ATR, support/resistance, breakouts and returns. |
| `.github/workflows/technicals.yml` | Runs the engine at 7:45 am and 4:10 pm IST on weekdays and commits the results to `data/`. |
| `data/` | `technicals.json`, `market.json` and `closes.json`, read by the FinPulse Research Desk agents. |

Headlines link to the original publishers. Sentiment and impact scores are keyword heuristics. Nothing here is investment advice.
