import asyncio
import json
import os
import sys
import re
from datetime import datetime, timezone

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from app.database import async_session
from app.models.program import Program
from app.models.university import University

CLASSIFIER_CODE_TO_EXAMS = {
    # Education / Pedagogy
    "B001": ["Биология", "География", "Специальный педагогический экзамен"],
    "B002": ["Биология", "География", "Специальный педагогический экзамен"],
    "B003": ["Биология", "География", "Специальный педагогический экзамен"],
    "B004": ["2 Творческих экзамена", "Специальный педагогический экзамен"],
    "B005": ["2 Творческих экзамена"],
    "B006": ["2 Творческих экзамена", "Специальный педагогический экзамен"],
    "B007": ["2 Творческих экзамена", "Специальный педагогический экзамен"],
    "B008": ["География", "Всемирная история", "Специальный педагогический экзамен"],
    "B009": ["Математика", "Физика", "Специальный педагогический экзамен"],
    "B010": ["Математика", "Физика", "Специальный педагогический экзамен"],
    "B011": ["Математика", "Информатика", "Специальный педагогический экзамен"],
    "B012": ["Химия", "Биология", "Специальный педагогический экзамен"],
    "B013": ["Биология", "Химия", "Специальный педагогический экзамен"],
    "B014": ["География", "Биология", "Специальный педагогический экзамен"],
    "B015": ["Всемирная история", "География", "Специальный педагогический экзамен"],
    "B016": ["Казахский язык", "Казахская литература", "Специальный педагогический экзамен"],
    "B017": ["Русский язык", "Русская литература", "Специальный педагогический экзамен"],
    "B018": ["Иностранный язык", "Всемирная история", "Специальный педагогический экзамен"],
    "B019": ["Биология", "География", "Специальный педагогический экзамен"],
    "B020": ["Биология", "География", "Специальный педагогический экзамен"],
    
    # Arts and Humanities
    "B023": ["2 Творческих экзамена"],
    "B029": ["2 Творческих экзамена"],
    "B031": ["2 Творческих экзамена"],
    "B032": ["Всемирная история", "География"],
    "B033": ["Всемирная история", "География"],
    "B034": ["Всемирная история", "География"],
    "B036": ["Иностранный язык", "Всемирная история"],
    "B038": ["Математика", "География"],
    "B040": ["Всемирная история", "География"],
    "B041": ["Биология", "География"],
    "B042": ["2 Творческих экзамена"],
    "B043": ["Всемирная история", "География"],
    
    # Business, Management, Law
    "B044": ["Математика", "География"],
    "B045": ["Математика", "География"],
    "B046": ["Математика", "География"],
    "B047": ["Математика", "География"],
    "B049": ["Всемирная история", "Человек.Общество.Право"],
    
    # Natural Sciences
    "B050": ["Биология", "Химия"],
    "B051": ["Биология", "География"],
    "B052": ["География", "Математика"],
    "B053": ["Химия", "Физика"],
    "B054": ["Физика", "Математика"],
    "B055": ["Математика", "Физика"],
    "B057": ["Математика", "Информатика"],
    "B058": ["Математика", "Информатика"],
    "B059": ["Математика", "Физика"],
    
    # Engineering & Technology
    "B062": ["Математика", "Физика"],
    "B063": ["Математика", "Физика"],
    "B064": ["Математика", "Физика"],
    "B065": ["Математика", "Физика"],
    "B066": ["Математика", "Физика"],
    "B067": ["Математика", "Физика"],
    "B068": ["Химия", "Биология"],
    "B070": ["Математика", "Физика"],
    "B071": ["Математика", "Физика"],
    "B072": ["Химия", "Биология"],
    "B073": ["2 Творческих экзамена"],
    "B074": ["Математика", "Физика"],
    "B076": ["Математика", "Физика"],
    
    # Agriculture
    "B077": ["Биология", "Химия"],
    "B078": ["Биология", "Химия"],
    "B082": ["Математика", "Физика"],
    "B183": ["Математика", "Физика"],
    
    # Health & Services
    "B085": ["Биология", "Химия"],
    "B090": ["Биология", "География"],
    "B091": ["География", "Иностранный язык"],
    "B092": ["2 Творческих экзамена"],
    "B093": ["География", "Иностранный язык"],
    
    # Others
    "B126": ["Математика", "Физика"],
    "B135": ["Иностранный язык", "Всемирная история"],
    "B140": ["Иностранный язык", "Всемирная история"],
    "B142": ["Иностранный язык", "Всемирная история"],
    "B157": ["Математика", "Информатика"],
    "B158": ["Математика", "Информатика"],
    "B162": ["Математика", "Физика"],
    "B167": ["Математика", "Физика"],
    "B265": ["Математика", "Физика"]
}

def get_min_ent_threshold(code: str) -> int:
    if code.startswith("B00") or code.startswith("B01") or code == "B020":
        return 75  # Педагогика
    if code == "B049":
        return 75  # Право
    if code in ["B084", "B085", "B086", "B087", "B088", "B089"]:
        return 70  # Здравоохранение
    return 50  # Остальные

def classify_program(name: str) -> str | None:
    n = name.lower().replace('ё', 'е')
    
    # 1. First-level highly specific keywords
    if 'дошкольн' in n or 'preschool' in n or 'детск' in n or 'сад' in n: return 'B002'
    if 'дефектол' in n or 'логопед' in n or 'defectolog' in n: return 'B020'
    if 'начальн' in n and ('обучен' in n or 'метод' in n or 'класс' in n): return 'B003'
    if 'воен' in n and ('подготовк' in n or 'кафедр' in n): return 'B004'
    
    if any(k in n for k in ['спорт', 'физкультур', 'физическая культур', 'физическ', 'тренер', 'athletic', 'sport', 'олимписк', 'фитнес', 'рекреац']):
        # If it has "физическ" and "культур"
        if 'культур' in n or 'спорт' in n or 'фитнес' in n or 'рекреац' in n:
            return 'B005'
        
    if any(k in n for k in ['актер', 'acting', 'режисс', 'directing', 'театр', 'драм', 'кино', 'film', 'дирижир', 'дириже']):
        return 'B023'
        
    if any(k in n for k in ['дизайн', 'design', 'мод', 'fashion', 'одежд', 'швейн', 'текстиль', 'легкои пром', 'легкой пром', 'художн']):
        return 'B031'
        
    if any(k in n for k in ['журналист', 'journalism', 'репортер', 'писател', 'копирайт']):
        return 'B042'
        
    if 'фармац' in n or 'pharmac' in n:
        if 'производ' in n or 'технол' in n: return 'B072'
        return 'B085'
        
    if 'ветеринар' in n or 'veterin' in n: return 'B078'
    if 'водн' in n or 'water' in n: return 'B082'
    if 'судовожд' in n: return 'B066'
    
    # Specific languages and Philology (RU & KZ)
    if 'казах' in n or 'kazakh' in n:
        if 'язык' in n or 'литератур' in n or 'филолог' in n:
            return 'B016'
    if 'русск' in n or 'russian' in n:
        if 'язык' in n or 'литератур' in n or 'филолог' in n:
            return 'B017'
            
    # Pedagogy / Education (RU & EN)
    if any(k in n for k in ['педагог', 'учитель', 'преподав', 'обучен', 'педагогика', 'pedagogy', 'education', 'teaching', 'методика', 'образование', 'образования', 'обществовед', 'обществознан']):
        if 'математик' in n or 'math' in n: return 'B009'
        if 'физик' in n or 'physic' in n: return 'B010'
        if 'информатик' in n or 'inform' in n: return 'B011'
        if 'хими' in n or 'chem' in n: return 'B012'
        if 'биолог' in n or 'biol' in n: return 'B013'
        if 'географ' in n or 'geogr' in n: return 'B014'
        if 'истори' in n or 'hist' in n or 'обществовед' in n or 'обществознан' in n: return 'B015'
        if 'социальн' in n or 'social' in n: return 'B019'
        if 'музык' in n or 'music' in n: return 'B006'
        if 'художеств' in n or 'черчен' in n or 'art' in n: return 'B007'
        if 'психолог' in n or 'psychology' in n: return 'B001'
        return 'B003'

    # General psychology (after pedagogy check)
    if 'психолог' in n or 'psychology' in n or 'когнитив' in n: return 'B041'

    # English Engineering / Science rules (run first to catch specific matches)
    if 'engineering' in n or 'engineer' in n:
        if any(k in n for k in ['electrical', 'electro', 'electronic', 'devices', 'приборостр', 'электр']): return 'B062'
        if any(k in n for k in ['software', 'systems', 'computing', 'it', 'ai', 'data', 'интернет']): return 'B057'
        if any(k in n for k in ['mining', 'petroleum', 'mineral', 'gas', 'oil', 'геологоразвед', 'разведка', 'горн', 'нефт', 'бурен', 'уран']): return 'B071'
        if any(k in n for k in ['civil', 'construction', 'строитель']): return 'B074'
        if any(k in n for k in ['chemical', 'material', 'metallurgy', 'металлург', 'химия', 'металл']): return 'B064'
        if 'agro' in n or 'аграр' in n or 'фермер' in n or 'сельхоз' in n or 'агро' in n: return 'B183'
        return 'B064'
        
    if 'science' in n or 'sciences' in n:
        if any(k in n for k in ['computer', 'data', 'computing', 'information', 'programming']): return 'B057'
        if any(k in n for k in ['biological', 'medical', 'health', 'life']): return 'B086'
        if any(k in n for k in ['earth', 'geological', 'geography']): return 'B052'
        if 'political' in n: return 'B040'
        if 'social' in n: return 'B038'

    # IT and computer science (RU & EN)
    if any(k in n for k in ['информацион', 'компьютер', 'вычислительн', 'программн', 'it', 'computer', 'software', 'data science', 'искусствен', 'artificial', 'intelligence', 'machine learning', 'разработк', 'web', 'кибер', 'cyber', 'программист', 'баз данных', 'информатика', 'вычислени', 'programming', 'системный администратор', 'вычислительная', 'ai', 'data', 'computing', 'systems', 'smart', 'технологии', 'вычисления', 'данн', 'данных', 'крипто', 'сетев', 'сети', 'телематик', 'internet of things', 'things', 'защиты информации', 'поддержк']):
        if 'безопасн' in n or 'security' in n or 'крипто' in n or 'защит' in n or 'защиты информации' in n: return 'B058'
        if 'моделир' in n: return 'B157'
        return 'B057'

    # Business, Finance, Economics, Management (RU & EN)
    if any(k in n for k in ['финанс', 'экономик', 'эконом', 'finance', 'economics', 'управление', 'менеджмент', 'management', 'бизнес', 'business', 'маркетинг', 'marketing', 'учет', 'аудит', 'accounting', 'логистик', 'logistics', 'государствен', 'местн', 'trade', 'commerce', 'рынок', 'рынки', 'fintech', 'economy', 'hr', 'менеджер', 'sales', 'продаж', 'предпринимат', 'mba', 'bba', 'бухгалт', 'налог', 'market', 'рынков', 'брокер', 'кредит', 'аналитик', 'риелтор', 'закупк', 'кадровому', 'секретар', 'делопроизвод', 'страхов']):
        if 'государствен' in n or 'public' in n: return 'B044'
        if 'аудит' in n or 'accounting' in n or 'учет' in n or 'бухгалт' in n: return 'B045'
        if 'маркетинг' in n or 'marketing' in n or 'реклам' in n or 'reklama': return 'B047'
        if 'логистик' in n or 'logistics' in n: return 'B065'
        return 'B046'

    # Law
    if any(k in n for k in ['право', 'юриспруд', 'law', 'юрист', 'юрид', 'судебн', 'legal', 'дипломат', 'полицейс', 'криминал', 'таможен']):
        return 'B049'

    # Art, Design, Journalism, Media (RU & EN)
    if any(k in n for k in ['дизайн', 'design', 'мод', 'fashion', 'одежд', 'швейн', 'анимац', 'анимат', 'visual effects', '3d', '2d', 'живопись', 'график', 'скульпт', 'искусств', 'изобразительн', 'акварель', 'фотограф']):
        return 'B031'
    if any(k in n for k in ['журналист', 'journalism', 'связь с общественностью', 'pr', 'public relations', 'связи с общественностью', 'пиар']):
        return 'B042'
    if any(k in n for k in ['режиссур', 'актер', 'театр', 'кино', 'film', 'acting', 'сцен', 'хореограф', 'танец', 'танц', 'балет', 'драм', 'performance', 'операторск']):
        return 'B023'
    if any(k in n for k in ['медиа', 'media', 'аудио', 'звук', 'телевиз', 'радио', 'вещание']):
        return 'B029'
    if any(k in n for k in ['консерват', 'инструмент', 'дирижер', 'вокал', 'пение', 'музык', 'music', 'певец', 'оркестр', 'хор', 'музыкальное', 'композ', 'дирижир']):
        return 'B006'

    # Natural Sciences
    if 'биотехнолог' in n: return 'B050'
    if any(k in n for k in ['биолог', 'biolog', 'biology', 'biological', 'микробиол', 'генетик']): return 'B050'
    if any(k in n for k in ['эколог', 'ecology', 'окружающ', 'environmental', 'природопольз', 'жизнедеят', 'техносфер', 'спасател', 'мчс']): return 'B051'
    if any(k in n for k in ['геолог', 'geolog', 'земл', 'earth', 'географ', 'geography', 'недра', 'картогр', 'геодез', 'землеустр', 'метеорол', 'сейсмол']): return 'B052'
    if any(k in n for k in ['хими', 'chemi', 'chemistry', 'chemical']): return 'B053'
    if any(k in n for k in ['физик', 'physi', 'physics', 'physical', 'астрон']): return 'B054'
    if any(k in n for k in ['математик', 'mathe', 'mathematics', 'статистик', 'statistics', 'актуари', 'аналитик данных', 'data analyst']): return 'B055'

    # Engineering (RU)
    if 'архитект' in n or 'architect' in n: return 'B073'
    if any(k in n for k in ['строитель', 'civil', 'бетон', 'конструкц', 'дорожн', 'трубопровод', 'здани', 'сооружен', 'проектир']): return 'B074'
    if any(k in n for k in ['электр', 'power', 'энерг', 'тепло', 'канализ', 'водоснабж', 'водоотвед']):
        if 'тепло' in n or 'heat' in n: return 'B162'
        return 'B062'
    if any(k in n for k in ['автоматиз', 'control', 'робот', 'robot', 'прибор', 'датчик', 'мехатрон', 'интернет вещ']): return 'B063'
    if any(k in n for k in ['механик', 'mechan', 'машино', 'металлург', 'литейного', 'металло', 'сварка', 'гидравл', 'станки', 'материал', 'металл', 'metallurgy', 'нанотехнолог', 'инженер', 'инженерия', 'технологические машины', 'технологических машин', 'технология производства']): return 'B064'
    if any(k in n for k in ['транспорт', 'автомобил', 'поезд', 'железнодорож', 'вагон', 'путевые', 'самолет', 'двигател', 'локомотив', 'путев', 'путейск', 'движен']):
        if 'железно' in n or 'жд' in n or 'локомотив' in n or 'путейск' in n or 'путев' in n: return 'B265'
        return 'B065'
    if any(k in n for k in ['авиа', 'летал', 'flight', 'pilot', 'воздушн', 'вертолет', 'космическ', 'маи', 'дроны', 'aircraft', 'аэропорт', 'авионик']):
        if any(k in n for k in ['expert', 'эксплуат', 'пилот', 'летн', 'навигац', 'авионик']): return 'B167'
        return 'B067'
    if any(k in n for k in ['стандарт', 'метрол', 'сертифик', 'качество', 'качества']): return 'B076'
    if any(k in n for k in ['горн', 'нефт', 'бурен', 'добыч', 'скважин', 'рудник', 'шахт', 'геологоразвед', 'разведка', 'полезн', 'ископаем', 'уран']): return 'B071'
    if any(k in n for k in ['аграр', 'сельхоз', 'агроинженер', 'механизац', 'фермер', 'агро']): return 'B183'

    # Medicine & Health
    if any(k in n for k in ['фармац', 'pharmac', 'аптек']):
        if 'производ' in n or 'технол' in n: return 'B072'
        return 'B085'
    if any(k in n for k in ['медицин', 'врач', 'medicine', 'doctor', 'клиническ', 'стоматолог', 'педиатр', 'сестринск', 'nursing', 'здравоохр', 'hygiene', 'гигиен', 'акушер', 'фармакология', 'здоровье', 'анатом', 'профилактическ', 'реабилитолог', 'эрготерапевт', 'резидентур', 'санитарн']):
        return 'B086'

    # Services & Agriculture
    if any(k in n for k in ['туризм', 'tourism', 'гид', 'евразийские исследования', 'краевед']): return 'B091'
    if any(k in n for k in ['ресторан', 'гостинич', 'hospitality', 'отель', 'сервис', 'кулинар', 'повар', 'гостеприим']): return 'B093'
    if any(k in n for k in ['растениевод', 'агроном', 'плодоовощ', 'почвовед', 'защита растений', 'аграрный', 'агрон', 'лесн', 'плодовод', 'сельское хозяйство']): return 'B077'
    if any(k in n for k in ['животновод', 'ветеринар', 'скотовод', 'птицевод', 'зверовод', 'охотовед', 'рыбовод', 'зоотех', 'аквакультур', 'пчеловод']): return 'B078'
    if any(k in n for k in ['водн', 'water', 'мелиор', 'гидротех', 'канализ', 'водоснабж']): return 'B082'
    if any(k in n for k in ['пищев', 'продовольств', 'перерабатыв', 'технолог пищевого']): return 'B068'

    # Languages and Philology (general language - placed after specific ones)
    if any(k in n for k in ['английск', 'english', 'немецк', 'german', 'француз', 'french', 'иностран', 'foreign', 'язык', 'языки', 'литератур', 'филолог', 'philolog', 'лингвист', 'linguist', 'языкознан', 'language', 'literature', 'перевод', 'translation']):
        # If it's a teacher training program, return B018, else translation B036
        if 'пед' in n or 'учител' in n or 'преподав' in n or 'обучен' in n or 'два' in n: return 'B018'
        return 'B036'

    # Others
    if ('международн' in n or 'international' in n) and ('отношен' in n or 'diplom' in n or 'relation' in n or 'relations' in n or 'международные' in n or 'дипломат' in n or 'international relations' in n or 'relations' in n): return 'B140'
    if any(k in n for k in ['перевод', 'translation', 'interpreting']): return 'B036'
    if 'востоковед' in n or 'oriental' in n or 'тюрколог' in n: return 'B135'
    if 'истори' in n or 'history' in n or 'археолог' in n or 'archaeology' in n: return 'B034'
    if 'философ' in n or 'philosophy' in n or 'культуролог' in n: return 'B032'
    if 'религио' in n or 'теолог' in n or 'ислам' in n or 'religi' in n or 'theolog' in n: return 'B033'
    if 'социолог' in n or 'sociology' in n or 'антропол' in n or 'anthropology' in n: return 'B038'
    if 'политолог' in n or 'political' in n: return 'B040'
    if 'библиотеч' in n or 'архивн' in n or 'библиотек' in n or 'архив' in n or 'архивариус' in n or 'библиотекарь' in n: return 'B043'
    if 'социальная работа' in n or 'social work' in n or 'соцпед' in n or 'социальный работник' in n or 'молодеж' in n: return 'B090'
    if 'регионовед' in n or 'regional studies' in n: return 'B140'
    if 'коммуникац' in n or 'communication' in n: return 'B059'
    if 'досуг' in n or 'культурно-досуг' in n: return 'B092'

    return None

async def main() -> None:
    dry_run = "--dry-run" in sys.argv

    # Load raw grant scores
    grant_scores_path = "scripts/data/grant_scores_2026_clean.json"
    with open(grant_scores_path, encoding="utf-8") as f:
        grant_scores = json.load(f)

    # Group grant scores by (specialty_code, ovpo_code) for fast lookup
    grant_lookup = {}
    for entry in grant_scores:
        key = (entry["specialty_code"], entry["ovpo"])
        grant_lookup.setdefault(key, []).append(entry)

    checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    async with async_session() as db:
        # Load all programs of Kazakhstan universities
        result = await db.execute(
            select(Program).options(joinedload(Program.university)).join(University).where(University.country == "Казахстан")
        )
        programs = result.scalars().all()

        print(f"Loaded {len(programs)} programs for KZ universities.")

        updated = 0
        unclassified_count = 0
        grant_matches = 0

        for program in programs:
            code = classify_program(program.name)
            if not code:
                print(f"[warning] Unclassified program name: '{program.name}' (ID: {program.id})")
                unclassified_count += 1
                continue

            requirements = dict(program.requirements or {})
            fact_sources = dict(program.fact_sources or {})
            changed = False

            # 1. Update exams and min threshold
            exams = CLASSIFIER_CODE_TO_EXAMS.get(code)
            min_ent_threshold = get_min_ent_threshold(code)

            if exams and requirements.get("exams") != exams:
                requirements["exams"] = exams
                fact_sources["requirements.exams"] = {
                    "url": "Приказ МОН РК о профильных предметах ЕНТ 2026",
                    "checked_at": checked_at
                }
                changed = True

            if requirements.get("min_ent_threshold") != min_ent_threshold:
                requirements["min_ent_threshold"] = min_ent_threshold
                fact_sources["requirements.min_ent_threshold"] = {
                    "url": "Норматив пороговых баллов ЕНТ МОН РК 2026",
                    "checked_at": checked_at
                }
                changed = True

            # 2. Match grant scores
            ovpo_code = program.university.ovpo_code
            matched_scores = []
            if ovpo_code:
                # Find matching scores in PDF
                entries = grant_lookup.get((code, ovpo_code)) or []
                for entry in entries:
                    quota_name = "Общий конкурс" if entry["quota"] == "ОБЩИЙ КОНКУРС" else (
                        "Сельская квота" if entry["quota"] == "СЕЛЬСКАЯ КВОТА" else entry["quota"]
                    )
                    # Keep main general and rural competition entries
                    if entry["quota"] in ["ОБЩИЙ КОНКУРС", "СЕЛЬСКАЯ КВОТА"]:
                        min_score = entry["min_score"]
                        max_score = entry["max_score"]
                        if min_score is not None and min_ent_threshold is not None and min_score < min_ent_threshold:
                            min_score = min_ent_threshold
                        if max_score is not None and min_ent_threshold is not None and max_score < min_ent_threshold:
                            max_score = min_ent_threshold
                        
                        matched_scores.append({
                            "ovpo": entry["ovpo"],
                            "specialty_code": entry["specialty_code"],
                            "specialty_name": entry["specialty_name"],
                            "quota": quota_name,
                            "min_score": min_score,
                            "max_score": max_score,
                            "year": entry["year"]
                        })

            # Check if admission_scores_2026 changed
            if matched_scores:
                grant_matches += 1
                if requirements.get("admission_scores_2026") != matched_scores:
                    requirements["admission_scores_2026"] = matched_scores
                    fact_sources["requirements.admission_scores_2026"] = {
                        "url": "Официальный список обладателей образовательных грантов МОН РК 2026",
                        "checked_at": checked_at
                    }
                    changed = True
            elif "admission_scores_2026" in requirements:
                # If there are no longer scores, clear them
                del requirements["admission_scores_2026"]
                if "requirements.admission_scores_2026" in fact_sources:
                    del fact_sources["requirements.admission_scores_2026"]
                changed = True

            if changed:
                updated += 1
                if dry_run:
                    print(f"[would update] {program.university.name} / {program.name} -> code: {code}, exams: {exams}, threshold: {min_ent_threshold}, grant: {bool(matched_scores)}")
                else:
                    program.requirements = requirements
                    program.fact_sources = fact_sources

        if not dry_run:
            await db.commit()

        print(f"\n{'DRY RUN — ' if dry_run else ''}Programs updated: {updated}")
        print(f"Unclassified: {unclassified_count}")
        print(f"Matched with grant scores: {grant_matches}")

if __name__ == "__main__":
    asyncio.run(main())
