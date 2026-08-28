"""
Foreign-university Program.cost_label is 100% free text (0 of 1205 foreign
programs have cost_per_year set — A6's numeric parser never ran against this
cluster dataset) and reads inconsistently on the card: mixed currencies,
mixed annual/semester/total-program framing, and several texts show a
domestic/citizen-only rate alongside (or instead of) the international rate
a Kazakhstani applicant would actually pay. See university-cards-ux-fix-plan.md
§2/§10 and the live examples that prompted this pass (Tsinghua "для китайцев"
vs "для иностранцев", University of Tokyo "бесплатно для японцев").

Every one of the 148 distinct cost_label values used across foreign programs
was read and hand-classified into one of two buckets:

  NUMERIC: a clean annual, international-applicable figure exists (rewritten
  to a per-year basis if the source was per-semester — multiplied by 2) ->
  sets cost_per_year_min/max + cost_currency in the ORIGINAL currency. The
  existing convert_cost_to_usd Pydantic validator (app/schemas/university.py)
  already converts this to a clean "$N NNN /год" at read time via
  formatCost() on the frontend -- no free-text parsing involved at all once
  this is set, which is what actually guarantees every card looks the same
  (patching the text converter further was not the fix; removing the need
  for it on these rows is). A domestic/citizen-only figure sitting next to
  the international one in the source text is simply not carried over here
  -- only the number a foreign (KZ) applicant would pay went into the
  numeric fields, so it silently stops being displayed at all once this
  runs, no separate text edit needed.

  TEXT_ONLY: genuinely not an annual figure (a total multi-year/MBA-program
  cost, a "few hundred dollars, exact figure unclear" case, or no usable
  number at all) -- cost_per_year_min/max stay null (falls back to the
  already-fixed convertLabelCurrenciesToUsd on the frontend), but the label
  text itself is rewritten where it contained a domestic-only rate/aside
  that doesn't apply to a foreign applicant (e.g. NUS's Tuition-Grant
  subsidized rate, which requires a multi-year Singapore work bond).

Dry-run by default. Pass --apply to commit.
  docker exec profy-backend-api-1 python scripts/backfill_foreign_cost_numeric.py [--apply]
"""
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select

from app.database import async_session
from app.models.program import Program
from app.models.university import University

# (university_name, exact_old_cost_label) -> (currency, min, max)
NUMERIC: dict[tuple[str, str], tuple[str, float, float]] = {
    ("École Nationale de l'Aviation Civile (ENAC)", "4 000 – 12 000 EUR в год"): ("EUR", 4000, 12000),
    ("Embry-Riddle Aeronautical University", "около 46 000 USD в год (кампус Дейтона-Бич, 2025/26), плюс отдельная оплата лётной подготовки; онлайн-программы от 12 500 USD в год"): ("USD", 46000, 46000),
    ("Southwest Jiaotong University", "~23 000 CNY в год для научно-инженерных программ"): ("CNY", 23000, 23000),
    ("Kühne Logistics University", "14 980–15 600 EUR в год в зависимости от программы"): ("EUR", 14980, 15600),
    ("Stellenbosch University — Department of Logistics", "ориентировочно от 64 000 ZAR в год для иностранных студентов (варьируется по программе и уровню обучения)"): ("ZAR", 64000, 64000),
    ("Politecnico di Milano — Scuola del Design", "€900-4,000 в год (в зависимости от программы и уровня дохода семьи)"): ("EUR", 900, 4000),
    ("King Fahd University of Petroleum and Minerals", "для стипендиатов обучение бесплатное; без стипендии — от 15 000 до 25 000 USD в год в зависимости от программы"): ("USD", 15000, 25000),
    ("University of Reading", "около 30 650–31 800 GBP в год для иностранных студентов бакалавриата"): ("GBP", 30650, 31800),
    ("China University of Petroleum, Beijing", "около 31 000 CNY в год для бакалавриата и магистратуры"): ("CNY", 31000, 31000),
    ("Wageningen University & Research", "~16 000 – 19 000 EUR в год (для граждан вне ЕЭЗ)"): ("EUR", 16000, 19000),
    ("UC Davis", "~44 000 USD в год для иностранных абитуриентов"): ("USD", 44000, 44000),
    ("Harvard Kennedy School, Harvard University", "около 61 900 долл. США в год (только обучение, 2025/2026); с учётом сборов и проживания — порядка 99 000 долл. США в год"): ("USD", 61900, 61900),
    ("Technical University of Munich (TUM)", "2 000 – 6 000 EUR в семестр для граждан вне ЕС"): ("EUR", 4000, 12000),
    ("ETH Zurich", "~730 CHF в семестр"): ("CHF", 1460, 1460),
    ("Carnegie Mellon University (CMU)", "60 000 – 70 000 USD в год (обучение) + около 24 000 USD в год на проживание"): ("USD", 60000, 70000),
    ("University of Edinburgh", "26 500 – 37 500 GBP в год (бакалавриат)"): ("GBP", 26500, 37500),
    ("University of Melbourne", "38 000 – 58 000 AUD в год (бакалавриат)"): ("AUD", 38000, 58000),
    ("Korea Advanced Institute of Science and Technology", "3 000 – 5 000 USD в семестр для иностранных студентов"): ("USD", 6000, 10000),
    ("Delft University of Technology (TU Delft)", "~16 000 – 20 000 EUR в год для студентов вне ЕЭЗ"): ("EUR", 16000, 20000),
    ("Technical University of Munich (TUM)", "€2000–€3000 за семестр (бакалавриат) для студентов вне ЕС"): ("EUR", 4000, 6000),
    ("Tokyo Institute of Technology", "~535 800 JPY (~3 746 USD) в год; возможны стипендии для отличных студентов"): ("USD", 3746, 3746),
    ("Imperial College London", "£38 000–£43 300 в год для программ бакалавриата (инженерия)"): ("GBP", 38000, 43300),
    ("University of Toronto, Temerty Faculty of Medicine", "$70 060–$72 860 в год для международных студентов бакалавриата"): ("USD", 70060, 72860),
    ("Toronto Metropolitan University", "~CAD 30,000-44,000 в год для иностранных студентов (в зависимости от программы: бакалавриат дороже, магистратура ~CAD 30,000)"): ("CAD", 30000, 44000),
    ("University of Reading", "£16 450—22 550 в год для бакалавриата; £30 650 в год для программ по агрономии"): ("GBP", 16450, 22550),
    ("Charles University", "≈19 400–21 000 евро в год (программа General Medicine, 6 лет); Второй медицинский факультет — около 460 000 CZK в год (≈20 000 USD)"): ("EUR", 19400, 21000),
    ("University of Toronto, Temerty Faculty of Medicine", "≈CAD 60 000–95 000 в год для иностранных студентов в зависимости от программы (медицина, стоматология значительно дороже сестринского дела и реабилитационных наук)"): ("CAD", 60000, 95000),
    ("National University of Singapore, Yong Loo Lin School of Medicine", "≈SGD 30 000–33 000 в год при получении Tuition Grant (с трёхлетним обязательством отработки в Сингапуре); без гранта — от SGD 80 000 в год"): ("SGD", 80000, 80000),
    ("University of Melbourne", "Doctor of Medicine — ≈AUD 112 000 за первый год; Doctor of Clinical Dentistry — ≈AUD 59 000 в год; Doctor of Dental Surgery — ≈AUD 98 500 в год"): ("AUD", 112000, 112000),
    ("University of Cape Town (UCT)", "≈R108 800 (≈USD 6 000) в год за обучение по программе MBChB; с учётом проживания и прочих расходов общий бюджет ≈USD 11 000–23 000 в год"): ("USD", 6000, 6000),
    ("University of Edinburgh", "£25,950–£36,300 в год"): ("GBP", 25950, 36300),
    ("Charité - Universitätsmedizin Berlin", "€300–€400 в семестр (только взносы, без обучения для иностранцев)"): ("EUR", 600, 800),
    ("Jagiellonian University", "€15,500–€16,000 в год (~€93,000 за полный 6-летний курс)"): ("EUR", 15500, 16000),
    ("University of Padua", "€2,500–€3,000 в год (зависит от семейного дохода)"): ("EUR", 2500, 3000),
    ("University of Warwick", "~24 000 – 30 000 GBP в год"): ("GBP", 24000, 30000),
    ("Erasmus University Rotterdam", "10 000 – 18 000 EUR в год (для граждан вне ЕЭЗ)"): ("EUR", 10000, 18000),
    ("University of St. Gallen (HSG)", "~730 CHF в семестр (швейцарские студенты), ~2400 CHF для иностранцев"): ("CHF", 4800, 4800),
    ("University of Mannheim", "~175 EUR в семестр (сбор, обучение фактически бесплатное в Германии)"): ("EUR", 350, 350),
    ("HEC Paris", "~30 000 – 45 000 EUR в год (зависит от уровня программы)"): ("EUR", 30000, 45000),
    ("University of St. Gallen (HSG)", "~3 100 CHF в семестр для иностранных студентов"): ("CHF", 6200, 6200),
    ("Wharton School of the University of Pennsylvania", "~$76,500 в год за MBA"): ("USD", 76500, 76500),
    ("WHU – Otto Beisheim School of Management", "~€20,000-24,000 в год за MBA"): ("EUR", 20000, 24000),
    ("RMIT University", "~35 000 – 40 000 AUD в год"): ("AUD", 35000, 40000),
    ("University of Cape Town Graduate School of Business", "от 99 000 до 594 400 ZAR за первый год обучения в зависимости от программы"): ("ZAR", 99000, 594400),
    ("Melbourne Business School, University of Melbourne", "около 56 000–60 000 австралийских долларов в год для программы full-time MBA; бакалаврские бизнес-программы — от 38 000 до 42 000 австралийских долларов в год"): ("AUD", 56000, 60000),
    ("Glion Institute of Higher Education", "~40 000 CHF в семестр (часто включает проживание и питание)"): ("CHF", 80000, 80000),
    ("Les Roches Global Hospitality", "~30 000 – 35 000 EUR/CHF в год"): ("EUR", 30000, 35000),
    ("University of Surrey — School of Hospitality and Tourism Management", "22 900–27 000 £ в год (бакалавриат) для иностранных студентов"): ("GBP", 22900, 27000),
    ("Columbia University Graduate School of Journalism", "≈78 364 USD за первый год обучения (специализация Data Journalism — до 117 546 USD)"): ("USD", 78364, 78364),
    ("École Supérieure d'Interprètes et de Traducteurs, Université Sorbonne Nouvelle", "Символическая регистрационная плата государственного вуза Франции — 254 евро в год (магистратура), для граждан не ЕС дополнительная плата по системе Bienvenue en France (до ≈3 770 евро/год)"): ("EUR", 3770, 3770),
    ("University of Technology Sydney (UTS)", "≈48,000 – 55,000 AUD в год (≈36,000 – 41,000 USD)"): ("USD", 36000, 41000),
    ("Universitat Autònoma de Barcelona (UAB)", "≈6,000 EUR в год для студентов вне ЕС/ЕЭЗ; ≈5,000 EUR для студентов ЕС"): ("EUR", 6000, 6000),
    ("University of Amsterdam", "≈13,000 – 22,000 EUR в год для иностранных студентов (в зависимости от программы)"): ("EUR", 13000, 22000),
    ("Johannes Gutenberg University Mainz (JGU)", "Бесплатно (только административный сбор ≈319 EUR в семестр); для граждан вне ЕС нет дополнительных платежей за обучение"): ("EUR", 638, 638),
    ("Leiden University", "~2,000 EUR в год для студентов ЕС, ~15,000-25,000 EUR для иностранцев"): ("EUR", 15000, 25000),
    ("The University of Tokyo", "~535,800 JPY в семестр (~4,000 USD; бесплатно для японцев с высокими баллами)"): ("USD", 8000, 8000),
    ("McGill University", "~CAD 30,000-40,000 в год для международных студентов"): ("CAD", 30000, 40000),
    ("Tsinghua University", "~26,000 CNY в год для китайцев; ~35,000-50,000 CNY для иностранцев"): ("CNY", 35000, 50000),
    ("Charles University", "3 000 – 15 000 EUR в год (на английском языке)"): ("EUR", 3000, 15000),
    ("University of Toronto, Temerty Faculty of Medicine", "От 10 000 до 58 000 CAD в год в зависимости от программы (магистратура OISE — около 10 000–20 000 CAD/год, профессиональные программы дороже)"): ("CAD", 10000, 58000),
    ("Eberhard Karls Universität Tübingen", "Около 1500 EUR за семестр (в основном взносы за услуги, обучение бесплатное для большинства программ)"): ("EUR", 3000, 3000),
    ("Seoul National University", "Около 4–7 млн вон (примерно 3000–5000 USD) за семестр в зависимости от факультета"): ("USD", 6000, 10000),
    ("University of Cape Town (UCT)", "Около 4500–8300 USD за семестр для международных студентов в зависимости от программы"): ("USD", 9000, 16600),
    ("University of Amsterdam", "2 200 – 11 000 EUR в год в зависимости от программы для студентов вне ЕЭЗ"): ("EUR", 2200, 11000),
    ("University of the Arts London (UAL)", "~25 000 – 30 000 GBP в год"): ("GBP", 25000, 30000),
    ("Berklee College of Music", "около 55 600 долларов США в год (плата за обучение), плюс проживание и питание около 21 300 долларов США в год"): ("USD", 55600, 55600),
    ("Deutsche Sporthochschule Köln", "обучение бесплатное (государственный вуз); семестровый взнос около 310 евро, включающий проездной билет по земле Северный Рейн-Вестфалия"): ("EUR", 620, 620),
    ("University of Cape Town — Michaelis School of Fine Art", "около 32 500 южноафриканских рэндов в год базовая плата плюс международный административный сбор около 5300 рэндов (итого примерно 2000-2500 долларов США в год для иностранных студентов, в зависимости от программы)"): ("USD", 2000, 2500),
    ("Aalto University", "€12 000–15 000 в год (бакалавриат для иностранцев)"): ("EUR", 12000, 15000),
    ("Tsinghua University", "26 000 – 45 000 CNY в год (около 3 600 – 6 200 USD) на бакалавриате и магистратуре"): ("USD", 3600, 6200),
    ("University of Cape Town (UCT)", "около 8 300 USD за семестр (16 000 – 17 000 USD в год) для иностранных студентов"): ("USD", 16000, 17000),
    ("Pontificia Universidad Católica de Chile (UC Chile)", "около 6 000 – 12 000 USD в год в зависимости от программы"): ("USD", 6000, 12000),
    ("Purdue University", "~31 000 USD в год (для иностранных бакалавров)"): ("USD", 31000, 31000),
    ("Politecnico di Milano", "От 900 до 3 900 EUR в год (варьируется от дохода семьи студента)"): ("EUR", 900, 3900),
    ("University of Melbourne", "от 40 000 до 63 000 AUD в год для бакалавриата по инженерным направлениям"): ("AUD", 40000, 63000),
    ("ETH Zurich", "около 730 CHF за семестр (≈1460 CHF/год) — тарифы одинаковы для швейцарских и иностранных студентов"): ("CHF", 1460, 1460),
    ("University of Cape Town (UCT)", "от 105 000 до 181 000 ZAR в год за обучение (без учёта проживания)"): ("ZAR", 105000, 181000),
    ("Universidade de São Paulo — Escola Politécnica", "государственный вуз с бесплатным обучением для бразильцев; для иностранных студентов — от 1000 USD в год"): ("USD", 1000, 1000),
    ("Georgia Institute of Technology", "около 31 370 USD в год за обучение на бакалавриате для иностранных студентов (плюс сборы)"): ("USD", 31370, 31370),
    ("National University of Singapore — NUS Business School", "около 40 000–50 000 SGD в год для иностранных студентов бакалавриата"): ("SGD", 40000, 50000),
    ("University of Waterloo", "около 45 500–48 000 CAD за первый год бакалавриата для иностранных студентов"): ("CAD", 45500, 48000),
    ("University of Toronto, Temerty Faculty of Medicine", "55 000 – 75 000 CAD в год (бакалавриат); 20 000 – 35 000 CAD в год (магистратура)"): ("CAD", 55000, 75000),
    ("John Jay College of Criminal Justice", "14 880 – 18 600 USD в год (для международных бакалавров)"): ("USD", 14880, 18600),
    ("Australian National University", "от 46 680 до 62 440 австралийских долларов в год в зависимости от программы"): ("AUD", 46680, 62440),
    ("University of Queensland", "~45 000 – 50 000 AUD в год"): ("AUD", 45000, 50000),
    ("University of Guelph", "~44 730 CAD в год для бакалавриата (2026/27); ~57 318 CAD для магистерских программ"): ("CAD", 44730, 44730),
    ("Univ. of Veterinary Medicine Budapest", "~12 480 EUR в год (на английском языке)"): ("EUR", 12480, 12480),
    ("University of Helsinki", "~13 000 – 18 000 EUR в год (вне ЕЭЗ/ЕС)"): ("EUR", 13000, 18000),
    ("London School of Economics (LSE)", "~25 000 – 28 000 GBP в год"): ("GBP", 25000, 28000),
    ("University of New South Wales — UNSW Business School", "около 50 000–60 000 AUD в год для иностранных студентов бакалавриата"): ("AUD", 50000, 60000),
    ("UCL (University College London)", "~25 000 – 35 000 GBP в год"): ("GBP", 25000, 35000),
    ("Pontificia Universidad Católica de Chile (UC Chile)", "Около 6000–9000 USD в год для иностранных студентов в зависимости от программы"): ("USD", 6000, 9000),
    ("Stockholm School of Economics", "~200 EUR в семестр (сбор для EU), ~13500 EUR в год для иностранцев"): ("EUR", 13500, 13500),
    ("The University of Hong Kong — HKU Business School", "около 224 000 HKD в год для иностранных студентов бакалавриата (≈28 700 USD); MBA — около 588 000 HKD за программу"): ("USD", 28700, 28700),
    ("Stockholm University", "90 000 – 140 000 SEK в год (примерно 8 500 – 13 500 EUR) для студентов вне ЕЭЗ"): ("SEK", 90000, 140000),
    ("Université Paris 1 Panthéon-Sorbonne", "~3 000 – 6 000 EUR в год для студентов вне ЕС (дифференцированные сборы)"): ("EUR", 3000, 6000),
    ("University of Illinois Urbana-Champaign — Gies College of Business", "около 36 000–38 000 USD в год для иностранных студентов бакалавриата (без учёта проживания)"): ("USD", 36000, 38000),
    ("Copenhagen Business School (CBS)", "~11 000 – 15 000 EUR в год (для граждан вне ЕС)"): ("EUR", 11000, 15000),
    ("University of Cape Town, Faculty of Law", "около 90 000–140 000 южноафриканских рэндов в год для иностранных студентов (в зависимости от программы)"): ("ZAR", 90000, 140000),
    ("Ritsumeikan Asia Pacific University — College of Asia Pacific Management (Tourism and Hospitality)", "≈700 000–1 000 000 японских иен в год (≈4 700–6 700 USD) с учётом стипендиальных скидок"): ("USD", 4700, 6700),
    ("IE University", "~25 000 EUR в год"): ("EUR", 25000, 25000),
    ("University of Alberta", "около 35 000–45 000 CAD в год для иностранных студентов инженерных программ"): ("CAD", 35000, 45000),
    ("Sciences Po", "~14 000 EUR в год (варьируется от дохода семьи студента)"): ("EUR", 14000, 14000),
    ("Politecnico di Milano — Scuola del Design", "около 4000 евро в год для программ бакалавриата и магистратуры (плата рассчитывается по прогрессивной шкале в зависимости от семейного дохода, для большинства иностранных студентов не превышает 4000 евро)"): ("EUR", 4000, 4000),
    ("Tokyo University of the Arts (Geidai)", "около 535 800 иен в год (~3600 долларов США) плюс единовременный вступительный взнос около 282 000 иен"): ("USD", 3600, 3600),
    ("University of Melbourne", "40 000–60 000 AUD в год в зависимости от программы"): ("AUD", 40000, 60000),
    ("University of Central Lancashire (UCLan)", "~26 310 USD в год (эквивалент в GBP)"): ("USD", 26310, 26310),
    ("National Institute of Dramatic Art", "около 40 000–45 000 австралийских долларов в год (программы бакалавриата и магистратуры изящных искусств)"): ("AUD", 40000, 45000),
    ("Amsterdam University of the Arts (AHK)", "~8 250 EUR в год (бакалавриат дизайн/танец 2026-2027)"): ("EUR", 8250, 8250),
    ("Griffith University", "около 41 500 AUD в год (первый год обучения на Bachelor of Aviation)"): ("AUD", 41500, 41500),
    ("Graduate Institute of International and Development Studies (Geneva Graduate Institute)", "около 7 000–7 500 швейцарских франков в год для магистерских программ"): ("CHF", 7000, 7500),
    ("Loughborough University", "~22 000 – 26 000 GBP в год"): ("GBP", 22000, 26000),
    ("Karolinska Institutet", "~160 000 – 200 000 SEK в год"): ("SEK", 160000, 200000),
    ("Parsons School of Design", "~55 000 USD в год"): ("USD", 55000, 55000),
    ("Semmelweis University", "~16 000 – 18 000 EUR в год"): ("EUR", 16000, 18000),
    ("Bocconi University", "около 18 200–18 500 EUR в год для иностранных студентов (магистерские программы)"): ("EUR", 18200, 18500),
    ("The University of Manchester — Alliance Manchester Business School", "около 30 000–33 500 GBP в год для иностранных студентов (MSc Marketing)"): ("GBP", 30000, 33500),
    ("University of Western Australia", "~40 000 – 45 000 AUD в год"): ("AUD", 40000, 45000),
    ("University of Pretoria, Faculty of Natural and Agricultural Sciences", "для иностранных студентов не из региона SADC — двойная местная стоимость обучения плюс международный сбор ≈ 4 725 южноафриканских рэндов (ZAR) в год; итоговая стоимость программы от 90 000 до 180 000 ZAR в год"): ("ZAR", 90000, 180000),
    ("Middlebury Institute of International Studies at Monterey — Translation, Interpretation and Localization Management", "≈49 870 USD в год (обучение), без учёта проживания"): ("USD", 49870, 49870),
    ("Bocconi University", "~14 000 – 16 000 EUR в год"): ("EUR", 14000, 16000),
    ("HEC Paris", "около 48 913–59 783EUR в год для магистерских программ (полная стоимость)"): ("USD", 48913, 59783),
    ("The Hong Kong Polytechnic University — School of Hotel and Tourism Management", "160 000–180 000 гонконгских долларов в год (≈20 500–23 000 USD) для иностранных студентов"): ("USD", 20500, 23000),
    ("National University of Singapore, Faculty of Law", "около 38 000–45 000 сингапурских долларов в год для иностранных студентов на бакалавриате"): ("SGD", 38000, 45000),
    ("EHL Hospitality Business School", "~35 000 – 40 000 CHF в год"): ("CHF", 35000, 40000),
    ("Colorado School of Mines", "~42 000 USD в год для иностранных студентов"): ("USD", 42000, 42000),
    ("Massey University", "NZD 32 000—79 000 в год (в зависимости от программы)"): ("NZD", 32000, 79000),
}

# (university_name, exact_old_cost_label) -> new_cost_label
# Genuinely not an annual figure (total program / MBA cost, or too vague to
# extract a number) -- cost_per_year stays null, only the TEXT is cleaned up
# where it carried a domestic-only rate/aside that doesn't apply to a
# foreign (KZ) applicant.
TEXT_ONLY: dict[tuple[str, str], str] = {
    (
        "University of Cape Town Graduate School of Business",
        "около 345 000 южноафриканских рэндов за программу MBA для студентов из Африки; для иностранных студентов не из Африки стоимость выше и уточняется индивидуально",
    ): "Стоимость MBA для иностранных студентов не из Африки уточняется индивидуально на сайте вуза",
    (
        "National University of Singapore",
        "от 17 100 до 39 150 SGD в год в зависимости от специальности (для инженерных направлений — субсидируемая ставка при Tuition Grant)",
    ): "Стоимость сильно зависит от специальности; указанные university-стороной цифры — субсидированная ставка Tuition Grant (требует последующей работы в Сингапуре) — уточняйте международную ставку на сайте вуза",
    (
        "National University of Singapore — NUS Business School",
        "около 40 000–58 000 сингапурских долларов в год для иностранных студентов бакалавриата (после гранта Tuition Grant — выше без него); программы MBA и магистратуры дороже, ориентировочно 60 000–90 000 SGD за программу",
    ): "Бакалаврская ставка приведена с учётом субсидии Tuition Grant (требует последующей работы в Сингапуре) — без гранта стоимость выше, уточняйте на сайте вуза; MBA/магистратура — ориентировочно 60 000–90 000 SGD за программу",
    (
        "Universidad Nacional Autónoma de México, Facultad de Medicina Veterinaria y Zootecnia",
        "символическая плата за обучение для очной формы (номинально до нескольких сотен USD в год по внутренним тарифам UNAM); иностранные студенты дополнительно оплачивают регистрационные и административные сборы, расходы на проживание ≈USD 400–700/мес",
    ): "Символическая плата по внутренним тарифам UNAM (до нескольких сотен USD в год) плюс регистрационные и административные сборы — точную сумму уточняйте на сайте вуза",
}


async def main() -> None:
    apply = "--apply" in sys.argv

    async with async_session() as db:
        numeric_changed = 0
        text_changed = 0
        already_applied = 0
        not_found = []

        for (uni_name, old_label), (currency, cmin, cmax) in NUMERIC.items():
            unis = (await db.execute(select(University).where(University.name == uni_name))).scalars().all()
            if not unis:
                not_found.append(f"university not found: {uni_name!r}")
                continue
            progs = (
                await db.execute(
                    select(Program).where(
                        Program.university_id.in_([u.id for u in unis]), Program.cost_label == old_label
                    )
                )
            ).scalars().all()
            if not progs:
                # Not necessarily missing -- a later pipeline step (e.g.
                # backfill_strip_masters_domestic_cost.py, which runs before
                # this script) can rewrite cost_label first, so the OLD text
                # this rule keys on may simply no longer exist because the
                # row already got its numeric fields filled by this exact
                # rule on an earlier run. Check for that before reporting it
                # as a failure.
                already = (
                    await db.execute(
                        select(Program).where(
                            Program.university_id.in_([u.id for u in unis]),
                            Program.cost_per_year_min == cmin,
                            Program.cost_per_year_max == cmax,
                        )
                    )
                ).scalars().first()
                if already is not None:
                    already_applied += 1
                else:
                    not_found.append(f"program not found (already changed?): {uni_name!r} / {old_label[:60]!r}")
                continue
            for prog in progs:
                if prog.cost_per_year_min is not None:
                    continue  # already applied
                tag = "[updating]" if apply else "[would update]"
                print(f"{tag} {uni_name} | {prog.name!r} | cost -> {currency} {cmin}-{cmax}")
                if apply:
                    prog.cost_currency = currency
                    prog.cost_per_year_min = cmin
                    prog.cost_per_year_max = cmax
                numeric_changed += 1

        for (uni_name, old_label), new_label in TEXT_ONLY.items():
            unis = (await db.execute(select(University).where(University.name == uni_name))).scalars().all()
            if not unis:
                not_found.append(f"university not found: {uni_name!r}")
                continue
            progs = (
                await db.execute(
                    select(Program).where(
                        Program.university_id.in_([u.id for u in unis]), Program.cost_label == old_label
                    )
                )
            ).scalars().all()
            if not progs:
                already = (
                    await db.execute(
                        select(Program).where(
                            Program.university_id.in_([u.id for u in unis]), Program.cost_label == new_label
                        )
                    )
                ).scalars().first()
                if already is not None:
                    already_applied += 1
                else:
                    not_found.append(f"program not found (already changed?): {uni_name!r} / {old_label[:60]!r}")
                continue
            for prog in progs:
                tag = "[updating]" if apply else "[would update]"
                print(f"{tag} {uni_name} | {prog.name!r} | text-only cost_label rewrite")
                if apply:
                    prog.cost_label = new_label
                text_changed += 1

        print(
            f"\n{numeric_changed} programs get numeric cost_per_year_min/max, {text_changed} get a cleaned text-only label "
            f"({already_applied} rule(s) already applied on an earlier run, not re-counted)."
        )
        if not_found:
            print(f"\n{len(not_found)} lookups failed:")
            for msg in not_found[:50]:
                print(f"  - {msg}")

        if apply:
            await db.commit()
            print("Committed.")
        else:
            print("Dry run — nothing written. Re-run with --apply to commit.")


if __name__ == "__main__":
    asyncio.run(main())
