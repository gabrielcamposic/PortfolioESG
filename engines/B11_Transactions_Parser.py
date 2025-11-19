from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from pathlib import Path
import re
import unicodedata
from datetime import datetime
import csv

# shared paths/constants
DATA_DIR = Path('data')
TX_FILE = DATA_DIR / 'transactions_parsed.csv'
FEES_FILE = DATA_DIR / 'fees_parsed.csv'
LEDGER_FILE = DATA_DIR / 'ledger.csv'
NOTAS_DIR = Path('Notas_Negociação')

# Optional PDF/OCR libraries
try:
    import pdfplumber
    from pdfplumber.utils.exceptions import PdfminerException
    PDFPLUMBER_AVAILABLE = True
except Exception:
    PDFPLUMBER_AVAILABLE = False

try:
    # PIL may be optional on machines that don't need OCR; only set flag if import succeeds
    from PIL import Image  # noqa: F401
    import pytesseract  # noqa: F401
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

# NOTE: decryption attempts removed per user request (no automatic unlocking)


def parse_decimal(s):
    if s is None or s == '':
        return Decimal('0')
    try:
        return Decimal(s)
    except InvalidOperation:
        # try to clean common BR formats
        s2 = str(s).strip().replace('R$', '').replace(' ', '')
        # if both . and , -> assume . thousands, , decimal
        if '.' in s2 and ',' in s2:
            s2 = s2.replace('.', '').replace(',', '.')
        else:
            s2 = s2.replace(',', '.')
        try:
            return Decimal(s2)
        except Exception:
            return Decimal('0')


# --- PDF parsing and heuristics ---

def normalize_text(t: str) -> str:
    # normalize unicode, remove control chars, unify whitespace
    if not t:
        return ''
    # decompose accents
    t = unicodedata.normalize('NFKD', t)
    t = ''.join(c for c in t if not unicodedata.combining(c))
    # replace non-breaking spaces and weird dashes
    t = t.replace('\xa0', ' ').replace('\u2011', '-').replace('\u2013', '-')
    # collapse multiple spaces and tabs
    t = re.sub(r'[\t\r]+', ' ', t)
    t = re.sub(r' +', ' ', t)
    # ensure newlines are normalized
    t = re.sub(r'\n\s+', '\n', t)
    return t.strip()


def extract_text_from_pdf(path: Path) -> str:
    """Extract text from PDF using pdfplumber; if text extraction yields empty text, fall back to OCR (pytesseract) when available.

    Per user request, do not attempt to decrypt or unlock PDFs automatically.
    """
    text_pages = []
    if not PDFPLUMBER_AVAILABLE:
        return ''
    try:
        with pdfplumber.open(path) as pdf:
            for p in pdf.pages:
                try:
                    t = p.extract_text() or ''
                except Exception:
                    t = ''
                text_pages.append(t)
    except Exception as e:
        # If pdfplumber can't open the file, report and do not attempt unlocking
        print(f"pdfplumber failed to open {path}: {e}")
        return ''

    full = '\n'.join(text_pages)
    full = normalize_text(full)
    if full.strip():
        return full

    # fallback to OCR if text empty and OCR available
    if OCR_AVAILABLE:
        ocr_texts = []
        try:
            with pdfplumber.open(path) as pdf:
                for p in pdf.pages:
                    try:
                        img = p.to_image(resolution=300).original
                        txt = pytesseract.image_to_string(img, lang='por+eng')
                    except Exception:
                        txt = ''
                    ocr_texts.append(txt)
        except Exception as e:
            print(f"OCR fallback failed for {path}: {e}")
            return ''
        full_ocr = '\n'.join(ocr_texts)
        return normalize_text(full_ocr)

    return full


def norm_num_br(s: str) -> Decimal:
    if s is None:
        return Decimal('0')
    t = str(s).strip()
    if t == '':
        return Decimal('0')
    t = t.replace('R$', '').replace(' ', '')
    t = re.sub(r'[^0-9,.-]', '', t)
    # brazilian formatting: '.' thousands and ',' decimals
    if '.' in t and ',' in t:
        t = t.replace('.', '').replace(',', '.')
    else:
        t = t.replace(',', '.')
    try:
        return Decimal(t)
    except Exception:
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)", t)
        return Decimal(m.group(1)) if m else Decimal('0')


def format_decimal(d, places=2):
    # ensure Decimal input and format with fixed number of decimal places
    try:
        dec = Decimal(d)
    except Exception:
        dec = Decimal('0')
    q = Decimal(1).scaleb(-places)  # 10 ** -places
    return format(dec.quantize(q, rounding=ROUND_HALF_UP), 'f')


def date_to_iso(d):
    """Normalize common date strings to ISO YYYY-MM-DD.
    Accepts dd/mm/YYYY, dd-mm-YYYY, or already ISO. Returns empty string on failure.
    """
    if not d:
        return ''
    s = str(d).strip()
    # already ISO
    if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
        return s
    # common brazilian format dd/mm/YYYY or dd-mm-YYYY
    for fmt in ('%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            pass
    # try to parse loosely (day first)
    try:
        parts = re.split(r'[\-/]', s)
        if len(parts) == 3:
            d0, m0, y0 = parts
            if len(y0) == 4:
                return datetime(int(y0), int(m0), int(d0)).date().isoformat()
    except Exception:
        pass
    return ''


def parse_broker_note_text(text: str):
    text = normalize_text(text)
    # find header info
    trade_date = ''
    settlement_date = ''
    broker_doc = ''
    broker = ''

    # trade date: first occurrence of dd/mm/yyyy
    m = re.search(r'(\d{2}/\d{2}/\d{4})', text)
    if m:
        trade_date = m.group(1)

    # settlement date: look for 'Liquido para' variants
    m = re.search(r'Liquido(?: para)?\s*(?:para\s*)?(\d{2}/\d{2}/\d{4})', text, re.I)
    if m:
        settlement_date = m.group(1)

    # Use line-based scanning for broker document (the nota number usually near the top)
    lines = text.splitlines()
    for i, ln in enumerate(lines[:20]):  # only scan the top of the document
        ln_stripped = ln.strip()
        # a line that starts with a 5-9 digit number is very likely the nota number
        mnum = re.match(r'^\s*([0-9]{5,9})\b', ln_stripped)
        if mnum:
            broker_doc = mnum.group(1)
            break
    # fallback: look for NOTA header followed by a numeric token on the same or next two lines
    if not broker_doc:
        for i, ln in enumerate(lines):
            if 'NOTA' in ln.upper():
                for j in range(i, min(i + 3, len(lines))):
                    nums = re.findall(r'\b([0-9]{5,9})\b', lines[j])
                    if nums:
                        broker_doc = nums[0]
                        break
                if broker_doc:
                    break
    # final fallback: any 6-9 digit number anywhere
    if not broker_doc:
        m3 = re.search(r'\b([0-9]{6,9})\b', text)
        if m3:
            broker_doc = m3.group(1)

    # broker name: look for line containing 'CORRETORA' or common suffixes
    m = re.search(r'([A-Z\s]{5,200}CORRETORA[\w\s,./\-]*)', text, re.I)
    if m:
        broker = m.group(1).strip()
    else:
        # fallback: take the first non-empty line after the nota header that looks like a company name
        for i, ln in enumerate(lines):
            if 'NOTA' in ln.upper() and i + 1 < len(lines):
                candidate = lines[i + 1].strip()
                if len(candidate) > 5 and any(c.isalpha() for c in candidate):
                    broker = candidate
                    break

    # Extract trades block robustly using header line detection
    trades_block = ''
    header_idx = None
    for i, ln in enumerate(lines):
        if re.search(r'Quantidade', ln, re.I) and re.search(r'Preco|Preço', ln, re.I):
            header_idx = i
            break
    if header_idx is not None:
        # collect following lines until an empty line or a summary header
        collected = []
        for ln in lines[header_idx + 1:]:
            if not ln.strip():
                break
            if re.search(r'Resumo(?: dos Neg(?:ocios)?| Financeiro)', ln, re.I):
                break
            collected.append(ln)
        trades_block = '\n'.join(collected)
    else:
        # fallback to the previous approach: between 'Negocios Realizados' and 'Resumo'
        start = re.search(r'Negocios Realizados', text, re.I)
        # single normalized end marker (text is normalized earlier so accents are removed)
        end = re.search(r'Resumo\s+dos\s+Negocios', text, re.I)
        if start and end and start.end() < end.start():
            trades_block = text[start.end():end.start()]
        else:
            trades_block = '\n'.join([ln for ln in lines if re.search(r'\b\d+\b\s+[\d.,]+\s+[\d.,]+\s+[CD]\b', ln, re.I)])

    trades = []

    # Preferred robust line-based parser: tokenize from right-hand side to extract qty, unit, value and D/C
    for ln in trades_block.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        # skip lines that are summary headers
        if re.search(r'Resumo dos Neg', ln, re.I) or re.search(r'Resumo Financeiro', ln, re.I):
            continue
        tokens = ln.split()
        if len(tokens) < 4:
            continue
        # attempt to parse from the right: last token should be D or C
        last = tokens[-1].upper()
        # sometimes D/C may be attached to the previous token like '569,60D'
        if last not in ('D', 'C'):
            # try to split attached D/C
            mdc = re.match(r'([\d.,]+)([DC])$', tokens[-1], re.I)
            if mdc:
                tokens[-1] = mdc.group(2).upper()
                tokens.insert(-1, mdc.group(1))
                last = tokens[-1].upper()
        if last in ('D', 'C'):
            try:
                dc = last
                raw_value = tokens[-2]
                raw_unit = tokens[-3]
                raw_qty = tokens[-4]
                # clean possible punctuation
                raw_qty = re.sub(r'[^0-9]', '', raw_qty)
                qty = int(raw_qty)
                unit = norm_num_br(raw_unit)
                val = norm_num_br(raw_value)
                desc_tokens = tokens[:-4]
                desc = ' '.join(desc_tokens).strip()
                # remove common market tokens
                desc = re.sub(r'\b(?:BOVESPA|FRACIONARIO|FRACIONADO|C|V)\b', '', desc, flags=re.I).strip()
                # try to extract ticker from end of desc
                ticker = desc
                tmatch = re.search(r'([A-Z0-9]{2,}(?:\s+(?:ON|PN|PNA|NM|11|3|4|5)\b)*)$', desc)
                if tmatch:
                    ticker = tmatch.group(1).strip()
                    desc = re.sub(re.escape(ticker) + r'\s*$', '', desc).strip()
                side = 'BUY' if dc == 'D' else 'SELL'
                trades.append({'description': desc or ticker, 'ticker': ticker, 'quantity': qty, 'unit_price': unit, 'gross_value': val, 'side': side})
                continue
            except Exception:
                pass

    # If preferred parser yielded nothing, fall back to regex-based parsing
    if not trades:
        core_re = re.compile(r'(\b\d+\b)\s+([\d.,]+)\s+([\d.,]+)\s+([CD])\b', re.I)
        for m in core_re.finditer(trades_block):
            qty = int(m.group(1))
            unit = norm_num_br(m.group(2))
            val = norm_num_br(m.group(3))
            dc = m.group(4).upper()
            # description: take up to 120 chars before the match start on that line
            line_start = trades_block.rfind('\n', 0, m.start())
            if line_start == -1:
                line_start = 0
            else:
                line_start += 1
            line_end = trades_block.find('\n', m.end())
            if line_end == -1:
                line_end = len(trades_block)
            line = trades_block[line_start:line_end].strip()
            desc = re.sub(r'\b\d+\b\s+[\d.,]+\s+[\d.,]+\s+[CD]\b\s*$', '', line, flags=re.I).strip()
            if not desc:
                pre = trades_block[max(0, m.start() - 120):m.start()].strip()
                desc = pre.split('\n')[-1].strip()
            side = 'BUY' if dc == 'D' else 'SELL'
            desc = ' '.join(desc.split())
            ticker = ''
            tmatch = re.search(r'([A-Z0-9]{2,}(?:\s+[A-Z]{1,4})+)$', desc)
            if tmatch:
                ticker = tmatch.group(1).strip()
                desc = re.sub(re.escape(ticker) + r'\s*$', '', desc).strip()
            trades.append({'description': desc, 'ticker': ticker or desc, 'quantity': qty, 'unit_price': unit, 'gross_value': val, 'side': side})

    # Fees: extract only the expected fee names from the 'Resumo Financeiro' area
    expected_fees = {
        # Clearing category
        'Taxa de liquidação/CCP': ('Clearing', 'fee'),
        'Taxa de registro': ('Clearing', 'fee'),
        # Bolsa category
        'Taxa de termo/opções': ('Bolsa', 'fee'),
        'Emolumentos': ('Bolsa', 'fee'),
        # Depositária
        'Taxa de Transferência de Ativos': ('Depositária', 'fee'),
        # Corretagem / Despesas - fees
        'Clearing': ('Corretagem / Despesas', 'fee'),
        'Execução': ('Corretagem / Despesas', 'fee'),
        'Execução Casa': ('Corretagem / Despesas', 'fee'),
        'Taxa Operacional': ('Corretagem / Despesas', 'fee'),
        # Corretagem / Despesas - taxes
        'I.S.': ('Corretagem / Despesas', 'tax'),
        'IR S/ Operações': ('Corretagem / Despesas', 'tax'),
    }

    fees = []
    # locate the resumo/financeiro section and collect its lines
    resume_start = re.search(r'Resumo(?:\s+dos\s+Neg(?:ocios)?|\s+Financeiro)', text, re.I)
    resume_lines = []
    if resume_start:
        tail = text[resume_start.end():resume_start.end() + 2000]
        # do not cut on 'Especificacoes' so we include depositaria / especificacoes diversas
        end_marker = re.search(r'Observa|AGORA CORRETORA', tail, re.I)
        block = tail[:end_marker.start()] if end_marker else tail
        resume_lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    else:
        resume_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # parse each resume line: label (text before amount) and amount (last decimal-like token)
    for ln in resume_lines:
        # skip header-like lines and unrelated rows
        # only skip if these tokens appear at the start of the line AND the line does not contain any fee-like keywords
        # this allows lines such as 'Compras à vista 987,60 Taxa de liquidação/CCP 0,22 D' to be parsed for the fee
        summary_start_re = re.compile(r'^(?:Nr\.?\s*Nota|Nota Folha|Pregao|Cliente|Valor\s+liquido\s+das\s+oper|Valor\s+das\s+operacoes|Debentures|Total|Vendas\s+a\s+vista|Compras\s+a\s+vista|Opcoes\s*[-–]\s*compras|Opcoes\s*[-–]\s*vendas|Operacoes\s+a\s+termo|Valor\s+das\s+oper\.\s*c/?\s*titulos\s+publ|I\.R\.\s*s/\s*corretagem)\b', re.I)
        fee_like_line = any(k in ln.lower() for k in ('taxa', 'emolumentos', 'transferencia', 'i.s.', 'ir s/', 'iss', 'taxa operacional', 'corretagem'))
        if summary_start_re.search(ln) and not fee_like_line:
            continue
        # find the last decimal-like token (with a decimal separator) at the end of the line
        m = re.search(r'([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{1,2})?)\s*[CD]?\s*$', ln)
        if not m:
            # no decimal-like token at line end -> skip
            continue
        raw_amount = m.group(1)
        # avoid matching large integer tokens (nota id) that lack decimal separators
        digits_only = re.sub(r'[^0-9]', '', raw_amount)
        if digits_only.isdigit() and len(digits_only) > 6 and ('.' not in raw_amount and ',' not in raw_amount):
            continue
        amount = norm_num_br(raw_amount)
        # label is the part before the matched amount
        label = ln[:m.start(1)].strip()
        # clean trailing punctuation and stray numbers in label
        label = re.sub(r'[:\-\s]+$', '', label)
        label = re.sub(r'\s+[0-9.,]+$', '', label).strip()
        # map label to expected canonical fee name if possible
        chosen = None
        label_norm = normalize_text(label).lower()
        for key in expected_fees.keys():
            if normalize_text(key).lower() in label_norm or normalize_text(key).lower() == label_norm:
                chosen = key
                break
        if chosen:
            cat, kind = expected_fees[chosen]
            # use canonical fee name as description to avoid brittle slicing/index errors
            description = chosen
            fees.append({'fee_type': chosen, 'amount': amount, 'category': cat, 'kind': kind, 'description': description})
        else:
            # not in expected list; keep as 'Other' only if the label looks fee-like
            if amount != Decimal('0'):
                label_l = label.lower()
                # avoid matching the dotted form 'i.r.' (we don't want to capture 'I.R. s/ corretagem')
                fee_like = any(k in label_l for k in ('taxa', 'emolumentos', 'transferencia', 'i.s.', 'ir s/', 'iss', 'taxa operacional', 'corretagem'))
                if fee_like:
                    fees.append({'fee_type': label or 'Unknown', 'amount': amount, 'category': 'Other', 'kind': 'fee', 'description': label})

    # dedupe and normalize
    seenf = set()
    fees_unique = []
    for f in fees:
        key = (f.get('fee_type', '').lower(), format_decimal(f.get('amount', 0), 2))
        if key in seenf:
            continue
        seenf.add(key)
        fees_unique.append(f)

    # final sanity: drop fees that are implausibly large compared to trades gross
    total_trades_gross = sum((t['gross_value'] for t in trades), Decimal('0'))
    threshold = max(total_trades_gross * Decimal('10'), Decimal('1000'))
    fees_unique = [f for f in fees_unique if f.get('amount', Decimal('0')) <= threshold]

    return {
        'trade_date': trade_date,
        'settlement_date': settlement_date,
        'broker_document': broker_doc,
        'broker': broker,
        'trades': trades,
        'fees': fees_unique
    }


def write_parsed_csvs(parsed, tx_path: Path, fees_path: Path):
    tx_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().isoformat()
    # write transactions
    with tx_path.open('w', newline='', encoding='utf-8') as f:
        fieldnames = ['transaction_id', 'portfolio', 'trade_date', 'settlement_date', 'broker_document', 'broker', 'ticker', 'isin', 'side', 'quantity', 'unit_price', 'gross_value', 'currency', 'fx_rate', 'order_type', 'broker_order_id', 'notes', 'import_ts']
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        broker_doc = parsed.get('broker_document') or 'manual'
        trade_date_iso = date_to_iso(parsed.get('trade_date') or '')
        settlement_date_iso = date_to_iso(parsed.get('settlement_date') or '')
        for i, t in enumerate(parsed.get('trades', []), start=1):
            tid = f"{broker_doc}-{i}" if broker_doc else f"manual-{i}"
            # format numbers consistently
            qty_val = t.get('quantity')
            try:
                qty_str = str(int(qty_val))
            except Exception:
                qty_str = str(qty_val)
            unit_str = format_decimal(t.get('unit_price'), 4) if t.get('unit_price') is not None else ''
            gross_str = format_decimal(t.get('gross_value'), 2) if t.get('gross_value') is not None else ''
            row = {
                'transaction_id': tid,
                'portfolio': 'MAIN',
                'trade_date': trade_date_iso,
                'settlement_date': settlement_date_iso,
                'broker_document': broker_doc,
                'broker': parsed.get('broker') or '',
                'ticker': t.get('ticker'),
                'isin': '',
                'side': t.get('side'),
                'quantity': qty_str,
                'unit_price': unit_str,
                'gross_value': gross_str,
                'currency': 'BRL',
                'fx_rate': '1.0',
                'order_type': '',
                'broker_order_id': broker_doc,
                'notes': t.get('description'),
                'import_ts': now
            }
            w.writerow(row)
    # write fees with category and kind columns
    with fees_path.open('w', newline='', encoding='utf-8') as f:
        fieldnames = ['transaction_id', 'category', 'kind', 'fee_type', 'amount', 'currency', 'description']
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        broker_doc = parsed.get('broker_document') or 'manual'
        for fee in parsed.get('fees', []):
            amt_str = format_decimal(fee.get('amount'), 2)
            w.writerow({'transaction_id': broker_doc, 'category': fee.get('category', 'Other'), 'kind': fee.get('kind', 'fee'), 'fee_type': fee.get('fee_type'), 'amount': amt_str, 'currency': 'BRL', 'description': fee.get('description')})

