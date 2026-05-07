import pandas as pd
import requests
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - Backfill - %(levelname)s - %(message)s")
logger = logging.getLogger("BackfillFund")

ROOT = Path("/Users/gabrielcampos/PortfolioESG")
FINDB_DIR = ROOT / "data" / "findb"
FUND_QUOTA_DB = FINDB_DIR / "FundQuotaDB.csv"
CNPJ_CLEAN = "38860877000125"

def backfill():
    meses = [
        "202510", "202511", "202512",
        "202601", "202602", "202603", "202604", "202605"
    ]
    
    all_data = []
    
    for mes in meses:
        url = f"https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{mes}.zip"
        logger.info(f"Baixando {url}...")
        try:
            df = pd.read_csv(url, sep=';', compression='zip', encoding='utf-8')
            if 'CNPJ_FUNDO_CLASSE' in df.columns:
                df['CNPJ_FUNDO_CLEAN'] = df['CNPJ_FUNDO_CLASSE'].str.replace(r'[^0-9]', '', regex=True)
            elif 'CNPJ_FUNDO' in df.columns:
                df['CNPJ_FUNDO_CLEAN'] = df['CNPJ_FUNDO'].str.replace(r'[^0-9]', '', regex=True)
            else:
                logger.error(f"Não encontrou CNPJ em {mes}")
                continue
                
            fundo = df[df['CNPJ_FUNDO_CLEAN'] == CNPJ_CLEAN].copy()
            if not fundo.empty:
                fundo['DT_COMPTC'] = pd.to_datetime(fundo['DT_COMPTC'])
                fundo['date'] = fundo['DT_COMPTC'].dt.strftime('%Y-%m-%d')
                fundo['quota'] = fundo['VL_QUOTA']
                all_data.append(fundo[['date', 'quota']])
                logger.info(f"Encontrou {len(fundo)} registros em {mes}")
            else:
                logger.warning(f"Fundo não encontrado em {mes}")
        except Exception as e:
            logger.error(f"Erro em {mes}: {e}")
            
    if all_data:
        combined = pd.concat(all_data)
        combined = combined.drop_duplicates(subset=['date'], keep='last').sort_values('date')
        combined['fund_return'] = combined['quota'].pct_change()
        
        # Merge with existing
        if FUND_QUOTA_DB.exists():
            old = pd.read_csv(FUND_QUOTA_DB)
            final = pd.concat([old, combined])
            final = final.drop_duplicates(subset=['date'], keep='last').sort_values('date')
            final['fund_return'] = final['quota'].pct_change()
            final.to_csv(FUND_QUOTA_DB, index=False)
        else:
            combined.to_csv(FUND_QUOTA_DB, index=False)
            
        logger.info(f"Backfill finalizado. {len(combined)} registros salvos.")
    else:
        logger.warning("Nenhum dado foi baixado no backfill.")

if __name__ == "__main__":
    backfill()
