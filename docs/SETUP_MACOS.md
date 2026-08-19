# macOS Setup

Use this from a clean checkout.

```bash
git clone https://github.com/Orphyxz/FinSent.git
cd FinSent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-research.txt
```

Do not copy a Windows `.venv` to macOS. Python packages with native wheels, especially `torch`, should be installed fresh on the Mac.

If you have `FinSent-data-bundle.zip`, extract its contents directly into the repository root. The expected shape is:

```text
FinSent/
  archive/
  data/
  output/
  finsent/
  docs/
  requirements.txt
```

Useful troubleshooting commands:

```bash
pwd
ls
ls data
ls archive/v1 | head
```

Create a root `.env` and follow [ALPACA_SETUP.md](ALPACA_SETUP.md):

```text
ALPACA_API_KEY=
ALPACA_API_SECRET=
ALPACA_DATA_BASE_URL=https://data.alpaca.markets
ALPACA_FEED=iex
```

Run preflight:

```bash
python -m finsent.scripts.demo_preflight
```

Start the dashboard:

```bash
python -m finsent.scripts.run_dashboard
```

Open:

```text
http://127.0.0.1:8050/
```
