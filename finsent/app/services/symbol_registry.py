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


SYMBOLS: tuple[SymbolRecord, ...] = (
    SymbolRecord("us-aapl", "AAPL", "Apple", "US", "AAPL", "AAPL | Apple | US", "Technology", polygon_symbol="AAPL"),
    SymbolRecord("us-amzn", "AMZN", "Amazon", "US", "AMZN", "AMZN | Amazon | US", "Consumer", polygon_symbol="AMZN"),
    SymbolRecord("us-msft", "MSFT", "Microsoft", "US", "MSFT", "MSFT | Microsoft | US", "Technology", polygon_symbol="MSFT"),
    SymbolRecord("us-nvda", "NVDA", "NVIDIA", "US", "NVDA", "NVDA | NVIDIA | US", "Technology", polygon_symbol="NVDA"),
    SymbolRecord("us-meta", "META", "Meta Platforms", "US", "META", "META | Meta Platforms | US", "Technology", polygon_symbol="META"),
    SymbolRecord("us-googl", "GOOGL", "Alphabet", "US", "GOOGL", "GOOGL | Alphabet | US", "Technology", polygon_symbol="GOOGL"),
    SymbolRecord("us-tsla", "TSLA", "Tesla", "US", "TSLA", "TSLA | Tesla | US", "Consumer", polygon_symbol="TSLA"),
    SymbolRecord("us-jpm", "JPM", "JPMorgan", "US", "JPM", "JPM | JPMorgan | US", "Finance", polygon_symbol="JPM"),
    SymbolRecord("nse-reliance", "RELIANCE", "Reliance Industries", "NSE", "NSE:RELIANCE", "RELIANCE | Reliance Industries | NSE", "Energy"),
    SymbolRecord("nse-tcs", "TCS", "Tata Consultancy Services", "NSE", "NSE:TCS", "TCS | Tata Consultancy Services | NSE", "Technology"),
    SymbolRecord("nse-infy", "INFY", "Infosys", "NSE", "NSE:INFY", "INFY | Infosys | NSE", "Technology"),
    SymbolRecord("nse-hdfcbank", "HDFCBANK", "HDFC Bank", "NSE", "NSE:HDFCBANK", "HDFCBANK | HDFC Bank | NSE", "Finance"),
    SymbolRecord("nse-icicibank", "ICICIBANK", "ICICI Bank", "NSE", "NSE:ICICIBANK", "ICICIBANK | ICICI Bank | NSE", "Finance"),
    SymbolRecord("nse-sbin", "SBIN", "State Bank of India", "NSE", "NSE:SBIN", "SBIN | State Bank of India | NSE", "Finance"),
    SymbolRecord("nse-itc", "ITC", "ITC", "NSE", "NSE:ITC", "ITC | ITC | NSE", "Consumer"),
    SymbolRecord("bse-reliance", "RELIANCE", "Reliance Industries", "BSE", "BSE:RELIANCE", "RELIANCE | Reliance Industries | BSE", "Energy"),
    SymbolRecord("bse-tcs", "TCS", "Tata Consultancy Services", "BSE", "BSE:TCS", "TCS | Tata Consultancy Services | BSE", "Technology"),
    SymbolRecord("bse-infy", "INFY", "Infosys", "BSE", "BSE:INFY", "INFY | Infosys | BSE", "Technology"),
    SymbolRecord("bse-hdfcbank", "HDFCBANK", "HDFC Bank", "BSE", "BSE:HDFCBANK", "HDFCBANK | HDFC Bank | BSE", "Finance"),
    SymbolRecord("bse-sbin", "SBIN", "State Bank of India", "BSE", "BSE:SBIN", "SBIN | State Bank of India | BSE", "Finance"),
)


class SymbolRegistry:
    def __init__(self, symbols: tuple[SymbolRecord, ...] = SYMBOLS) -> None:
        self._symbols = symbols
        self._by_provider_symbol = {symbol.provider_symbol.upper(): symbol for symbol in symbols}
        self._by_exchange_ticker = {(symbol.exchange, symbol.ticker): symbol for symbol in symbols}

    def list_symbols(self, exchange: str | None = None) -> list[SymbolRecord]:
        if exchange is None:
            return list(self._symbols)
        target = exchange.upper().strip()
        return [symbol for symbol in self._symbols if symbol.exchange == target]

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
