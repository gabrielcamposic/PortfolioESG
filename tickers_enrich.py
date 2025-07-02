import yfinance as yf
import pandas as pd
import os

# Caminho para seu arquivo original
input_file = os.path.expanduser("~/Documents/Prog/PortfolioESG_Data/Tickers.txt")
output_file = os.path.expanduser("~/Documents/Prog/PortfolioESG_Data/Tickers_Enriched.csv")

# Carrega os tickers
with open(input_file, "r") as f:
    tickers = [line.strip() for line in f if line.strip() and not line.startswith("#")]

# Limpa e prepara os tickers
tickers_cleaned = [ticker.replace(".SA", "") for ticker in tickers]

# Consulta o setor e a indústria
data = []
for ticker in tickers_cleaned:
    try:
        t = yf.Ticker(f"{ticker}.SA")
        info = t.info
        data.append({
            "Ticker": f"{ticker}.SA",
            "Sector": info.get("sector", "Unknown"),
            "Industry": info.get("industry", "Unknown")
        })
    except Exception as e:
        data.append({
            "Ticker": f"{ticker}.SA",
            "Sector": "Error",
            "Industry": str(e)
        })

# Salva em CSV
df = pd.DataFrame(data)
df.to_csv(output_file, index=False)
print(f"Arquivo salvo como: {output_file}")