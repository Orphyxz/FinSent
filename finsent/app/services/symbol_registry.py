from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SymbolRecord:
    internal_id: str
    ticker: str
    display_name: str
    exchange: str
    provider_symbol: str
    ui_label: str
    sector: str
    isin: str | None = None
    polygon_symbol: str | None = None
    kite_instrument_key: str | None = None
    listing_exchange: str | None = None

    @property
    def market(self) -> str:
        return "US" if self.exchange == "US" else "INDIA"

    @property
    def currency(self) -> str:
        return "USD" if self.exchange == "US" else "INR"

    @property
    def yahoo_symbol(self) -> str:
        if self.exchange == "NSE":
            return f"{self.ticker}.NS"
        if self.exchange == "BSE":
            return f"{self.ticker}.BO"
        return self.ticker

    def symbol_for(self, provider: str) -> str:
        target = provider.lower().strip()
        if target == "kite":
            return self.provider_symbol
        if target == "polygon":
            return self.polygon_symbol or self.ticker
        if target in {"yahoo", "yfinance", "fallback_web"}:
            return self.yahoo_symbol
        return self.ticker if self.exchange == "US" else self.provider_symbol


def _us(ticker: str, name: str, sector: str, listing_exchange: str = "NYSE") -> SymbolRecord:
    return SymbolRecord(
        f"us-{ticker.lower().replace('.', '-')}", ticker, name, "US", ticker,
        f"{ticker} - {name} | US", sector, polygon_symbol=ticker, listing_exchange=listing_exchange,
    )


def _nse(ticker: str, name: str, sector: str) -> SymbolRecord:
    return SymbolRecord(
        f"nse-{ticker.lower()}", ticker, name, "NSE", f"NSE:{ticker}",
        f"{ticker} - {name} | NSE", sector, listing_exchange="NSE",
    )


def _bse(ticker: str, name: str, sector: str) -> SymbolRecord:
    return SymbolRecord(
        f"bse-{ticker.lower()}", ticker, name, "BSE", f"BSE:{ticker}",
        f"{ticker} - {name} | BSE", sector, listing_exchange="BSE",
    )


# Curated metadata is loaded eagerly; prices and news remain strictly on demand.
US_SYMBOLS: tuple[SymbolRecord, ...] = (
    _us("AAPL", "Apple", "Technology", "NASDAQ"),
    _us("MSFT", "Microsoft", "Technology", "NASDAQ"),
    _us("NVDA", "NVIDIA", "Technology", "NASDAQ"),
    _us("AMZN", "Amazon", "Consumer", "NASDAQ"),
    _us("GOOGL", "Alphabet", "Technology", "NASDAQ"),
    _us("META", "Meta Platforms", "Technology", "NASDAQ"),
    _us("TSLA", "Tesla", "Consumer", "NASDAQ"),
    _us("AVGO", "Broadcom Inc.", "Technology", "NASDAQ"),
    _us("AMD", "Advanced Micro Devices", "Technology", "NASDAQ"),
    _us("INTC", "Intel Corp.", "Technology", "NASDAQ"),
    _us("ORCL", "Oracle Corp.", "Technology"),
    _us("CRM", "Salesforce Inc.", "Technology"),
    _us("ADBE", "Adobe Inc.", "Technology", "NASDAQ"),
    _us("NFLX", "Netflix Inc.", "Communication Services", "NASDAQ"),
    _us("QCOM", "Qualcomm Inc.", "Technology", "NASDAQ"),
    _us("CSCO", "Cisco Systems Inc.", "Technology", "NASDAQ"),
    _us("IBM", "IBM", "Technology"),
    _us("TXN", "Texas Instruments", "Technology", "NASDAQ"),
    _us("AMAT", "Applied Materials", "Technology", "NASDAQ"),
    _us("MU", "Micron Technology", "Technology", "NASDAQ"),
    _us("NOW", "ServiceNow Inc.", "Technology"),
    _us("INTU", "Intuit Inc.", "Technology", "NASDAQ"),
    _us("PANW", "Palo Alto Networks", "Technology", "NASDAQ"),
    _us("PLTR", "Palantir Technologies", "Technology", "NASDAQ"),
    _us("JPM", "JPMorgan", "Finance"),
    _us("BAC", "Bank of America", "Financials"),
    _us("GS", "Goldman Sachs", "Financials"),
    _us("MS", "Morgan Stanley", "Financials"),
    _us("WFC", "Wells Fargo", "Financials"),
    _us("C", "Citigroup Inc.", "Financials"),
    _us("SCHW", "Charles Schwab", "Financials"),
    _us("BLK", "BlackRock Inc.", "Financials"),
    _us("AXP", "American Express", "Financials"),
    _us("V", "Visa Inc.", "Financials"),
    _us("MA", "Mastercard Inc.", "Financials"),
    _us("COF", "Capital One Financial", "Financials"),
    _us("USB", "U.S. Bancorp", "Financials"),
    _us("PNC", "PNC Financial Services", "Financials"),
    _us("UNH", "UnitedHealth Group", "Health Care"),
    _us("JNJ", "Johnson & Johnson", "Health Care"),
    _us("LLY", "Eli Lilly and Co.", "Health Care"),
    _us("PFE", "Pfizer Inc.", "Health Care"),
    _us("MRK", "Merck & Co.", "Health Care"),
    _us("ABBV", "AbbVie Inc.", "Health Care"),
    _us("TMO", "Thermo Fisher Scientific", "Health Care"),
    _us("ABT", "Abbott Laboratories", "Health Care"),
    _us("DHR", "Danaher Corp.", "Health Care"),
    _us("BMY", "Bristol Myers Squibb", "Health Care"),
    _us("AMGN", "Amgen Inc.", "Health Care", "NASDAQ"),
    _us("GILD", "Gilead Sciences", "Health Care", "NASDAQ"),
    _us("CVS", "CVS Health", "Health Care"),
    _us("CI", "Cigna Group", "Health Care"),
    _us("ISRG", "Intuitive Surgical", "Health Care", "NASDAQ"),
    _us("MDT", "Medtronic plc", "Health Care"),
    _us("WMT", "Walmart Inc.", "Consumer Staples"),
    _us("COST", "Costco Wholesale", "Consumer Staples", "NASDAQ"),
    _us("HD", "Home Depot", "Consumer Discretionary"),
    _us("MCD", "McDonald's Corp.", "Consumer Discretionary"),
    _us("NKE", "Nike Inc.", "Consumer Discretionary"),
    _us("LOW", "Lowe's Companies", "Consumer Discretionary"),
    _us("SBUX", "Starbucks Corp.", "Consumer Discretionary", "NASDAQ"),
    _us("TGT", "Target Corp.", "Consumer Staples"),
    _us("TJX", "TJX Companies", "Consumer Discretionary"),
    _us("BKNG", "Booking Holdings", "Consumer Discretionary", "NASDAQ"),
    _us("CMG", "Chipotle Mexican Grill", "Consumer Discretionary"),
    _us("KO", "Coca-Cola Co.", "Consumer Staples"),
    _us("PEP", "PepsiCo Inc.", "Consumer Staples", "NASDAQ"),
    _us("PG", "Procter & Gamble", "Consumer Staples"),
    _us("PM", "Philip Morris International", "Consumer Staples"),
    _us("MO", "Altria Group", "Consumer Staples"),
    _us("CL", "Colgate-Palmolive", "Consumer Staples"),
    _us("MDLZ", "Mondelez International", "Consumer Staples", "NASDAQ"),
    _us("KMB", "Kimberly-Clark", "Consumer Staples"),
    _us("DIS", "Walt Disney Co.", "Communication Services"),
    _us("CMCSA", "Comcast Corp.", "Communication Services", "NASDAQ"),
    _us("T", "AT&T Inc.", "Communication Services"),
    _us("VZ", "Verizon Communications", "Communication Services"),
    _us("TMUS", "T-Mobile US", "Communication Services", "NASDAQ"),
    _us("XOM", "Exxon Mobil", "Energy"),
    _us("CVX", "Chevron Corp.", "Energy"),
    _us("COP", "ConocoPhillips", "Energy"),
    _us("SLB", "SLB", "Energy"),
    _us("EOG", "EOG Resources", "Energy"),
    _us("OXY", "Occidental Petroleum", "Energy"),
    _us("CAT", "Caterpillar Inc.", "Industrials"),
    _us("BA", "Boeing Co.", "Industrials"),
    _us("GE", "GE Aerospace", "Industrials"),
    _us("HON", "Honeywell International", "Industrials", "NASDAQ"),
    _us("UPS", "United Parcel Service", "Industrials"),
    _us("RTX", "RTX Corp.", "Industrials"),
    _us("LMT", "Lockheed Martin", "Industrials"),
    _us("DE", "Deere & Co.", "Industrials"),
    _us("UNP", "Union Pacific", "Industrials"),
    _us("FDX", "FedEx Corp.", "Industrials"),
    _us("MMM", "3M Co.", "Industrials"),
    _us("ETN", "Eaton Corp.", "Industrials"),
    _us("NEE", "NextEra Energy", "Utilities"),
    _us("DUK", "Duke Energy", "Utilities"),
    _us("SO", "Southern Co.", "Utilities"),
    _us("AEP", "American Electric Power", "Utilities", "NASDAQ"),
    _us("EXC", "Exelon Corp.", "Utilities", "NASDAQ"),
    _us("AMT", "American Tower", "Real Estate"),
    _us("PLD", "Prologis Inc.", "Real Estate"),
    _us("EQIX", "Equinix Inc.", "Real Estate", "NASDAQ"),
    _us("SPG", "Simon Property Group", "Real Estate"),
    _us("O", "Realty Income", "Real Estate"),
    _us("LIN", "Linde plc", "Materials", "NASDAQ"),
    _us("APD", "Air Products and Chemicals", "Materials"),
    _us("SHW", "Sherwin-Williams", "Materials"),
    _us("FCX", "Freeport-McMoRan", "Materials"),
    _us("NEM", "Newmont Corp.", "Materials"),
)


INDIA_SYMBOLS: tuple[SymbolRecord, ...] = (
    _nse("RELIANCE", "Reliance Industries Ltd.", "Energy"),
    _nse("TCS", "Tata Consultancy Services", "Technology"),
    _nse("HDFCBANK", "HDFC Bank Ltd.", "Financials"),
    _nse("ICICIBANK", "ICICI Bank Ltd.", "Financials"),
    _nse("INFY", "Infosys Ltd.", "Technology"),
    _nse("SBIN", "State Bank of India", "Financials"),
    _nse("BHARTIARTL", "Bharti Airtel Ltd.", "Communication Services"),
    _nse("ITC", "ITC Ltd.", "Consumer Staples"),
    _nse("LT", "Larsen & Toubro Ltd.", "Industrials"),
    _nse("HINDUNILVR", "Hindustan Unilever Ltd.", "Consumer Staples"),
    _nse("KOTAKBANK", "Kotak Mahindra Bank", "Financials"),
    _nse("AXISBANK", "Axis Bank Ltd.", "Financials"),
    _nse("BAJFINANCE", "Bajaj Finance Ltd.", "Financials"),
    _nse("MARUTI", "Maruti Suzuki India", "Consumer Discretionary"),
    _nse("M&M", "Mahindra & Mahindra", "Consumer Discretionary"),
    _nse("SUNPHARMA", "Sun Pharmaceutical Industries", "Health Care"),
    _nse("TITAN", "Titan Company Ltd.", "Consumer Discretionary"),
    _nse("ULTRACEMCO", "UltraTech Cement", "Materials"),
    _nse("ASIANPAINT", "Asian Paints Ltd.", "Materials"),
    _nse("NTPC", "NTPC Ltd.", "Utilities"),
    _nse("POWERGRID", "Power Grid Corp. of India", "Utilities"),
    _nse("TATAMOTORS", "Tata Motors Ltd.", "Consumer Discretionary"),
    _nse("TATASTEEL", "Tata Steel Ltd.", "Materials"),
    _nse("JSWSTEEL", "JSW Steel Ltd.", "Materials"),
    _nse("ONGC", "Oil and Natural Gas Corp.", "Energy"),
    _nse("COALINDIA", "Coal India Ltd.", "Energy"),
    _nse("ADANIENT", "Adani Enterprises", "Industrials"),
    _nse("ADANIPORTS", "Adani Ports and SEZ", "Industrials"),
    _nse("WIPRO", "Wipro Ltd.", "Technology"),
    _nse("HCLTECH", "HCL Technologies", "Technology"),
    _nse("TECHM", "Tech Mahindra", "Technology"),
    _nse("DRREDDY", "Dr. Reddy's Laboratories", "Health Care"),
    _nse("CIPLA", "Cipla Ltd.", "Health Care"),
    _nse("APOLLOHOSP", "Apollo Hospitals Enterprise", "Health Care"),
    _nse("GRASIM", "Grasim Industries", "Materials"),
    _nse("NESTLEIND", "Nestle India", "Consumer Staples"),
    _nse("EICHERMOT", "Eicher Motors", "Consumer Discretionary"),
    _nse("HEROMOTOCO", "Hero MotoCorp", "Consumer Discretionary"),
    _nse("BAJAJFINSV", "Bajaj Finserv", "Financials"),
    _nse("BAJAJ-AUTO", "Bajaj Auto", "Consumer Discretionary"),
    _nse("BEL", "Bharat Electronics", "Industrials"),
    _nse("TRENT", "Trent Ltd.", "Consumer Discretionary"),
    _nse("SHRIRAMFIN", "Shriram Finance", "Financials"),
    _nse("SBILIFE", "SBI Life Insurance", "Financials"),
    _nse("HDFCLIFE", "HDFC Life Insurance", "Financials"),
    _nse("BRITANNIA", "Britannia Industries", "Consumer Staples"),
    _nse("HINDALCO", "Hindalco Industries", "Materials"),
    _nse("INDUSINDBK", "IndusInd Bank", "Financials"),
    _nse("MAXHEALTH", "Max Healthcare Institute", "Health Care"),
    _nse("JIOFIN", "Jio Financial Services", "Financials"),
    _nse("DMART", "Avenue Supermarts", "Consumer Staples"),
    _nse("PIDILITIND", "Pidilite Industries", "Materials"),
    _nse("DLF", "DLF Ltd.", "Real Estate"),
    _nse("SIEMENS", "Siemens Ltd.", "Industrials"),
    _nse("HAL", "Hindustan Aeronautics", "Industrials"),
    _nse("IOC", "Indian Oil Corp.", "Energy"),
    _nse("BPCL", "Bharat Petroleum Corp.", "Energy"),
    _nse("DIVISLAB", "Divi's Laboratories", "Health Care"),
    _nse("DABUR", "Dabur India", "Consumer Staples"),
    _nse("GODREJCP", "Godrej Consumer Products", "Consumer Staples"),
    _nse("TVSMOTOR", "TVS Motor Company", "Consumer Discretionary"),
    _nse("ZYDUSLIFE", "Zydus Lifesciences", "Health Care"),
)


BSE_SYMBOLS: tuple[SymbolRecord, ...] = (
    _bse("RELIANCE", "Reliance Industries Ltd.", "Energy"),
    _bse("TCS", "Tata Consultancy Services", "Technology"),
    _bse("INFY", "Infosys Ltd.", "Technology"),
    _bse("HDFCBANK", "HDFC Bank Ltd.", "Financials"),
    _bse("SBIN", "State Bank of India", "Financials"),
)


SYMBOLS: tuple[SymbolRecord, ...] = US_SYMBOLS + INDIA_SYMBOLS + BSE_SYMBOLS


class SymbolRegistry:
    def __init__(self, symbols: tuple[SymbolRecord, ...] = SYMBOLS) -> None:
        self._symbols = symbols
        self._by_provider_symbol = {symbol.provider_symbol.upper(): symbol for symbol in symbols}
        self._by_exchange_ticker = {(symbol.exchange, symbol.ticker): symbol for symbol in symbols}

    def list_symbols(self, exchange: str | None = None) -> list[SymbolRecord]:
        if exchange is None:
            return list(self._symbols)
        target = exchange.upper().strip()
        if target == "ALL":
            return list(self._symbols)
        if target == "INDIA":
            return [symbol for symbol in self._symbols if symbol.exchange == "NSE"]
        return [symbol for symbol in self._symbols if symbol.exchange == target]

    def search(self, query: str = "", market: str | None = None, limit: int = 250) -> list[SymbolRecord]:
        terms = [term for term in query.upper().strip().split() if term]
        symbols = self.list_symbols(market or "ALL")
        if terms:
            symbols = [
                symbol
                for symbol in symbols
                if all(term in f"{symbol.ticker} {symbol.display_name} {symbol.exchange} {symbol.sector}".upper() for term in terms)
            ]
        return symbols[: max(0, limit)]

    def get(self, exchange: str, ticker: str) -> SymbolRecord | None:
        return self._by_exchange_ticker.get((exchange.upper().strip(), ticker.upper().strip()))

    def get_by_provider_symbol(self, provider_symbol: str) -> SymbolRecord | None:
        return self._by_provider_symbol.get(provider_symbol.upper().strip())

    def resolve_any(self, raw_value: str) -> SymbolRecord | None:
        candidate = raw_value.upper().strip()
        if ":" in candidate:
            return self._by_provider_symbol.get(candidate)
        if candidate.endswith(".NS"):
            return self.get("NSE", candidate[:-3])
        if candidate.endswith(".BO"):
            return self.get("BSE", candidate[:-3])
        us_symbol = self.get("US", candidate)
        if us_symbol is not None:
            return us_symbol
        for exchange in ("NSE", "BSE"):
            symbol = self.get(exchange, candidate)
            if symbol is not None:
                return symbol
        return None


registry = SymbolRegistry()
