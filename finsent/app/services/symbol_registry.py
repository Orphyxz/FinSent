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
        if target in {"yahoo", "yahoo_chart", "yfinance", "fallback_web"}:
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
    # Expanded coverage: additional large caps across every GICS sector.
    _us("ADI", "Analog Devices", "Technology", "NASDAQ"),
    _us("KLAC", "KLA Corp.", "Technology", "NASDAQ"),
    _us("LRCX", "Lam Research", "Technology", "NASDAQ"),
    _us("MRVL", "Marvell Technology", "Technology", "NASDAQ"),
    _us("ANET", "Arista Networks", "Technology"),
    _us("SNPS", "Synopsys Inc.", "Technology", "NASDAQ"),
    _us("CDNS", "Cadence Design Systems", "Technology", "NASDAQ"),
    _us("CRWD", "CrowdStrike Holdings", "Technology", "NASDAQ"),
    _us("FTNT", "Fortinet Inc.", "Technology", "NASDAQ"),
    _us("ZS", "Zscaler Inc.", "Technology", "NASDAQ"),
    _us("NET", "Cloudflare Inc.", "Technology"),
    _us("SNOW", "Snowflake Inc.", "Technology"),
    _us("DDOG", "Datadog Inc.", "Technology", "NASDAQ"),
    _us("WDAY", "Workday Inc.", "Technology", "NASDAQ"),
    _us("DELL", "Dell Technologies", "Technology"),
    _us("HPQ", "HP Inc.", "Technology"),
    _us("SMCI", "Super Micro Computer", "Technology", "NASDAQ"),
    _us("UBER", "Uber Technologies", "Industrials"),
    _us("ABNB", "Airbnb Inc.", "Consumer Discretionary", "NASDAQ"),
    _us("CHTR", "Charter Communications", "Communication Services", "NASDAQ"),
    _us("EA", "Electronic Arts", "Communication Services", "NASDAQ"),
    _us("TTWO", "Take-Two Interactive", "Communication Services", "NASDAQ"),
    _us("WBD", "Warner Bros. Discovery", "Communication Services", "NASDAQ"),
    _us("GM", "General Motors", "Consumer Discretionary"),
    _us("F", "Ford Motor Co.", "Consumer Discretionary"),
    _us("RIVN", "Rivian Automotive", "Consumer Discretionary", "NASDAQ"),
    _us("LULU", "Lululemon Athletica", "Consumer Discretionary", "NASDAQ"),
    _us("ROST", "Ross Stores", "Consumer Discretionary", "NASDAQ"),
    _us("ORLY", "O'Reilly Automotive", "Consumer Discretionary", "NASDAQ"),
    _us("AZO", "AutoZone Inc.", "Consumer Discretionary"),
    _us("MAR", "Marriott International", "Consumer Discretionary", "NASDAQ"),
    _us("HLT", "Hilton Worldwide", "Consumer Discretionary"),
    _us("YUM", "Yum! Brands", "Consumer Discretionary"),
    _us("EBAY", "eBay Inc.", "Consumer Discretionary", "NASDAQ"),
    _us("KHC", "Kraft Heinz", "Consumer Staples", "NASDAQ"),
    _us("GIS", "General Mills", "Consumer Staples"),
    _us("KDP", "Keurig Dr Pepper", "Consumer Staples", "NASDAQ"),
    _us("MNST", "Monster Beverage", "Consumer Staples", "NASDAQ"),
    _us("STZ", "Constellation Brands", "Consumer Staples"),
    _us("HSY", "Hershey Co.", "Consumer Staples"),
    _us("KR", "Kroger Co.", "Consumer Staples"),
    _us("EL", "Estee Lauder", "Consumer Staples"),
    _us("SPGI", "S&P Global", "Financials"),
    _us("MCO", "Moody's Corp.", "Financials"),
    _us("ICE", "Intercontinental Exchange", "Financials"),
    _us("CME", "CME Group", "Financials", "NASDAQ"),
    _us("PYPL", "PayPal Holdings", "Financials", "NASDAQ"),
    _us("XYZ", "Block Inc.", "Financials"),
    _us("COIN", "Coinbase Global", "Financials", "NASDAQ"),
    _us("HOOD", "Robinhood Markets", "Financials", "NASDAQ"),
    _us("BX", "Blackstone Inc.", "Financials"),
    _us("KKR", "KKR & Co.", "Financials"),
    _us("PGR", "Progressive Corp.", "Financials"),
    _us("CB", "Chubb Ltd.", "Financials"),
    _us("AIG", "American International Group", "Financials"),
    _us("MET", "MetLife Inc.", "Financials"),
    _us("VRTX", "Vertex Pharmaceuticals", "Health Care", "NASDAQ"),
    _us("REGN", "Regeneron Pharmaceuticals", "Health Care", "NASDAQ"),
    _us("ZTS", "Zoetis Inc.", "Health Care"),
    _us("SYK", "Stryker Corp.", "Health Care"),
    _us("BSX", "Boston Scientific", "Health Care"),
    _us("ELV", "Elevance Health", "Health Care"),
    _us("HCA", "HCA Healthcare", "Health Care"),
    _us("HUM", "Humana Inc.", "Health Care"),
    _us("MRNA", "Moderna Inc.", "Health Care", "NASDAQ"),
    _us("BIIB", "Biogen Inc.", "Health Care", "NASDAQ"),
    _us("PSX", "Phillips 66", "Energy"),
    _us("MPC", "Marathon Petroleum", "Energy"),
    _us("VLO", "Valero Energy", "Energy"),
    _us("KMI", "Kinder Morgan", "Energy"),
    _us("WMB", "Williams Companies", "Energy"),
    _us("HAL", "Halliburton Co.", "Energy"),
    _us("NOC", "Northrop Grumman", "Industrials"),
    _us("GD", "General Dynamics", "Industrials"),
    _us("LHX", "L3Harris Technologies", "Industrials"),
    _us("WM", "Waste Management", "Industrials"),
    _us("CSX", "CSX Corp.", "Industrials", "NASDAQ"),
    _us("NSC", "Norfolk Southern", "Industrials"),
    _us("EMR", "Emerson Electric", "Industrials"),
    _us("ITW", "Illinois Tool Works", "Industrials"),
    _us("PH", "Parker-Hannifin", "Industrials"),
    _us("DAL", "Delta Air Lines", "Industrials"),
    _us("UAL", "United Airlines Holdings", "Industrials", "NASDAQ"),
    _us("D", "Dominion Energy", "Utilities"),
    _us("SRE", "Sempra", "Utilities"),
    _us("PCG", "PG&E Corp.", "Utilities"),
    _us("XEL", "Xcel Energy", "Utilities", "NASDAQ"),
    _us("CCI", "Crown Castle", "Real Estate"),
    _us("PSA", "Public Storage", "Real Estate"),
    _us("WELL", "Welltower Inc.", "Real Estate"),
    _us("DLR", "Digital Realty Trust", "Real Estate"),
    _us("DOW", "Dow Inc.", "Materials"),
    _us("NUE", "Nucor Corp.", "Materials"),
    _us("ECL", "Ecolab Inc.", "Materials"),
    _us("DD", "DuPont de Nemours", "Materials"),
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
    # Tata Motors demerged in 2025; TATAMOTORS no longer resolves on providers.
    _nse("TMPV", "Tata Motors Passenger Vehicles", "Consumer Discretionary"),
    _nse("TMCV", "Tata Motors Ltd. (Commercial Vehicles)", "Industrials"),
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
    # Expanded coverage: Nifty Next 50 and liquid mid caps.
    _nse("BANKBARODA", "Bank of Baroda", "Financials"),
    _nse("PNB", "Punjab National Bank", "Financials"),
    _nse("CANBK", "Canara Bank", "Financials"),
    _nse("UNIONBANK", "Union Bank of India", "Financials"),
    _nse("IDFCFIRSTB", "IDFC First Bank", "Financials"),
    _nse("FEDERALBNK", "Federal Bank", "Financials"),
    _nse("AUBANK", "AU Small Finance Bank", "Financials"),
    _nse("CHOLAFIN", "Cholamandalam Investment", "Financials"),
    _nse("MUTHOOTFIN", "Muthoot Finance", "Financials"),
    _nse("BAJAJHLDNG", "Bajaj Holdings & Investment", "Financials"),
    _nse("ICICIGI", "ICICI Lombard General Insurance", "Financials"),
    _nse("ICICIPRULI", "ICICI Prudential Life Insurance", "Financials"),
    _nse("LICI", "Life Insurance Corp. of India", "Financials"),
    _nse("PFC", "Power Finance Corp.", "Financials"),
    _nse("RECLTD", "REC Ltd.", "Financials"),
    _nse("IRFC", "Indian Railway Finance Corp.", "Financials"),
    _nse("HDFCAMC", "HDFC Asset Management", "Financials"),
    _nse("PAYTM", "One 97 Communications (Paytm)", "Financials"),
    _nse("POLICYBZR", "PB Fintech (Policybazaar)", "Financials"),
    _nse("LTM", "LTM Ltd. (LTIMindtree)", "Technology"),
    _nse("PERSISTENT", "Persistent Systems", "Technology"),
    _nse("COFORGE", "Coforge Ltd.", "Technology"),
    _nse("MPHASIS", "Mphasis Ltd.", "Technology"),
    _nse("OFSS", "Oracle Financial Services Software", "Technology"),
    _nse("KPITTECH", "KPIT Technologies", "Technology"),
    _nse("TATAELXSI", "Tata Elxsi", "Technology"),
    _nse("NAUKRI", "Info Edge (Naukri)", "Communication Services"),
    _nse("ETERNAL", "Eternal Ltd. (Zomato)", "Consumer Discretionary"),
    _nse("NYKAA", "FSN E-Commerce (Nykaa)", "Consumer Discretionary"),
    _nse("INDUSTOWER", "Indus Towers", "Communication Services"),
    _nse("IDEA", "Vodafone Idea", "Communication Services"),
    _nse("LUPIN", "Lupin Ltd.", "Health Care"),
    _nse("AUROPHARMA", "Aurobindo Pharma", "Health Care"),
    _nse("TORNTPHARM", "Torrent Pharmaceuticals", "Health Care"),
    _nse("ALKEM", "Alkem Laboratories", "Health Care"),
    _nse("MANKIND", "Mankind Pharma", "Health Care"),
    _nse("BIOCON", "Biocon Ltd.", "Health Care"),
    _nse("FORTIS", "Fortis Healthcare", "Health Care"),
    _nse("TATACONSUM", "Tata Consumer Products", "Consumer Staples"),
    _nse("MARICO", "Marico Ltd.", "Consumer Staples"),
    _nse("COLPAL", "Colgate-Palmolive (India)", "Consumer Staples"),
    _nse("VBL", "Varun Beverages", "Consumer Staples"),
    _nse("UNITDSPR", "United Spirits", "Consumer Staples"),
    _nse("PAGEIND", "Page Industries", "Consumer Discretionary"),
    _nse("JUBLFOOD", "Jubilant FoodWorks", "Consumer Discretionary"),
    _nse("HAVELLS", "Havells India", "Consumer Discretionary"),
    _nse("VOLTAS", "Voltas Ltd.", "Consumer Discretionary"),
    _nse("DIXON", "Dixon Technologies", "Consumer Discretionary"),
    _nse("INDHOTEL", "Indian Hotels Co.", "Consumer Discretionary"),
    _nse("IRCTC", "Indian Railway Catering & Tourism", "Consumer Discretionary"),
    _nse("MOTHERSON", "Samvardhana Motherson", "Consumer Discretionary"),
    _nse("BOSCHLTD", "Bosch Ltd.", "Consumer Discretionary"),
    _nse("MRF", "MRF Ltd.", "Consumer Discretionary"),
    _nse("ASHOKLEY", "Ashok Leyland", "Industrials"),
    _nse("ABB", "ABB India", "Industrials"),
    _nse("BHEL", "Bharat Heavy Electricals", "Industrials"),
    _nse("CUMMINSIND", "Cummins India", "Industrials"),
    _nse("POLYCAB", "Polycab India", "Industrials"),
    _nse("CGPOWER", "CG Power and Industrial Solutions", "Industrials"),
    _nse("MAZDOCK", "Mazagon Dock Shipbuilders", "Industrials"),
    _nse("INDIGO", "InterGlobe Aviation (IndiGo)", "Industrials"),
    _nse("CONCOR", "Container Corp. of India", "Industrials"),
    _nse("GMRAIRPORT", "GMR Airports", "Industrials"),
    _nse("GAIL", "GAIL (India) Ltd.", "Utilities"),
    _nse("HINDPETRO", "Hindustan Petroleum", "Energy"),
    _nse("TATAPOWER", "Tata Power Co.", "Utilities"),
    _nse("JSWENERGY", "JSW Energy", "Utilities"),
    _nse("NHPC", "NHPC Ltd.", "Utilities"),
    _nse("ADANIGREEN", "Adani Green Energy", "Utilities"),
    _nse("ADANIPOWER", "Adani Power", "Utilities"),
    _nse("ADANIENSOL", "Adani Energy Solutions", "Utilities"),
    _nse("VEDL", "Vedanta Ltd.", "Materials"),
    _nse("HINDZINC", "Hindustan Zinc", "Materials"),
    _nse("JINDALSTEL", "Jindal Steel", "Materials"),
    _nse("SAIL", "Steel Authority of India", "Materials"),
    _nse("NMDC", "NMDC Ltd.", "Materials"),
    _nse("AMBUJACEM", "Ambuja Cements", "Materials"),
    _nse("SHREECEM", "Shree Cement", "Materials"),
    _nse("SRF", "SRF Ltd.", "Materials"),
    _nse("PIIND", "PI Industries", "Materials"),
    _nse("UPL", "UPL Ltd.", "Materials"),
    _nse("GODREJPROP", "Godrej Properties", "Real Estate"),
    _nse("LODHA", "Lodha Developers", "Real Estate"),
    _nse("OBEROIRLTY", "Oberoi Realty", "Real Estate"),
    _nse("PRESTIGE", "Prestige Estates Projects", "Real Estate"),
    _nse("PHOENIXLTD", "Phoenix Mills", "Real Estate"),
)


BSE_SYMBOLS: tuple[SymbolRecord, ...] = (
    _bse("RELIANCE", "Reliance Industries Ltd.", "Energy"),
    _bse("TCS", "Tata Consultancy Services", "Technology"),
    _bse("INFY", "Infosys Ltd.", "Technology"),
    _bse("HDFCBANK", "HDFC Bank Ltd.", "Financials"),
    _bse("SBIN", "State Bank of India", "Financials"),
    _bse("ICICIBANK", "ICICI Bank Ltd.", "Financials"),
    _bse("BHARTIARTL", "Bharti Airtel Ltd.", "Communication Services"),
    _bse("ITC", "ITC Ltd.", "Consumer Staples"),
    _bse("LT", "Larsen & Toubro Ltd.", "Industrials"),
    _bse("HINDUNILVR", "Hindustan Unilever Ltd.", "Consumer Staples"),
    _bse("KOTAKBANK", "Kotak Mahindra Bank", "Financials"),
    _bse("AXISBANK", "Axis Bank Ltd.", "Financials"),
    _bse("BAJFINANCE", "Bajaj Finance Ltd.", "Financials"),
    _bse("MARUTI", "Maruti Suzuki India", "Consumer Discretionary"),
    _bse("SUNPHARMA", "Sun Pharmaceutical Industries", "Health Care"),
    _bse("TITAN", "Titan Company Ltd.", "Consumer Discretionary"),
    _bse("WIPRO", "Wipro Ltd.", "Technology"),
    _bse("HCLTECH", "HCL Technologies", "Technology"),
    _bse("NTPC", "NTPC Ltd.", "Utilities"),
    _bse("TATASTEEL", "Tata Steel Ltd.", "Materials"),
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
