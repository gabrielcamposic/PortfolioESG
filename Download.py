# ----------------------------------------------------------- #
#                           Libraries                         #
# ----------------------------------------------------------- #

import yfinance as yfin
import pandas as pd
import os
import requests
from datetime import datetime, timedelta
import holidays
import random
import time
import json
from fake_useragent import UserAgent
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# ----------------------------------------------------------- #
#                       Global variables                      #
# ----------------------------------------------------------- #

choose_server = 'test'  # either 'prod' or 'test'
DEBUG = False

server_paths = {
    'prod': {
        'findata': '~/PortfolioESG_Data/findata/',
        'findb': '~/PortfolioESG_Data/findb/',
        'tickers_file': '~/PortfolioESG_Data/Tickers.txt',
        'log_file_path': '~/PortfolioESG_Prod/Logs/Ticker_download.log',
        'web_log_path': '/var/www/html/progress.json',
    },
    'test': {
        'findata': '~/Documents/Prog/PortfolioESG_Data/findata/',
        'findb': '~/Documents/Prog/PortfolioESG_Data/findb/',
        'tickers_file': '~/Documents/Prog/PortfolioESG_Data/Tickers.txt',
        'log_file_path': '~/Documents/Prog/PortfolioESG_Prod/Logs/Ticker_download.log',
        'web_log_path': '~/Documents/Prog/PortfolioESG_Prod/html/progress.json',
    }
}

# Expand user paths for the selected server
if choose_server not in server_paths:
    raise ValueError("Invalid server choice. Please choose either 'prod' or 'test'.")
paths = {key: os.path.expanduser(value) for key, value in server_paths[choose_server].items()}

findata = paths['findata']
findb = paths['findb']
tickers_file = paths['tickers_file']
log_file_path = paths['log_file_path']
web_log_path = paths['web_log_path']

db_filename = "StockDataDB.csv"
db_filepath = os.path.join(findb, db_filename)
years = 10

# Fallback list of user agents
FALLBACK_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 12.3; rv:118.0) Gecko/20100101 Firefox/118.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:115.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36 Edg/118.0.2088.76",
    "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1"
]

USER_AGENTS = FALLBACK_USER_AGENTS  # Ensure always defined
ua = None  # To avoid NameError if refresh logic tries to use ua

# ----------------------------------------------------------- #
#                           Classes                           #
# ----------------------------------------------------------- #

class Logger:
    def __init__(self, log_path, flush_interval=10, web_log_path=None):
        self.log_path = log_path
        self.web_log_path = web_log_path  # Path to the web-accessible log file
        self.messages = []
        self.flush_interval = flush_interval
        self.log_count = 0
        self.web_data = {}  # Data to be written to the web log file

    def log(self, message, web_data=None):
        """Logs messages and optionally updates the web log file."""
        print(message)  # Console output
        self.messages.append(message)
        self.log_count += 1

        # Update web log file if web_data is provided
        if web_data and self.web_log_path:
            self.web_data.update(web_data)
            with open(self.web_log_path, 'w') as web_file:
                json.dump(self.web_data, web_file, indent=4)
                web_file.flush()            # Ensure data is flushed from buffer
                os.fsync(web_file.fileno()) # Force write to disk (good for web access)

        if self.log_count % self.flush_interval == 0:
            self.flush()

    def flush(self):
        """Write logs to file in bulk and clear memory."""
        if self.messages:
            with open(self.log_path, 'a') as file:
                file.write("\n".join(self.messages) + "\n")
            self.messages = []  # Clear memory

logger = Logger(
    log_path=log_file_path,
    web_log_path=web_log_path  # Shared JSON file for progress monitoring
)

# ----------------------------------------------------------- #
#                        Basic Functions                      #
# ----------------------------------------------------------- #

# Function to fetch dynamic user agents
def fetch_dynamic_user_agents():
    try:
        # Example API for fetching user agents (replace with a reliable source if needed)
        response = requests.get("https://useragentapi.com/api/v4/json/f7afb3be4db1a4fd3f67cea1c225fadc/user_agents")
        response.raise_for_status()  # Raise an error for bad responses (4xx or 5xx)
        data = response.json()

        # Extract user agents from the JSON response
        user_agents = [agent['user_agent'] for agent in data.get('data', [])]

        if user_agents:
            logger.log(f"✅ Successfully fetched {len(user_agents)} user agents from the online source.")
            return user_agents
    except Exception as e:
        logger.log(f"⚠️ Failed to fetch dynamic user agents: {e}")
        return None

# Function to fetch proxies using proxybroker
# def fetch_proxies(limit=10):
#     proxies = []
#     for _ in range(limit):
#         try:
#             proxy = FreeProxy().get()
#             proxies.append({
#                 "http": proxy,
#                 "https": proxy
#             })
#         except Exception as e:
#             logger.log(f"⚠️ Failed to fetch proxy: {e}")
#     logger.log(f"✅ Successfully fetched {len(proxies)} proxies using free-proxy.")
#     return proxies

def fetch_proxies_from_public_list(limit=10):
    proxies = []
    try:
        response = requests.get("https://www.proxyscan.io/api/proxy?limit=20&type=http,https")
        response.raise_for_status()
        data = response.json()
        for proxy in data[:limit]:
            ip = proxy.get("Ip")
            port = proxy.get("Port")
            if ip and port:
                proxies.append({
                    "http": f"http://{ip}:{port}",
                    "https": f"https://{ip}:{port}"
                })
    except Exception as e:
        logger.log(f"⚠️ Failed to fetch proxies from public list: {e}")
    return proxies  # Return an empty list if fetching fails

def fetch_combined_proxy_list(limit=20):
    proxies = []
    try:
        # Source 1: proxyscrape.com
        response1 = requests.get("https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=1000&country=all&ssl=all&anonymity=all")
        if response1.ok:
            for line in response1.text.strip().split("\n"):
                if ":" in line:
                    proxies.append({
                        "http": f"http://{line}",
                        "https": f"https://{line}"
                    })

        # Source 2: proxyscan.io
        response2 = requests.get("https://www.proxyscan.io/api/proxy?limit=20&type=http,https")
        if response2.ok:
            for proxy in response2.json():
                ip = proxy.get("Ip")
                port = proxy.get("Port")
                if ip and port:
                    proxies.append({
                        "http": f"http://{ip}:{port}",
                        "https": f"https://{ip}:{port}"
                    })

    except Exception as e:
        logger.log(f"⚠️ Error fetching proxies from one or more sources: {e}")

    return proxies[:limit]

# Function to rotate User-Agent and Proxy
def rotate_user_agent_and_proxy(session, user_agents, proxies):
    if user_agents:
        random_user_agent = random.choice(user_agents)
        session.headers.update({"User-Agent": random_user_agent})
        if DEBUG:
            logger.log(f"Rotated User-Agent: {random_user_agent}")
    else:
        if DEBUG:
            logger.log("⚠️ No user agents available for rotation.")

    if proxies:
        random_proxy = random.choice(proxies)
        session.proxies.update(random_proxy)
        if DEBUG:
            logger.log(f"Rotated Proxy: {random_proxy}")
    else:
        if DEBUG:
            logger.log("⚠️ No proxies available for rotation.")

def get_previous_business_day():
    today = datetime.today()
    sp_holidays = holidays.Brazil(years=today.year, subdiv='SP')

    if today.weekday() == 0:  # Monday
        previous_business_day = today - timedelta(days=3)
    else:
        previous_business_day = today - timedelta(days=1)

    while previous_business_day.weekday() >= 5 or previous_business_day in sp_holidays:
        previous_business_day -= timedelta(days=1)

    return previous_business_day.strftime('%Y-%m-%d')

def get_sao_paulo_holidays(year):
    from dateutil.easter import easter
    holiday_dict = {}

    # National + SP holidays
    sp_holidays = holidays.Brazil(years=year, subdiv='SP')
    for date, name in sp_holidays.items():
        holiday_dict[date] = name

    # Fixed market-specific dates
    fixed_holidays = {
        datetime(year, 1, 25): "Aniversário de São Paulo",
        datetime(year, 7, 9): "Data Magna SP",
        datetime(year, 11, 20): "Consciência Negra",
        datetime(year, 12, 24): "Véspera de Natal",
        datetime(year, 12, 31): "Véspera de Ano Novo",
    }

    # Floating based on Easter
    easter_sunday = easter(year)
    floating_holidays = {
        easter_sunday - timedelta(days=48): "Carnaval (Segunda-feira)",
        easter_sunday - timedelta(days=47): "Carnaval (Terça-feira)",
        easter_sunday - timedelta(days=2): "Sexta-feira Santa",
        easter_sunday + timedelta(days=60): "Corpus Christi",
    }

    # Market closures
    special_market_closures = {
        datetime(2016, 12, 30): "Encerramento B3",
        datetime(2022, 12, 30): "Encerramento B3",
        datetime(2023, 12, 29): "Encerramento B3",
    }

    all_custom = {**fixed_holidays, **floating_holidays, **special_market_closures}
    holiday_dict.update(all_custom)

    return holiday_dict

def get_missing_dates(ticker, findata, start_date, end_date):
    """
    Return only business days (excluding weekends and holidays) that are missing for a given ticker.
    """
    ticker_folder = os.path.join(findata, ticker)
    if not os.path.exists(ticker_folder):
        logger.log(f"📂 No folder found for {ticker}. All dates are missing.")
        ticker_holidays = holidays.Brazil(years=range(start_date.year, end_date.year + 1), subdiv='SP')
        ticker_holidays.update(get_sao_paulo_holidays(start_date.year))
        business_days = pd.bdate_range(start=start_date, end=end_date, freq='C', holidays=ticker_holidays)
        return business_days.to_pydatetime().tolist()

    # Step 1: Get existing dates from CSV filenames
    existing_dates = []
    for file in os.listdir(ticker_folder):
        if file.startswith(f"StockData_{ticker}_") and file.endswith(".csv"):
            try:
                file_date = file.split("_")[-1].replace(".csv", "")
                existing_dates.append(datetime.strptime(file_date, "%Y-%m-%d").date())
            except ValueError:
                logger.log(f"⚠️ Skipping file with invalid date format: {file}")
                continue

    # Step 2: Build full business date range (excluding holidays/weekends)
    all_years = list(range(start_date.year, end_date.year + 1))
    br_holidays = {}

    for year in all_years:
        custom = get_sao_paulo_holidays(year)
        br_holidays.update(custom)

    business_days = pd.bdate_range(start=start_date, end=end_date, freq='C', holidays=br_holidays)

    # Step 3: Find missing dates (as datetime, not .date)
    missing_dates = [dt for dt in business_days if dt.date() not in existing_dates]

    return missing_dates

def read_tickers_from_file(file_path):
    with open(file_path, 'r') as f:
        tickers = [line.strip() for line in f.readlines() if line.strip()]
    return tickers

def save_ticker_data_to_csv(ticker, data, findata):
    """
    Save the fetched data for a ticker to individual CSVs in the findata folder (one file per date).
    """
    # Ensure the findata folder for the ticker exists
    ticker_folder = os.path.join(findata, ticker)
    if not os.path.exists(ticker_folder):
        os.makedirs(ticker_folder)

    # Validate the data
    if data.empty:
        logger.log(f"⚠️ No data to save for ticker: {ticker}. DataFrame is empty.")
        return

    # Make sure 'Date' is a datetime object
    data['Date'] = pd.to_datetime(data['Date'], errors='coerce')
    data = data.dropna(subset=['Date'])

    # Save one CSV per unique date
    for date, group in data.groupby(data['Date'].dt.date):
        file_name = f"StockData_{ticker}_{date}.csv"
        file_path = os.path.join(ticker_folder, file_name)

        try:
            group.to_csv(file_path, index=False)
            logger.log(f"✅ Data for {ticker} on {date} saved to {file_path}")
        except Exception as e:
            logger.log(f"⚠️ Error saving data for {ticker} on {date}: {e}")

def debug_check_dates_against_holidays(dates_to_check):
    from datetime import datetime
    import holidays

    checked_dates = [datetime.strptime(d, "%Y-%m-%d").date() for d in dates_to_check]
    all_years = set(d.year for d in checked_dates)

    # Correct merge into a flat dict, not HolidayBase
    br_holidays = {}
    for year in all_years:
        national = holidays.Brazil(years=year, subdiv='SP')
        custom = get_sao_paulo_holidays(year)

        for day, name in national.items():
            br_holidays[day] = name
        for day, name in custom.items():
            br_holidays[day] = name

    print("📆 Checking which missing dates are in the holiday calendar...\n")
    for d in checked_dates:
        holiday = br_holidays.get(d)
        if holiday:
            print(f"✅ {d} is a holiday: {holiday}")
        else:
            print(f"❌ {d} is NOT marked as a holiday")

def download_and_append(tickers, findata, findb, db_filepath):
    """
    Download missing data for each ticker, compare with existing data in findata and StockDataDB.csv,
    and update StockDataDB.csv with only the missing rows.
    """
    global USER_AGENTS, ua
    common_cols = ['Date', 'Stock', 'Open', 'Low', 'High', 'Close', 'Volume']

    end_date = datetime.strptime(get_previous_business_day(), '%Y-%m-%d')
    start_date = datetime.today() - timedelta(days=365 * years)

    # Step 1: Load existing StockDataDB.csv
    if os.path.exists(db_filepath):
        existing_db = pd.read_csv(db_filepath)
        existing_db['Date'] = pd.to_datetime(existing_db['Date'], format='mixed', errors='coerce').dt.date
        logger.log(f"✅ Loaded existing StockDataDB.csv with {len(existing_db)} rows.")
    else:
        existing_db = pd.DataFrame(columns=common_cols)
        logger.log("⚠️ StockDataDB.csv does not exist. Starting with an empty database.")

    # Step 2: Load all data from findata folder
    findata_rows = []
    for ticker in tickers:
        ticker_folder = os.path.join(findata, ticker)
        if not os.path.exists(ticker_folder):
            logger.log(f"📂 No folder found for {ticker}. Skipping.")
            continue

        for file in os.listdir(ticker_folder):
            if file.endswith(".csv"):
                file_path = os.path.join(ticker_folder, file)
                try:
                    file_data = pd.read_csv(file_path)
                    file_data['Date'] = pd.to_datetime(file_data['Date'], format='mixed', errors='coerce').dt.date
                    file_data['Stock'] = ticker
                    findata_rows.append(file_data)
                except Exception as e:
                    logger.log(f"⚠️ Failed to load file {file_path}: {e}")

    if findata_rows:
        findata_df = pd.concat(findata_rows, ignore_index=True)
        logger.log(f"✅ Loaded {len(findata_df)} rows from findata folder.")
    else:
        findata_df = pd.DataFrame(columns=common_cols)
        logger.log("⚠️ No data found in findata folder.")

    # Step 3: Combine existing_db and findata_df, and deduplicate
    combined_data = pd.concat([existing_db, findata_df], ignore_index=True)
    combined_data = combined_data.drop_duplicates(subset=['Date', 'Stock'], keep='last')
    logger.log(f"✅ Combined data has {len(combined_data)} unique rows after deduplication.")

    # Step 4: Download missing data for each ticker
    all_downloaded_data = []
    for i, ticker in enumerate(tickers):
        # 🔁 Refresh user agents every 10 tickers
        if i > 0 and i % 10 == 0 and ua:
            try:
                USER_AGENTS = [ua.random for _ in range(50)]
                if DEBUG:
                    logger.log(f"🔁 Refreshed user agent list after {i} tickers.")
            except Exception as e:
                if DEBUG:
                    logger.log(f"⚠️ Failed to refresh user agents: {e}")

        # Step 1: Determine missing business days
        missing_dates = get_missing_dates(ticker, findata, start_date, end_date)
        if DEBUG:
            logger.log(f"🔍 Missing dates for {ticker}: {[d.strftime('%Y-%m-%d') for d in missing_dates]}")
        confirmed_missing_dates = []
        for d in missing_dates:
            file_path = os.path.join(findata, ticker, f"StockData_{ticker}_{d.date()}.csv")
            if not os.path.exists(file_path):
                confirmed_missing_dates.append(d)

        if not confirmed_missing_dates:
            logger.log(f"✅ All data for {ticker} is already downloaded. Skipping.")
            continue

        # Step 2: Fetch missing data
        rotate_user_agent_and_proxy(session, USER_AGENTS, PROXIES_LIST)
        end_date_for_download = max(confirmed_missing_dates) + timedelta(days=1)
        data = yfin.download(
            ticker,
            start=min(confirmed_missing_dates).strftime('%Y-%m-%d'),
            end=end_date_for_download.strftime('%Y-%m-%d')
        )
        if data.empty:
            logger.log(f"⚠️ No data fetched for {ticker}. Skipping.")
            continue

        data.reset_index(inplace=True)

        # Step 3: Flatten MultiIndex if needed
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = [col[0] if col[0] != '' else col[1] for col in data.columns]

        # Step 4: Ensure 'Date' column
        if 'Date' not in data.columns:
            if 'index' in data.columns:
                data.rename(columns={'index': 'Date'}, inplace=True)
            else:
                datetime_cols = [col for col in data.columns if pd.api.types.is_datetime64_any_dtype(data[col])]
                if datetime_cols:
                    data.rename(columns={datetime_cols[0]: 'Date'}, inplace=True)

        if 'Date' not in data.columns:
            logger.log(f"⚠️ Ticker {ticker}: No 'Date' column found after reset. Skipping.")
            continue

        # Step 5: Filter and Save
        data['Date'] = pd.to_datetime(data['Date']).dt.date
        data['Stock'] = ticker
        data = data[data['Date'].isin([d.date() for d in confirmed_missing_dates])]

        if data.empty:
            logger.log(f"⚠️ No new data to save for {ticker} after filtering for missing dates.")
            continue

        logger.log(
            f"📈 Downloaded {len(data)} rows for {ticker} from {min(confirmed_missing_dates).strftime('%Y-%m-%d')} to {max(confirmed_missing_dates).strftime('%Y-%m-%d')}"
        )

        save_ticker_data_to_csv(ticker, data, findata)
        all_downloaded_data.append(data)

    # Step 5: Combine downloaded data with combined_data
    if all_downloaded_data:
        downloaded_data = pd.concat(all_downloaded_data, ignore_index=True)
        combined_data = pd.concat([combined_data, downloaded_data], ignore_index=True)
        combined_data = combined_data.drop_duplicates(subset=['Date', 'Stock'], keep='last')
        logger.log(f"✅ Final combined data has {len(combined_data)} unique rows after adding downloaded data.")

    # Step 6: Save the updated StockDataDB.csv
    combined_data.to_csv(db_filepath, index=False)
    logger.log(f"✅ Updated StockDataDB.csv with {len(combined_data)} total unique rows.")

# ----------------------------------------------------------- #
#                     Execution Pipeline                      #
# ----------------------------------------------------------- #

start_time = datetime.now()
logger.log(f"🚀 Starting execution pipeline at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
logger.log(
    "🧾 Execution timestamps updated.",
    web_data={"execution_start": start_time.strftime('%Y-%m-%d %H:%M:%S')}
)
# Fetch dynamic user agents or use the fallback list
try:
    from fake_useragent import UserAgent
    ua = UserAgent()
    USER_AGENTS = [ua.random for _ in range(50)]  # Generate 50 real agents
    logger.log(f"✅ Generated {len(USER_AGENTS)} dynamic user agents using fake-useragent.")
except Exception as e:
    USER_AGENTS = FALLBACK_USER_AGENTS
    logger.log(f"⚠️ Failed to generate dynamic user agents. Using fallback list. Reason: {e}")

if not USER_AGENTS:
    logger.log("⚠️ No user agents available. Falling back to default behavior.")

# Fetch proxies using proxybroker
# PROXIES_LIST = fetch_proxies_from_public_list(limit=10)
# if not PROXIES_LIST:
#     logger.log("⚠️ No proxies available. Proceeding without proxies.")

PROXIES_LIST = fetch_combined_proxy_list(limit=20)
if not PROXIES_LIST:
    logger.log("⚠️ No proxies available. Proceeding without proxies.")
else:
    logger.log(f"✅ Loaded {len(PROXIES_LIST)} proxies from multiple sources.")

# Create a session
session = requests.Session()

# Configure retries for the session
retry_strategy = Retry(
    total=3,  # Number of retries
    backoff_factor=1,  # Wait time between retries (exponential backoff)
    status_forcelist=[500, 502, 503, 504],  # Retry on these HTTP status codes
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)

tickers = read_tickers_from_file(tickers_file)
if not tickers:
    logger.log("⚠️ No tickers found in the file. Exiting.")
    exit(1)
download_and_append(tickers, findata, findb, db_filepath)

end_time = datetime.now()
logger.log(f"✅ Execution completed at: {end_time.strftime('%Y-%m-%d %H:%M:%S')} in {end_time - start_time}")

logger.log(
    "🧾 Execution timestamps updated.",
    web_data={"execution_end": end_time.strftime('%Y-%m-%d %H:%M:%S')}
)