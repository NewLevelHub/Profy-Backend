# University snapshot — normalize report

Input : `C:\Users\amanz\OneDrive\Desktop\ProfOr\profi-backend\scripts\data\university_snapshot.json`
Output: `C:\Users\amanz\OneDrive\Desktop\ProfOr\profi-backend\scripts\data\university_snapshot.clean.json`

## A/B — stripped fields

- ranking fields removed: 12615 (from universities)
- cost fields removed: 62865 (from programs)

## C — duplicate universities merged

**18 auto-merges.**

- **keep** University of Oxford [Оксфорд, Великобритания] slug=university-of-oxford
  **absorb** University of Oxford [Лондон, Великобритания] slug=university-of-oxford-2  (jinaq_id=61)
  → +5 programs, 0 name-collisions skipped, filled: contacts, facilities
- **keep** Университет «Туран-Астана» [Астана, Казахстан] slug=turan-astana
  **absorb** Университет «Туран-Астана» [Нур-Султан, Казахстан] slug=universitet-turan-astana  (jinaq_id=987)
  → +0 programs, 7 name-collisions skipped, filled: contacts, facilities
- **keep** University of Waterloo [Ватерлоо, Канада] slug=university-of-waterloo-actuarial-science
  **absorb** University of Waterloo [Торонто, Канада] slug=university-of-waterloo  (jinaq_id=134)
  → +2 programs, 0 name-collisions skipped, filled: contacts, facilities
- **keep** Leiden University [Лейден, Нидерланды] slug=leiden-university
  **absorb** Leiden University [Амстердам, Нидерланды] slug=leiden-university-2  (jinaq_id=79)
  → +3 programs, 0 name-collisions skipped, filled: contacts, facilities
- **keep** Wageningen University & Research [Вагенинген, Нидерланды] slug=wageningen-university
  **absorb** Wageningen University & Research [Амстердам, Нидерланды] slug=wageningen-university-and-research  (jinaq_id=80)
  → +3 programs, 0 name-collisions skipped, filled: short_name, contacts, facilities
- **keep** Massey University [Палмерстон-Норт, Новая Зеландия] slug=massey-university
  **absorb** Massey University [Веллингтон, Новая Зеландия] slug=massey-university-2  (jinaq_id=124)
  → +3 programs, 0 name-collisions skipped, filled: contacts, facilities
- **keep** Stanford University [Стэнфорд, США] slug=stanford-university
  **absorb** Stanford University [Бостон, США] slug=stanford-university-2  (jinaq_id=128)
  → +6 programs, 0 name-collisions skipped, filled: contacts, facilities
- **keep** Satbayev University (Университет Сатпаева) [Алматы, Казахстан] slug=satbayev-university
  **absorb** Satbayev University [Алматы, Казахстан] slug=satbayev-university-2  (jinaq_id=3)
  → +7 programs, 3 name-collisions skipped, filled: contacts, facilities
- **keep** Алматинский гуманитарно-экономический университет (АГЭУ) [Алматы, Казахстан] slug=almatinskij-gumanitarno-ekonomicheskij-universitet
  **absorb** Алматинский гуманитарно-экономический университет [Алматы, Казахстан] slug=almatinskiy-gumanitarno-ekonomicheskiy-universitet  (jinaq_id=959)
  → +6 programs, 1 name-collisions skipped, filled: contacts, facilities
- **keep** Алматинский технологический университет (АТУ) [Алматы, Казахстан] slug=almatinskij-tehnologicheskij-universitet
  **absorb** Алматинский технологический университет [Алматы, Казахстан] slug=almatinskiy-tehnologicheskiy-universitet  (jinaq_id=955)
  → +8 programs, 0 name-collisions skipped, filled: contacts, facilities
- **keep** Алматинский университет энергетики и связи (АУЭС) [Алматы, Казахстан] slug=almatinskij-universitet-energetiki-i-svyazi
  **absorb** Алматинский университет энергетики и связи [Алматы, Казахстан] slug=almatinskiy-universitet-energetiki-i-svyazi  (jinaq_id=985)
  → +2 programs, 7 name-collisions skipped, filled: contacts, facilities
- **keep** Казахская академия спорта и туризма (КАСТ) [Алматы, Казахстан] slug=kazahskaya-akademiya-sporta-i-turizma
  **absorb** Казахская академия спорта и туризма [Алматы, Казахстан] slug=kazahskaya-akademiya-sporta-i-turizma-2  (jinaq_id=974)
  → +0 programs, 6 name-collisions skipped, filled: contacts, facilities
- **keep** Казахский национальный аграрный исследовательский университет (КазНАИУ) [Алматы, Казахстан] slug=kazahskij-naczionalnyj-agrarnyj-issledovatelskij-universitet
  **absorb** Казахский национальный аграрный исследовательский университет [Алматы, Казахстан] slug=kazahskiy-natsionalnyy-agrarnyy-issledovatelskiy-universitet  (jinaq_id=968)
  → +6 programs, 0 name-collisions skipped, filled: contacts, facilities
- **keep** Казахстанско-Британский технический университет (КБТУ) [Алматы, Казахстан] slug=kazahstansko-britanskij-tehnicheskij-universitet
  **absorb** Казахстанско-Британский Технический Университет [Алматы, Казахстан] slug=kazahstansko-britanskiy-tehnicheskiy-universitet  (jinaq_id=954)
  → +8 programs, 0 name-collisions skipped, filled: contacts, facilities
- **keep** Казахстанско-Немецкий университет (КНУ) [Алматы, Казахстан] slug=kazahstansko-nemeczkij-universitet
  **absorb** Казахстанско-Немецкий университет [Алматы, Казахстан] slug=kazahstansko-nemetskiy-universitet  (jinaq_id=978)
  → +4 programs, 3 name-collisions skipped, filled: contacts, facilities
- **keep** Казахстанско-Российский медицинский университет (КРМУ) [Алматы, Казахстан] slug=kazahstansko-rossijskij-mediczinskij-universitet
  **absorb** Казахстанско-Российский медицинский университет [Алматы, Казахстан] slug=kazahstansko-rossiyskiy-meditsinskiy-universitet  (jinaq_id=979)
  → +4 programs, 2 name-collisions skipped, filled: contacts, facilities
- **keep** Международный университет информационных технологий (МУИТ) [Алматы, Казахстан] slug=mezhdunarodnyj-universitet-informaczionnyh-tehnologij
  **absorb** Международный университет информационных технологий [Алматы, Казахстан] slug=mezhdunarodnyy-universitet-informatsionnyh-tehnologiy  (jinaq_id=984)
  → +4 programs, 0 name-collisions skipped, filled: contacts, facilities
- **keep** Nanyang Technological University (NTU) [Сингапур, Сингапур] slug=ntu-singapore
  **absorb** Nanyang Technological University [Сингапур, Сингапур] slug=nanyang-technological-university  (jinaq_id=107)
  → +8 programs, 0 name-collisions skipped, filled: contacts, facilities

## C — same-name groups NOT merged (manual review): 11

- _both have jinaq_id (name)_
  - Университет Виктории [Мельбурн, Австралия] slug=universitet-viktorii
  - Университет Виктории [Виктория, Канада] slug=universitet-viktorii-2
- _both have jinaq_id (name)_
  - Университет Нью-Ингленда [Армидейл, Австралия] slug=universitet-nyu-inglenda
  - Университет Нью-Ингленда [Арнолдстаун, США] slug=universitet-nyu-inglenda-2
- _both have jinaq_id (name)_
  - Университет Вестминстера [Лондон, Великобритания] slug=universitet-vestminstera
  - Университет Вестминстера [Солт-Лейк-Сити, США] slug=universitet-vestminstera-2
- _both have jinaq_id (name)_
  - Тихоокеанский государственный университет [Хабаровск, Россия] slug=tihookeanskiy-gosudarstvennyy-universitet
  - Тихоокеанский государственный университет [Владивосток, Россия] slug=tihookeanskiy-gosudarstvennyy-universitet-2
- _both have jinaq_id (name-no-paren)_
  - Университет Виктории [Мельбурн, Австралия] slug=universitet-viktorii
  - Университет Виктории [Виктория, Канада] slug=universitet-viktorii-2
- _both have jinaq_id (name-no-paren)_
  - Университет Нью-Ингленда [Армидейл, Австралия] slug=universitet-nyu-inglenda
  - Университет Нью-Ингленда [Арнолдстаун, США] slug=universitet-nyu-inglenda-2
- _both have jinaq_id (name-no-paren)_
  - Университет Вестминстера [Лондон, Великобритания] slug=universitet-vestminstera
  - Университет Вестминстера [Солт-Лейк-Сити, США] slug=universitet-vestminstera-2
- _both have jinaq_id (name-no-paren)_
  - Университет Святого Томаса [Фредериктон, Канада] slug=universitet-svyatogo-tomasa
  - Университет Святого Томаса (Миннесота) [Сент-Пол, США] slug=universitet-svyatogo-tomasa-minnesota
- _both have jinaq_id (name-no-paren)_
  - Тихоокеанский государственный университет [Хабаровск, Россия] slug=tihookeanskiy-gosudarstvennyy-universitet
  - Тихоокеанский государственный университет [Владивосток, Россия] slug=tihookeanskiy-gosudarstvennyy-universitet-2
- _both have jinaq_id (name-no-paren)_
  - Университет Майами [Коррал-Гейблс, США] slug=universitet-mayami
  - Университет Майами (Огайо) [Оксфорд, США] slug=universitet-mayami-ogayo
- _both have jinaq_id (name-no-paren)_
  - Seoul National University [Сеул, Южная Корея] slug=seoul-national-university
  - Seoul National University (SNU) [Сеул, Южная Корея] slug=seoul-national-university-snu

## C2 — English-name / Russian-name jinaq duplicates

rank signal (confirmed uniranks_world_rank_review entries): 1358

**48 auto-merges** (kept the Russian name, English name → `aliases`):

- **keep** Австралийский национальный университет [Канберра, Австралия] slug=australian-national-university
  drop EN name → alias: _Australian National University_  · signal: world_rank=143  · +5 programs, 0 collisions
- **keep** Университет Гриффит [Брисбен / Голд-Кост, Австралия] slug=griffith-university-aviation
  drop EN name → alias: _Griffith University_  · signal: world_rank=319  · +5 programs, 0 collisions
- **keep** Университет Квинсленда [Брисбен, Австралия] slug=universitet-kvinslenda
  drop EN name → alias: _The University of Queensland_  · signal: world_rank=99  · +3 programs, 0 collisions
- **keep** Университет Западной Австралии [Перт, Австралия] slug=universitet-zapadnoy-avstralii
  drop EN name → alias: _The University of Western Australia_  · signal: world_rank=204  · +3 programs, 0 collisions
- **keep** Университет Квинсленда [Брисбен, Австралия] slug=university-of-queensland
  drop EN name → alias: _University of Queensland_  · signal: world_rank=99  · +8 programs, 0 collisions
- **keep** Университет Западной Австралии [Перт, Австралия] slug=university-of-western-australia
  drop EN name → alias: _University of Western Australia_  · signal: world_rank=204  · +8 programs, 0 collisions
- **keep** Университет Кранфилда [Крэнфилд, Великобритания] slug=cranfield-university
  drop EN name → alias: _Cranfield University_  · signal: world_rank=535  · +4 programs, 0 collisions
- **keep** Лафборо университет [Лафборо, Великобритания] slug=loughborough-university
  drop EN name → alias: _Loughborough University_  · signal: world_rank=248  · +4 programs, 0 collisions
- **keep** Университет Центрального Ланкашира [Престон, Великобритания] slug=uclan-preston
  drop EN name → alias: _University of Central Lancashire (UCLan)_  · signal: world_rank=662  · +5 programs, 0 collisions
- **keep** Оксфордский университет [Оксфорд, Великобритания] slug=university-of-oxford
  drop EN name → alias: _University of Oxford_  · signal: world_rank=4  · +1 programs, 4 collisions
- **keep** Университет Рединга [Рединг, Великобритания] slug=university-of-reading
  drop EN name → alias: _University of Reading_  · signal: world_rank=167  · +4 programs, 0 collisions
- **keep** Суррейский университет [Гилфорд, Великобритания] slug=university-of-surrey-hospitality-tourism
  drop EN name → alias: _University of Surrey — School of Hospitality and Tourism Management_  · signal: world_rank=217  · +5 programs, 0 collisions
- **keep** Университет Уорика [Ковентри, Великобритания] slug=universitet-uorika
  drop EN name → alias: _University of Warwick_  · signal: world_rank=51  · +5 programs, 0 collisions
- **keep** Гейдельбергский университет [Гейдельберг, Германия] slug=geydelbergskiy-universitet
  drop EN name → alias: _Heidelberg University_  · signal: world_rank=3954  · +1 programs, 1 collisions
- **keep** Университет имени Иоганна Гутенберга в Майнце [Майнц, Германия] slug=jgu-mainz
  drop EN name → alias: _Johannes Gutenberg University Mainz (JGU)_  · signal: world_rank=6675  · +5 programs, 0 collisions
- **keep** Университет логистики Кюне [Гамбург, Германия] slug=kuehne-logistics-university
  drop EN name → alias: _Kühne Logistics University_  · signal: world_rank=13076  · +2 programs, 0 collisions
- **keep** Технический университет Мюнхена [Мюнхен, Германия] slug=tu-munich
  drop EN name → alias: _Technical University of Munich (TUM)_  · signal: world_rank=22  · +5 programs, 0 collisions
- **keep** Университет Хоэнхайм [Штутгарт, Германия] slug=university-of-hohenheim
  drop EN name → alias: _University of Hohenheim_  · signal: world_rank=7288  · +6 programs, 0 collisions
- **keep** Миланский политехнический университет [Милан, Италия] slug=politecnico-di-milano
  drop EN name → alias: _Politecnico di Milano_  · signal: world_rank=120  · +4 programs, 1 collisions
- **keep** Падуанский университет [Падуя, Италия] slug=university-of-padua
  drop EN name → alias: _University of Padua_  · signal: world_rank=216  · +5 programs, 0 collisions
- **keep** Альбертский университет [Эдмонтон, Канада] slug=university-of-alberta
  drop EN name → alias: _University of Alberta_  · signal: world_rank=68  · +6 programs, 0 collisions
- **keep** Британский университет Колумбии [Ванкувер, Канада] slug=britanskiy-universitet-kolumbii
  drop EN name → alias: _University of British Columbia_  · signal: world_rank=38  · +3 programs, 0 collisions
- **keep** Университет Гуэлфа [Гуэльф, Канада] slug=university-of-guelph
  drop EN name → alias: _University of Guelph_  · signal: world_rank=358  · +5 programs, 0 collisions
- **keep** Китайский сельскохозяйственный университет [Пекин, Китай] slug=china-agricultural-university
  drop EN name → alias: _China Agricultural University_  · signal: world_rank=497  · +4 programs, 0 collisions
- **keep** Пекинский университет [Пекин, Китай] slug=pekinskiy-universitet
  drop EN name → alias: _Peking University_  · signal: world_rank=69  · +3 programs, 0 collisions
- **keep** Ягеллонский университет [Краков, Польша] slug=jagiellonian-university
  drop EN name → alias: _Jagiellonian University_  · signal: world_rank=511  · +4 programs, 0 collisions
- **keep** Московский государственный технический университет имени Н. Э. Баумана [Москва, Россия] slug=moskovskiy-gosudarstvennyy-tehnicheskiy-universitet-imeni-n-e-baumana
  drop EN name → alias: _Bauman Moscow State Technical University_  · signal: world_rank=704  · +3 programs, 0 collisions
- **keep** Российский государственный университет нефти и газа имени И. М. Губкина (Национальный исследовательский университет) [Москва, Россия] slug=gubkin-university-moscow
  drop EN name → alias: _Gubkin Russian State University of Oil and Gas_  · signal: world_rank=1552  · +5 programs, 0 collisions
- **keep** Московский государственный университет имени М. В. Ломоносова [Москва, Россия] slug=moskovskiy-gosudarstvennyy-universitet-imeni-m-v-lomonosova
  drop EN name → alias: _Lomonosov Moscow State University_  · signal: world_rank=159  · +2 programs, 1 collisions
- **keep** Университет Карнеги — Меллон [Питтсбург, США] slug=carnegie-mellon-university
  drop EN name → alias: _Carnegie Mellon University (CMU)_  · signal: world_rank=40  · +5 programs, 0 collisions
- **keep** Школа горного дела Колорадо [Голден, США] slug=colorado-school-of-mines
  drop EN name → alias: _Colorado School of Mines_  · signal: world_rank=398  · +3 programs, 0 collisions
- **keep** Аэрокосмический университет Эмбри-Риддл [Дейтона-Бич, США] slug=embry-riddle-aeronautical-university
  drop EN name → alias: _Embry-Riddle Aeronautical University_  · signal: world_rank=955  · +5 programs, 0 collisions
- **keep** Технологический институт Джорджии [Атланта, США] slug=georgia-institute-of-technology
  drop EN name → alias: _Georgia Institute of Technology_  · signal: world_rank=21  · +4 programs, 0 collisions
- **keep** Гарвардский университет [Кембридж, Массачусетс, США] slug=harvard-university
  drop EN name → alias: _Harvard University_  · signal: world_rank=5  · +1 programs, 4 collisions
- **keep** Массачусетский технологический институт [Кембридж, США] slug=massachusetskiy-tehnologicheskiy-institut
  drop EN name → alias: _Massachusetts Institute of Technology_  · signal: world_rank=1  · +4 programs, 0 collisions
- **keep** Нью-Йоркский университет [Нью-Йорк, США] slug=nyu-yorkskiy-universitet
  drop EN name → alias: _New York University_  · signal: world_rank=18  · +6 programs, 0 collisions
- **keep** Университет Пердью [Уэст-Лафайет, США] slug=purdue-university
  drop EN name → alias: _Purdue University_  · signal: world_rank=113  · +4 programs, 0 collisions
- **keep** Стэнфордский университет [Стэнфорд, США] slug=stanford-university
  drop EN name → alias: _Stanford University_  · signal: world_rank=3  · +1 programs, 3 collisions
- **keep** Калифорнийский университет в Беркли [Беркли, США] slug=kaliforniyskiy-universitet-v-berkli
  drop EN name → alias: _University of California, Berkeley_  · signal: world_rank=6  · +5 programs, 2 collisions
- **keep** Чикагский университет [Чикаго, США] slug=university-of-chicago
  drop EN name → alias: _University of Chicago_  · signal: world_rank=17  · +6 programs, 0 collisions
- **keep** Национальный университет Сингапура [Сингапур, Сингапур] slug=national-university-of-singapore
  drop EN name → alias: _National University of Singapore_  · signal: world_rank=12  · +5 programs, 0 collisions
- **keep** Сингапурский университет менеджмента [Сингапур, Сингапур] slug=singapurskiy-universitet-menedzhmenta
  drop EN name → alias: _Singapore Management University_  · signal: world_rank=364  · +3 programs, 0 collisions
- **keep** Сингапурский университет технологий и дизайна [Сингапур, Сингапур] slug=singapore-university-of-technology-and-design
  drop EN name → alias: _Singapore University of Technology and Design_  · signal: world_rank=664  · +4 programs, 0 collisions
- **keep** Корейский университет [Сеул, Южная Корея] slug=koreyskiy-universitet
  drop EN name → alias: _Korea University_  · signal: world_rank=178  · +3 programs, 0 collisions
- **keep** Пусанский национальный университет [Пусан, Южная Корея] slug=pusanskiy-natsionalnyy-universitet
  drop EN name → alias: _Pusan National University_  · signal: world_rank=239  · +3 programs, 0 collisions
- **keep** Сеульский национальный университет [Сеул, Южная Корея] slug=seoul-national-university
  drop EN name → alias: _Seoul National University_  · signal: world_rank=75  · +5 programs, 0 collisions
- **keep** Университет Ёнсе [Сеул, Южная Корея] slug=universitet-ense
  drop EN name → alias: _Yonsei University_  · signal: world_rank=226  · +3 programs, 0 collisions
- **keep** Тохоку университет [Сэндай, Япония] slug=tohoku-universitet
  drop EN name → alias: _Tohoku University_  · signal: world_rank=98  · +3 programs, 0 collisions

### C2 — need manual review: 3

- _en/ru, one side is a faculty/school (rank 161)_
  - University of Birmingham — Birmingham Centre for Railway Research and Education [Бирмингем, Великобритания] slug=university-of-birmingham-bcrre
  - Бирмингемский университет [Бирмингем, Великобритания] slug=birmingemskiy-universitet
- _en/ru, one side is a faculty/school (rank 511)_
  - Jagiellonian University [Краков, Польша] slug=jagiellonian-university
  - Медицинский колледж Ягеллонского университета [Краков, Польша] slug=meditsinskiy-kolledzh-yagellonskogo-universiteta
- _en/ru, one side is a faculty/school (rank 13)_
  - Cornell University — ILR School (School of Industrial and Labor Relations) [Итака, США] slug=cornell-ilr-school
  - Корнеллский университет [Итака, США] slug=kornellskiy-universitet

## C3 — human-confirmed EN/RU pairs (SNAP-7)

confirmed in en_ru_university_merge.json: 68   applied: **58**

- keep _Назарбаев Университет_  ← drop _Nazarbayev University_  (+11 programs, 5 collisions)
- keep _Университет Аделаиды_  ← drop _The University of Adelaide_  (+3 programs, 0 collisions)
- keep _University of Edinburgh_  ← drop _The University of Edinburgh_  (+3 programs, 0 collisions)
- keep _University of Melbourne_  ← drop _The University of Melbourne_  (+8 programs, 0 collisions)
- keep _Университет Торонто Метрополитен_  ← drop _Toronto Metropolitan University_  (+4 programs, 0 collisions)
- keep _Университет Цинхуа_  ← drop _Tsinghua University_  (+5 programs, 0 collisions)
- keep _Yessenov University (Каспийский государственный университет технологий и инжиниринга им. Ш. Есенова)_  ← drop _Каспийский университет технологий и инжиниринга имени Ш. Есенова_  (+8 programs, 0 collisions)
- keep _Актюбинский региональный университет имени К.Жубанова_  ← drop _Актюбинский региональный университет имени К. Жубанова_  (+9 programs, 0 collisions)
- keep _Аркалыкский педагогический университет имени Ыбырай Алтынсарин_  ← drop _Аркалыкский педагогический институт имени Ыбырая Алтынсарина_  (+4 programs, 6 collisions)
- keep _Атырауский университет нефти и газа имени Сафи Утебаева_  ← drop _Атырауский университет нефти и газа имени С. Утебаева_  (+9 programs, 0 collisions)
- keep _Восточно-Казахстанский технический университет_  ← drop _Восточно-Казахстанский технический университет имени Д. Серикбаева_  (+10 programs, 0 collisions)
- keep _Восточно-Казахстанский университет имени Сарсена Аманжолова_  ← drop _Восточно-Казахстанский государственный университет имени Сарсена Аманжолова_  (+6 programs, 4 collisions)
- keep _Евразийский национальный университет им. Л.Н. Гумилёва_  ← drop _Евразийский национальный университет имени Л.Н. Гумилева_  (+8 programs, 0 collisions)
- keep _Египетский университет исламской культуры «Нур-Мубарак»_  ← drop _Египетский университет исламской культуры «Нур-Мубарак» в Казахстане_  (+1 programs, 4 collisions)
- keep _Западно-Казахстанский медицинский университет имени М.Оспанова_  ← drop _Западно-Казахстанский медицинский университет имени Марата Оспанова_  (+1 programs, 4 collisions)
- keep _Казахская национальная академия искусств им. Т. Жургенова (КазНАИ)_  ← drop _Казахская национальная академия искусств имени Т. Жургенова_  (+7 programs, 0 collisions)
- keep _Казахская национальная консерватория им. Курмангазы_  ← drop _Казахская национальная консерватория имени Курмангазы_  (+5 programs, 3 collisions)
- keep _Казахский агротехнический исследовательский университет им. С. Сейфуллина_  ← drop _Казахский агротехнический университет имени Сакена Сейфуллина_  (+7 programs, 0 collisions)
- keep _Казахский государственный женский педагогический университет (КГЖПУ)_  ← drop _Казахский национальный женский педагогический университет_  (+6 programs, 0 collisions)
- keep _Казахский национальный медицинский университет им. С.Д. Асфендиярова (КазНМУ)_  ← drop _Казахский национальный медицинский университет имени С.Д. Асфендиярова_  (+4 programs, 6 collisions)
- keep _Казахский национальный педагогический университет им. Абая (КазНПУ)_  ← drop _Казахский национальный педагогический университет имени Абая_  (+7 programs, 0 collisions)
- keep _Казахский университет международных отношений и мировых языков им. Абылай хана_  ← drop _Казахский университет международных отношений и мировых языков имени Абылай хана_  (+5 programs, 5 collisions)
- keep _Казахский университет технологии и бизнеса им. К. Кулажанова_  ← drop _Казахский университет технологии и бизнеса имени К. Кулажанова_  (+6 programs, 0 collisions)
- keep _Карагандинский университет имени академика Е.А. Букетова_  ← drop _Карагандинский государственный университет имени академика Е. А. Букетова_  (+6 programs, 0 collisions)
- keep _Костанайский социально-технический университет имени академика Зулхарнай Алдамжар_  ← drop _Костанайский социально-технический университет имени академика Зулкарнай Алдамжара_  (+2 programs, 3 collisions)
- keep _Рудненский индустриальный институт_  ← drop _Рудненский индустриальный университет_  (+2 programs, 0 collisions)
- keep _Шанхайский университет международных исследований_  ← drop _Шанхайский международный университет исследований_  (+0 programs, 3 collisions)
- keep _Южно-Казахстанский университет имени М. Ауэзова_  ← drop _Южно-Казахстанский государственный университет имени М. Ауэзова_  (+6 programs, 0 collisions)
- keep _Университет имени Алихана Бокейхана_  ← drop _Alikhan Bokeikhan University_  (+6 programs, 0 collisions)
- keep _Кызылординский государственный университет имени Коркыт Ата_  ← drop _Korkyt Ata Kyzylorda University_  (+6 programs, 0 collisions)
- keep _Кызылординский Университет «Болашак»_  ← drop _Kyzylorda Bolashak University_  (+6 programs, 0 collisions)
- keep _Медицинский университет Астана_  ← drop _Astana Medical University_  (+9 programs, 0 collisions)
- keep _Есильский университет_  ← drop _Esil University_  (+2 programs, 8 collisions)
- keep _Международный казахско-турецкий университет имени Ходжи Ахмеда Ясави_  ← drop _Khoja Ahmed Yasawi International Kazakh-Turkish University_  (+0 programs, 0 collisions)
- keep _Манчестерский университет_  ← drop _The University of Manchester — Alliance Manchester Business School_  (+4 programs, 0 collisions)
- keep _Университет Иллинойса в Урбана-Шампейн_  ← drop _University of Illinois Urbana-Champaign — Gies College of Business_  (+5 programs, 0 collisions)
- keep _Национальный университет Сингапура_  ← drop _National University of Singapore — NUS Business School_  (+20 programs, 0 collisions)
- keep _Казахский национальный университет им. аль-Фараби (КазНУ)_  ← drop _КазНУ им. аль-Фараби_  (+7 programs, 2 collisions)
- keep _Университет КИМЭП_  ← drop _Казахстанско-Американский университет КИМЭП_  (+3 programs, 7 collisions)
- keep _Алматинский институт менеджмента (АИМ, AlmaU)_  ← drop _Алматы Менеджмент Университет_  (+6 programs, 3 collisions)
- keep _Атырауский университет имени Халела Досмухамедова_  ← drop _Атырауский университет имени Х. Досмухамедова_  (+9 programs, 1 collisions)
- keep _Де Монтфорт Юниверсити Казахстан (DMU Kazakhstan)_  ← drop _Де Монтфорт Университет Казахстан_  (+10 programs, 0 collisions)
- keep _Таразский университет имени М.Х. Дулати_  ← drop _Таразский государственный педагогический университет имени М. Х. Дулати_  (+5 programs, 2 collisions)
- keep _Международный Таразский университет имени Шерхана Муртазы_  ← drop _Таразский инновационный университет имени Шерхана Муртазы_  (+4 programs, 2 collisions)
- keep _Университет имени Жубанова Ахметулы Ташенева_  ← drop _Университет имени Жумабека Ахметулы Ташенева_  (+5 programs, 2 collisions)
- keep _Университет международного бизнеса (UIB)_  ← drop _Университет международного бизнеса имени Кенжегали Сагадиева_  (+6 programs, 0 collisions)
- keep _Университет имени Шакарима города Семей_  ← drop _Шакаримский университет_  (+4 programs, 0 collisions)
- keep _Костанайский региональный университет_  ← drop _Костанайский региональный университет имени Ахмета Байтурсынова_  (+6 programs, 0 collisions)
- keep _Академия «Bolashaq»_  ← drop _Карагандинская академия «Bolashaq»_  (+3 programs, 3 collisions)
- keep _Карагандинский государственный технический университет имени Абылкаса Сагинова_  ← drop _Карагандинский технический университет (КарТУ)_  (+9 programs, 1 collisions)
- keep _Медицинский университет Караганды_  ← drop _Карагандинский государственный медицинский университет_  (+6 programs, 0 collisions)
- keep _Казахский медицинский университет «Семей»_  ← drop _Некоммерческое акционерное общество «Медицинский университет Семей»_  (+3 programs, 4 collisions)
- keep _ALT UNIVERSITY им. Мухаметжана Тынышпаева_  ← drop _Казахский университет транспорта и коммуникаций имени М. Тынышпаева_  (+10 programs, 0 collisions)
- keep _Университет имени М. С. Нарикбаева_  ← drop _Maqsut Narikbayev University_  (+1 programs, 7 collisions)
- keep _Торайгыров Университет (ToU)_  ← drop _Павлодарский государственный университет имени С. Торайгырова_  (+5 programs, 0 collisions)
- keep _Astana IT University_  ← drop _Астана IT Университет_  (+5 programs, 4 collisions)
- keep _Академия гражданской авиации (АГА)_  ← drop _Казахская академия гражданской авиации_  (+5 programs, 5 collisions)
- keep _Сеульский национальный университет_  ← drop _Seoul National University (SNU)_  (+6 programs, 0 collisions)

## Totals

| | before | after pass 1 | after pass 3 |
|---|---|---|---|
| universities | 2523 | 2505 | 2399 |
| programs | 12573 | — | 12434 |
| programs with profession tag | — | — | 9962 (80%) |
