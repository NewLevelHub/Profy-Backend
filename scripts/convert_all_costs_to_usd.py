import asyncio
import os
import sys
import re
from decimal import Decimal

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select
from app.database import async_session
from app.models.program import Program

CURRENCY_MAP = [
    ("KZT", 480.0, r"\bKZT\b|тенге"),
    ("EUR", 0.92, r"\bEUR\b|евро"),
    ("GBP", 0.77, r"\bGBP\b|фунт[а-я]*"),
    ("CNY", 7.15, r"\bCNY\b|юан[а-я]*"),
    ("CAD", 1.37, r"\bCAD\b"),
    ("SGD", 1.35, r"\bSGD\b"),
    ("HKD", 7.80, r"\bHKD\b"),
    ("KRW", 1330.0, r"\bKRW\b|вон[а-я]*"),
    ("AUD", 1.50, r"\bAUD\b"),
    ("SEK", 10.50, r"\bSEK\b|крон[а-я]*"),
    ("NOK", 10.70, r"\bNOK\b"),
    ("CHF", 0.88, r"\bCHF\b|франк[а-я]*"),
    ("JPY", 147.0, r"\bJPY\b|иен[а-я]*|йен[а-я]*"),
    ("ZAR", 18.0, r"\bZAR\b|рэнд[а-я]*|ранд[а-я]*"),
    ("BRL", 5.50, r"\bBRL\b|реал[а-я]*"),
]

def convert_label_to_usd(label: str) -> str:
    if not label:
        return label
    
    low_label = label.lower()
    # If the label has already been converted to USD, skip it to prevent double conversion
    if "usd" in low_label or "доллар" in low_label:
        return label

    detected_currency = None
    rate = 1.0
    pattern = None
    for curr_code, curr_rate, curr_pattern in CURRENCY_MAP:
        if re.search(curr_pattern, label, re.IGNORECASE):
            detected_currency = curr_code
            rate = curr_rate
            pattern = curr_pattern
            break
            
    if not detected_currency:
        return label
        
    def replace_num(match):
        match_str = match.group(0)
        # Clean spacing and commas from the matched digits to convert safely
        cleaned = re.sub(r"[\s,]", "", match_str)
        try:
            val = float(cleaned)
            # Skip year indicators
            if val in (2025.0, 2026.0, 2027.0, 2028.0):
                return match_str
            usd_val = int(round(val / rate))
            return f"{usd_val:,}".replace(",", " ")
        except ValueError:
            return match_str

    # Precise number regex to match digits (optionally grouped by space/comma/dot) but without capturing trailing spaces
    number_re = re.compile(r"\b\d+(?:[\s,.]\d+)*\b")
    result = number_re.sub(replace_num, label)
    
    # Replace original currency symbols/words with USD
    result = re.sub(pattern, "USD", result, flags=re.IGNORECASE)
    return result

async def main():
    async with async_session() as db:
        res = await db.execute(select(Program))
        programs = res.scalars().all()
        
        updated_count = 0
        for p in programs:
            changed = False
            
            # 1. Convert cost_per_year, cost_per_year_min, cost_per_year_max columns if not USD
            # Note: We check p.cost_currency. If it is already 'USD', we don't convert it again!
            if p.cost_currency and p.cost_currency.upper() != "USD":
                rate = 1.0
                for curr_code, curr_rate, _ in CURRENCY_MAP:
                    if curr_code == p.cost_currency.upper():
                        rate = curr_rate
                        break
                
                if rate != 1.0:
                    if p.cost_per_year is not None:
                        p.cost_per_year = Decimal(str(round(float(p.cost_per_year) / rate)))
                    if p.cost_per_year_min is not None:
                        p.cost_per_year_min = Decimal(str(round(float(p.cost_per_year_min) / rate)))
                    if p.cost_per_year_max is not None:
                        p.cost_per_year_max = Decimal(str(round(float(p.cost_per_year_max) / rate)))
                    p.cost_currency = "USD"
                    changed = True
            
            # 2. Convert text inside cost_label
            if p.cost_label:
                new_label = convert_label_to_usd(p.cost_label)
                if new_label != p.cost_label:
                    print(f"Update Cost Label: {p.cost_label!r} -> {new_label!r}")
                    p.cost_label = new_label
                    changed = True
                    
            if changed:
                updated_count += 1
                
        if updated_count > 0:
            await db.commit()
            print(f"Successfully converted and saved {updated_count} programs in DB.")
        else:
            print("No programs needed updates.")

if __name__ == '__main__':
    asyncio.run(main())
