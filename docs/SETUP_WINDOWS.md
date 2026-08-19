# Windows Setup

Use this from a clean checkout.

```powershell
git clone https://github.com/Orphyxz/FinSent.git
cd FinSent
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-research.txt
```

If you have `FinSent-data-bundle.zip`, extract its contents directly into the repository root so the resulting tree can contain:

```text
FinSent/
  archive/
  data/
  output/
  finsent/
  docs/
  requirements.txt
```

Create a root `.env` and follow [ALPACA_SETUP.md](ALPACA_SETUP.md):

```text
ALPACA_API_KEY=
ALPACA_API_SECRET=
ALPACA_DATA_BASE_URL=https://data.alpaca.markets
ALPACA_FEED=iex
```

Run preflight:

```powershell
python -m finsent.scripts.demo_preflight
```

Start the dashboard:

```powershell
python -m finsent.scripts.run_dashboard
```

Open:

```text
http://127.0.0.1:8050/
```

Do not copy a `.venv` from another machine. Recreate it locally.
