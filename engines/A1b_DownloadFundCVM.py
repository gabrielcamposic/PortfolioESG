#!/usr/bin/env python3
"""
engines/A1b_DownloadFundCVM.py — Fund Quota Downloader

Fetches the daily quota for a specific fund (default Bradesco ESG Global)
from the CVM open data portal and stores it in data/findb/FundQuotaDB.csv.
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path
import pandas as pd

# Setup paths
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FINDB_DIR = ROOT / "data" / "findb"
FUND_QUOTA_DB = FINDB_DIR / "FundQuotaDB.csv"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - A1b_DownloadFund - %(levelname)s - %(message)s")
logger = logging.getLogger("A1b_DownloadFund")

def download_cvm_fund_quota(cnpj_clean: str = "38860877000125"):
    logger.info("Starting CVM Fund Quota download...")
    FINDB_DIR.mkdir(parents=True, exist_ok=True)
    
    data_atual = datetime.now()
    # Try current month first, then previous month
    meses_tentar = [data_atual, data_atual - pd.DateOffset(months=1)]
    
    df = None
    for data_t in meses_tentar:
        mes_ano = data_t.strftime('%Y%m')
        url = f"https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{mes_ano}.zip"
        logger.info(f"Fetching CVM data from: {url}")
        try:
            df = pd.read_csv(url, sep=';', compression='zip', encoding='utf-8')
            if 'CNPJ_FUNDO_CLASSE' in df.columns:
                break
        except Exception as e:
            logger.warning(f"Failed to fetch {mes_ano}: {e}")
            df = None

    if df is None or df.empty:
        logger.error("Failed to fetch CVM data from any recent month.")
        return

    try:
        df['CNPJ_FUNDO_CLEAN'] = df['CNPJ_FUNDO_CLASSE'].str.replace(r'[^0-9]', '', regex=True)
        fundo_dados = df[df['CNPJ_FUNDO_CLEAN'] == cnpj_clean].copy()
        
        if fundo_dados.empty:
            logger.warning(f"Fund {cnpj_clean} not found in CVM file.")
            return
            
        fundo_dados['DT_COMPTC'] = pd.to_datetime(fundo_dados['DT_COMPTC'])
        fundo_dados = fundo_dados.sort_values('DT_COMPTC')
        
        # We need Date, Quota Value, and Daily Return
        fundo_dados['date'] = fundo_dados['DT_COMPTC'].dt.strftime('%Y-%m-%d')
        fundo_dados['quota'] = fundo_dados['VL_QUOTA']
        fundo_dados['fund_return'] = fundo_dados['quota'].pct_change()
        
        # Load existing DB if any to calculate missing pct_change
        if FUND_QUOTA_DB.exists():
            old_df = pd.read_csv(FUND_QUOTA_DB)
            # Combine old and new, dropping duplicates by date
            combined = pd.concat([old_df, fundo_dados[['date', 'quota', 'fund_return']]])
            combined = combined.drop_duplicates(subset=['date'], keep='last').sort_values('date')
            combined['fund_return'] = combined['quota'].pct_change()
            combined.to_csv(FUND_QUOTA_DB, index=False)
            logger.info(f"Updated {FUND_QUOTA_DB} with latest data.")
        else:
            fundo_dados[['date', 'quota', 'fund_return']].to_csv(FUND_QUOTA_DB, index=False)
            logger.info(f"Created {FUND_QUOTA_DB} with initial data.")
            
    except Exception as e:
        logger.error(f"Failed to fetch or process CVM data: {e}")

if __name__ == "__main__":
    download_cvm_fund_quota()
