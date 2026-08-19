# Alpaca Setup

FinSent uses Alpaca as the primary live US market-data and current-news provider for the demo.

## Steps

1. Create or log in to an Alpaca account.
2. Create a Paper Trading account/workspace.
3. Generate an API key pair.
4. Never paste real keys into Git, screenshots, chat logs, or documentation.
5. Create a `.env` file in the repository root.
6. Add placeholders in this exact shape, replacing only the values after `=`:

```text
ALPACA_API_KEY=
ALPACA_API_SECRET=
ALPACA_DATA_BASE_URL=https://data.alpaca.markets
ALPACA_FEED=iex
```

Use `https://paper-api.alpaca.markets/v2` only for trading/account endpoints. FinSent's market-data provider calls the Alpaca data API, so `ALPACA_DATA_BASE_URL` should normally be `https://data.alpaca.markets`.

7. Restart FinSent after editing `.env`.
8. Run:

```bash
python -m finsent.scripts.demo_preflight
```

9. Confirm the dashboard System Status panel reports Alpaca configured/healthy when live data is available.

## IEX Limitation

`ALPACA_FEED=iex` uses Alpaca Basic/IEX data. It is useful for a student demo, but it is not the full consolidated SIP market feed. During market close, the app may show latest available prices rather than current live ticks.

## Safety

`.env` is ignored by Git. Do not rename it into a tracked file or include it in a data bundle.
