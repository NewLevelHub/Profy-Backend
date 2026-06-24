"""
Seed script: populate universities and programs tables.
Run inside Docker: docker-compose exec api python scripts/seed_universities.py
Idempotent: upserts by university name; upserts programs by (university_id, name).
Coverage: KZ, USA, UK, Europe, Canada, Asia — 20 universities, 40+ programs.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.program import Program
from app.models.university import University

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

UNIVERSITIES: list[dict] = [
    # --- Kazakhstan ---
    {
        "name": "Nazarbayev University",
        "country": "Kazakhstan",
        "city": "Astana",
        "website": "https://nu.edu.kz",
        "ranking": 301,
        "description": (
            "Leading research university in Kazakhstan, offering English-language programs "
            "in partnership with top global universities."
        ),
    },
    {
        "name": "KIMEP University",
        "country": "Kazakhstan",
        "city": "Almaty",
        "website": "https://kimep.kz",
        "ranking": None,
        "description": (
            "Kazakhstan's premier business and social sciences university, "
            "fully accredited by AACSB and AMBA."
        ),
    },
    {
        "name": "Al-Farabi Kazakh National University",
        "country": "Kazakhstan",
        "city": "Almaty",
        "website": "https://kaznu.kz",
        "ranking": 181,
        "description": (
            "The largest classical university in Kazakhstan, offering a broad range "
            "of programs in natural sciences, engineering, and humanities."
        ),
    },
    # --- USA ---
    {
        "name": "Massachusetts Institute of Technology",
        "country": "USA",
        "city": "Cambridge",
        "website": "https://mit.edu",
        "ranking": 1,
        "description": (
            "World-renowned research university consistently ranked #1 globally, "
            "known for engineering, computing, and science."
        ),
    },
    {
        "name": "Stanford University",
        "country": "USA",
        "city": "Stanford",
        "website": "https://stanford.edu",
        "ranking": 3,
        "description": (
            "Elite private research university in Silicon Valley, a hub for "
            "entrepreneurship, technology, and innovation."
        ),
    },
    {
        "name": "University of California, Berkeley",
        "country": "USA",
        "city": "Berkeley",
        "website": "https://berkeley.edu",
        "ranking": 10,
        "description": (
            "Top public research university in the USA, with outstanding programs "
            "in computer science, engineering, and data science."
        ),
    },
    {
        "name": "New York University",
        "country": "USA",
        "city": "New York",
        "website": "https://nyu.edu",
        "ranking": 55,
        "description": (
            "Global private university in the heart of New York City, "
            "offering world-class programs in technology, business, and arts."
        ),
    },
    # --- UK ---
    {
        "name": "University College London",
        "country": "UK",
        "city": "London",
        "website": "https://ucl.ac.uk",
        "ranking": 9,
        "description": (
            "London's leading multidisciplinary university, ranked among the top 10 "
            "globally, with strengths in science, engineering, and social sciences."
        ),
    },
    {
        "name": "University of Edinburgh",
        "country": "UK",
        "city": "Edinburgh",
        "website": "https://ed.ac.uk",
        "ranking": 22,
        "description": (
            "One of the world's top universities, founded in 1583, with particularly "
            "strong programs in informatics and AI."
        ),
    },
    {
        "name": "University of Manchester",
        "country": "UK",
        "city": "Manchester",
        "website": "https://manchester.ac.uk",
        "ranking": 32,
        "description": (
            "Russell Group research university with a strong track record in "
            "computer science, data science, and engineering."
        ),
    },
    # --- Europe ---
    {
        "name": "Delft University of Technology",
        "country": "Netherlands",
        "city": "Delft",
        "website": "https://tudelft.nl",
        "ranking": 57,
        "description": (
            "Top technical university in the Netherlands and Europe, renowned for "
            "engineering, design, and applied sciences."
        ),
    },
    {
        "name": "Ludwig Maximilian University of Munich",
        "country": "Germany",
        "city": "Munich",
        "website": "https://lmu.de",
        "ranking": 38,
        "description": (
            "One of Germany's oldest and most prestigious universities, "
            "offering tuition-free programs in computer science and informatics."
        ),
    },
    {
        "name": "ETH Zurich",
        "country": "Switzerland",
        "city": "Zurich",
        "website": "https://ethz.ch",
        "ranking": 7,
        "description": (
            "Switzerland's leading science and technology university, consistently "
            "ranked in the global top 10 for engineering and computing."
        ),
    },
    {
        "name": "EPFL",
        "country": "Switzerland",
        "city": "Lausanne",
        "website": "https://epfl.ch",
        "ranking": 19,
        "description": (
            "École Polytechnique Fédérale de Lausanne — one of Europe's most innovative "
            "technical universities, known for computer science and data science."
        ),
    },
    # --- Canada ---
    {
        "name": "University of Toronto",
        "country": "Canada",
        "city": "Toronto",
        "website": "https://utoronto.ca",
        "ranking": 21,
        "description": (
            "Canada's top-ranked university with a world-class computer science "
            "department that pioneered deep learning research."
        ),
    },
    {
        "name": "University of British Columbia",
        "country": "Canada",
        "city": "Vancouver",
        "website": "https://ubc.ca",
        "ranking": 34,
        "description": (
            "Leading Canadian research university with strong programs in "
            "computer science, data science, and engineering."
        ),
    },
    # --- Asia ---
    {
        "name": "National University of Singapore",
        "country": "Singapore",
        "city": "Singapore",
        "website": "https://nus.edu.sg",
        "ranking": 8,
        "description": (
            "Asia's top university, consistently ranked among the global top 10, "
            "with world-class computing and business programs."
        ),
    },
    {
        "name": "KAIST",
        "country": "South Korea",
        "city": "Daejeon",
        "website": "https://kaist.ac.kr",
        "ranking": 42,
        "description": (
            "Korea Advanced Institute of Science and Technology — leading STEM "
            "university in Asia, offering fully English-taught graduate programs."
        ),
    },
    {
        "name": "Imperial College London",
        "country": "UK",
        "city": "London",
        "website": "https://imperial.ac.uk",
        "ranking": 6,
        "description": (
            "World-leading science, engineering, medicine, and business university "
            "in central London, ranked top 10 globally."
        ),
    },
    {
        "name": "Seoul National University",
        "country": "South Korea",
        "city": "Seoul",
        "website": "https://snu.ac.kr",
        "ranking": 31,
        "description": (
            "South Korea's most prestigious university, offering strong programs "
            "in engineering, computing, and natural sciences."
        ),
    },
]

# Programs keyed by university name → list of program dicts
PROGRAMS_BY_UNIVERSITY: dict[str, list[dict]] = {
    "Nazarbayev University": [
        {
            "name": "Computer Science (BSc)",
            "direction_slug": "it-development",
            "language": "English",
            "cost_per_year": 3000,
            "description": (
                "Four-year undergraduate program covering algorithms, systems programming, "
                "software engineering, and AI, delivered entirely in English."
            ),
            "who_its_for": (
                "High-achieving school graduates passionate about software development "
                "and research, aiming for careers in tech or graduate study abroad."
            ),
            "career_options": [
                "Software Engineer", "Backend Developer", "Research Engineer",
                "System Architect", "Tech Lead",
            ],
            "requirements": {
                "min_gpa": 3.5,
                "exams": ["SAT", "IELTS", "UNT"],
                "min_ielts": 6.5,
                "min_sat": 1200,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Olympiads in math/informatics", "Programming competitions"],
            },
            "deadlines": {
                "application_open": "2025-11-01",
                "application_close": "2026-02-28",
                "exam_deadline": "2026-02-01",
                "decision_date": "2026-04-15",
            },
            "grants": [
                {
                    "name": "Presidential Scholarship",
                    "amount": "Full tuition + stipend",
                    "conditions": "Top UNT score, competitive selection",
                },
                {
                    "name": "NU Merit Award",
                    "amount": "50% tuition",
                    "conditions": "SAT 1350+ or equivalent",
                },
            ],
        },
        {
            "name": "Data Science (BSc)",
            "direction_slug": "data-science",
            "language": "English",
            "cost_per_year": 3000,
            "description": (
                "Interdisciplinary program combining statistics, machine learning, "
                "and data engineering to prepare graduates for the data-driven economy."
            ),
            "who_its_for": (
                "Students strong in mathematics and statistics who want to build "
                "predictive models and extract insights from large datasets."
            ),
            "career_options": [
                "Data Scientist", "ML Engineer", "Data Analyst",
                "BI Developer", "Research Analyst",
            ],
            "requirements": {
                "min_gpa": 3.5,
                "exams": ["SAT", "IELTS", "UNT"],
                "min_ielts": 6.5,
                "min_sat": 1200,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Math olympiads", "Statistics or programming projects"],
            },
            "deadlines": {
                "application_open": "2025-11-01",
                "application_close": "2026-02-28",
                "exam_deadline": "2026-02-01",
                "decision_date": "2026-04-15",
            },
            "grants": [
                {
                    "name": "Presidential Scholarship",
                    "amount": "Full tuition + stipend",
                    "conditions": "Top UNT score, competitive selection",
                },
            ],
        },
    ],
    "KIMEP University": [
        {
            "name": "Business Administration (BBA)",
            "direction_slug": "business-entrepreneurship",
            "language": "English",
            "cost_per_year": 4500,
            "description": (
                "AACSB-accredited four-year BBA covering management, marketing, finance, "
                "and entrepreneurship with a strong practical focus."
            ),
            "who_its_for": (
                "Ambitious students who want to launch their own business or build a career "
                "in management, consulting, or corporate leadership."
            ),
            "career_options": [
                "Business Analyst", "Product Manager", "Entrepreneur",
                "Management Consultant", "Operations Manager",
            ],
            "requirements": {
                "min_gpa": 3.0,
                "exams": ["IELTS", "TOEFL", "UNT"],
                "min_ielts": 6.0,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": True,
                "extracurriculars": ["Student government", "Business case competitions"],
            },
            "deadlines": {
                "application_open": "2025-10-01",
                "application_close": "2026-03-31",
                "exam_deadline": "2026-03-01",
                "decision_date": "2026-04-30",
            },
            "grants": [
                {
                    "name": "KIMEP Excellence Scholarship",
                    "amount": "Up to 100% tuition",
                    "conditions": "High UNT score + interview",
                },
            ],
        },
        {
            "name": "Finance (BSc)",
            "direction_slug": "finance-economics",
            "language": "English",
            "cost_per_year": 4500,
            "description": (
                "Rigorous finance program covering corporate finance, investment analysis, "
                "financial modelling, and capital markets."
            ),
            "who_its_for": (
                "Students passionate about financial markets, investment banking, "
                "or building a career in fintech and corporate finance."
            ),
            "career_options": [
                "Financial Analyst", "Investment Banker", "Risk Manager",
                "Auditor", "Fintech Specialist",
            ],
            "requirements": {
                "min_gpa": 3.2,
                "exams": ["IELTS", "TOEFL", "UNT"],
                "min_ielts": 6.0,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Economics olympiads", "Finance clubs"],
            },
            "deadlines": {
                "application_open": "2025-10-01",
                "application_close": "2026-03-31",
                "exam_deadline": "2026-03-01",
                "decision_date": "2026-04-30",
            },
            "grants": [
                {
                    "name": "KIMEP Merit Scholarship",
                    "amount": "25–75% tuition",
                    "conditions": "GPA 3.5+ and IELTS 7.0+",
                },
            ],
        },
    ],
    "Al-Farabi Kazakh National University": [
        {
            "name": "Software Engineering (BSc)",
            "direction_slug": "it-development",
            "language": "Kazakh / Russian",
            "cost_per_year": 900,
            "description": (
                "Five-year engineering degree covering software design, algorithms, "
                "databases, and systems programming. State grant places available."
            ),
            "who_its_for": (
                "Graduates seeking an affordable, high-quality engineering degree "
                "in Kazakhstan's largest classical university."
            ),
            "career_options": [
                "Software Developer", "Systems Analyst", "Database Administrator",
                "QA Engineer", "IT Consultant",
            ],
            "requirements": {
                "min_gpa": 3.0,
                "exams": ["UNT"],
                "min_ielts": None,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": False,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Programming competitions", "Science fairs"],
            },
            "deadlines": {
                "application_open": "2026-06-01",
                "application_close": "2026-07-25",
                "exam_deadline": "2026-06-20",
                "decision_date": "2026-08-10",
            },
            "grants": [
                {
                    "name": "State Educational Grant",
                    "amount": "Full tuition",
                    "conditions": "Top UNT score, competitive by major",
                },
            ],
        },
        {
            "name": "Biology (BSc)",
            "direction_slug": "medicine-biology",
            "language": "Kazakh / Russian",
            "cost_per_year": 800,
            "description": (
                "Classical biology program covering cell biology, genetics, ecology, "
                "and biochemistry, with laboratory practice."
            ),
            "who_its_for": (
                "Students passionate about living organisms, ecology, "
                "or pursuing a career in biotech, medicine, or research."
            ),
            "career_options": [
                "Biologist", "Biochemist", "Lab Researcher",
                "Ecologist", "Medical Scientist",
            ],
            "requirements": {
                "min_gpa": 3.0,
                "exams": ["UNT"],
                "min_ielts": None,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": False,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Biology olympiads", "Environmental volunteering"],
            },
            "deadlines": {
                "application_open": "2026-06-01",
                "application_close": "2026-07-25",
                "exam_deadline": "2026-06-20",
                "decision_date": "2026-08-10",
            },
            "grants": [
                {
                    "name": "State Educational Grant",
                    "amount": "Full tuition",
                    "conditions": "Top UNT score in chemistry/biology",
                },
            ],
        },
    ],
    "Massachusetts Institute of Technology": [
        {
            "name": "Computer Science and Engineering (BSc)",
            "direction_slug": "it-development",
            "language": "English",
            "cost_per_year": 59750,
            "description": (
                "MIT's flagship undergraduate program in Course 6, covering algorithms, "
                "systems, AI, and software engineering with world-leading faculty."
            ),
            "who_its_for": (
                "Exceptionally talented students with demonstrated passion for "
                "engineering and problem solving who want to shape the future of technology."
            ),
            "career_options": [
                "Software Engineer", "Research Scientist", "Entrepreneur",
                "Systems Architect", "AI/ML Engineer",
            ],
            "requirements": {
                "min_gpa": 3.9,
                "exams": ["SAT", "ACT", "AP"],
                "min_ielts": 7.0,
                "min_sat": 1570,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": [
                    "USACO / international programming olympiad",
                    "Research projects or publications",
                    "Science Olympiad / math competitions",
                ],
            },
            "deadlines": {
                "application_open": "2025-08-01",
                "application_close": "2026-01-01",
                "exam_deadline": "2025-12-01",
                "decision_date": "2026-03-14",
            },
            "grants": [
                {
                    "name": "MIT Need-Based Financial Aid",
                    "amount": "Up to full cost of attendance",
                    "conditions": "Based on family income; families earning <$140k pay nothing",
                },
            ],
        },
        {
            "name": "Electrical Engineering and Computer Science (MEng)",
            "direction_slug": "it-development",
            "language": "English",
            "cost_per_year": 62000,
            "description": (
                "MIT's combined BS/MEng program allowing undergrads to earn a master's "
                "degree in 5 years, covering advanced computing and electrical systems."
            ),
            "who_its_for": (
                "MIT undergraduates seeking advanced technical depth in hardware, "
                "software, and systems before entering industry or doctoral programs."
            ),
            "career_options": [
                "Hardware Engineer", "Chip Designer", "Systems Engineer",
                "Research Scientist", "CTO",
            ],
            "requirements": {
                "min_gpa": 4.0,
                "exams": ["GRE"],
                "min_ielts": 7.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["MIT undergraduate research (UROP)", "Published work"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2026-02-01",
                "exam_deadline": "2026-01-15",
                "decision_date": "2026-04-01",
            },
            "grants": [
                {
                    "name": "MIT Teaching / Research Assistantship",
                    "amount": "Tuition + stipend ~$40k/year",
                    "conditions": "Competitive; awarded by department",
                },
            ],
        },
    ],
    "Stanford University": [
        {
            "name": "Computer Science (BSc)",
            "direction_slug": "it-development",
            "language": "English",
            "cost_per_year": 62484,
            "description": (
                "Stanford's CS program offers unparalleled access to Silicon Valley "
                "industry and cutting-edge research in systems, AI, and HCI."
            ),
            "who_its_for": (
                "Top students with strong academics and entrepreneurial drive who want "
                "to build products or conduct research at the forefront of computing."
            ),
            "career_options": [
                "Software Engineer", "Product Manager", "Founder",
                "AI Researcher", "Tech Lead",
            ],
            "requirements": {
                "min_gpa": 3.9,
                "exams": ["SAT", "ACT"],
                "min_ielts": 7.0,
                "min_sat": 1550,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": [
                    "Competitive programming (ICPC, IOI)",
                    "Side projects or startups",
                    "Research internships",
                ],
            },
            "deadlines": {
                "application_open": "2025-08-01",
                "application_close": "2026-01-02",
                "exam_deadline": "2025-12-06",
                "decision_date": "2026-03-30",
            },
            "grants": [
                {
                    "name": "Stanford Need-Based Aid",
                    "amount": "Up to full cost of attendance",
                    "conditions": "Families earning <$150k pay nothing",
                },
            ],
        },
        {
            "name": "Artificial Intelligence (MSc)",
            "direction_slug": "artificial-intelligence",
            "language": "English",
            "cost_per_year": 63450,
            "description": (
                "Stanford's graduate AI program covers machine learning, deep learning, "
                "NLP, computer vision, and robotics with access to world-class labs."
            ),
            "who_its_for": (
                "CS graduates who want to deepen expertise in AI research or "
                "enter the AI industry at companies like Google, OpenAI, or top startups."
            ),
            "career_options": [
                "ML Engineer", "AI Researcher", "NLP Engineer",
                "Computer Vision Engineer", "AI Product Manager",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["GRE", "TOEFL", "IELTS"],
                "min_ielts": 7.0,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": [
                    "ML research publications or preprints",
                    "Kaggle top rankings",
                    "Open-source AI contributions",
                ],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2025-12-04",
                "exam_deadline": "2025-11-30",
                "decision_date": "2026-03-15",
            },
            "grants": [
                {
                    "name": "Stanford Fellowship",
                    "amount": "Full tuition + $45k stipend",
                    "conditions": "Competitive; top applicants receive funding",
                },
            ],
        },
    ],
    "University of California, Berkeley": [
        {
            "name": "Computer Science (BSc)",
            "direction_slug": "it-development",
            "language": "English",
            "cost_per_year": 44066,
            "description": (
                "UC Berkeley's EECS/CS program is among the world's best, providing "
                "rigorous theory and strong ties to Bay Area industry."
            ),
            "who_its_for": (
                "Driven students seeking a world-class CS education at a public "
                "research university with close connections to Silicon Valley companies."
            ),
            "career_options": [
                "Software Engineer", "Full-Stack Developer", "Systems Engineer",
                "Product Manager", "Research Engineer",
            ],
            "requirements": {
                "min_gpa": 3.8,
                "exams": ["SAT", "ACT"],
                "min_ielts": 6.5,
                "min_sat": 1500,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": [
                    "USACO or competitive programming",
                    "Open-source contributions",
                    "Hackathon wins",
                ],
            },
            "deadlines": {
                "application_open": "2025-08-01",
                "application_close": "2025-11-30",
                "exam_deadline": "2025-11-30",
                "decision_date": "2026-03-31",
            },
            "grants": [
                {
                    "name": "Cal Grant",
                    "amount": "Up to $15,000/year",
                    "conditions": "California residents based on financial need",
                },
                {
                    "name": "Berkeley Global Award",
                    "amount": "$10,000/year",
                    "conditions": "International applicants with outstanding academics",
                },
            ],
        },
        {
            "name": "Data Science (BSc)",
            "direction_slug": "data-science",
            "language": "English",
            "cost_per_year": 44066,
            "description": (
                "Berkeley's interdisciplinary Data Science program blends statistics, "
                "computing, and domain knowledge to prepare data scientists."
            ),
            "who_its_for": (
                "Students who love working with data, statistics, and programming "
                "and want to solve real-world problems across industries."
            ),
            "career_options": [
                "Data Scientist", "Data Analyst", "ML Engineer",
                "Research Analyst", "Data Engineer",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["SAT", "ACT"],
                "min_ielts": 6.5,
                "min_sat": 1480,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Kaggle competitions", "Statistics projects", "Data hackathons"],
            },
            "deadlines": {
                "application_open": "2025-08-01",
                "application_close": "2025-11-30",
                "exam_deadline": "2025-11-30",
                "decision_date": "2026-03-31",
            },
            "grants": [
                {
                    "name": "Cal Grant",
                    "amount": "Up to $15,000/year",
                    "conditions": "California residents based on financial need",
                },
            ],
        },
    ],
    "New York University": [
        {
            "name": "Computer Science (BSc)",
            "direction_slug": "it-development",
            "language": "English",
            "cost_per_year": 58168,
            "description": (
                "NYU Tandon's CS program in the heart of New York City, "
                "offering strong industry connections and research opportunities."
            ),
            "who_its_for": (
                "Students who want to study CS in a global city with access to "
                "NYC's thriving tech scene, startups, and finance industry."
            ),
            "career_options": [
                "Software Developer", "Full-Stack Engineer", "DevOps Engineer",
                "Data Engineer", "Cybersecurity Analyst",
            ],
            "requirements": {
                "min_gpa": 3.5,
                "exams": ["SAT", "ACT", "IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": 1400,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Hackathons", "Coding clubs", "Research projects"],
            },
            "deadlines": {
                "application_open": "2025-08-01",
                "application_close": "2026-01-01",
                "exam_deadline": "2025-12-15",
                "decision_date": "2026-03-20",
            },
            "grants": [
                {
                    "name": "NYU Scholarship",
                    "amount": "Up to $25,000/year",
                    "conditions": "Merit-based, competitive",
                },
            ],
        },
        {
            "name": "Business (BBA — Stern School)",
            "direction_slug": "business-entrepreneurship",
            "language": "English",
            "cost_per_year": 58168,
            "description": (
                "NYU Stern's undergraduate business program, one of the most prestigious "
                "in the world, located in NYC's Financial District."
            ),
            "who_its_for": (
                "Aspiring business leaders, entrepreneurs, and finance professionals "
                "who want access to Wall Street and global business networks."
            ),
            "career_options": [
                "Investment Banker", "Management Consultant", "Entrepreneur",
                "Product Manager", "Marketing Director",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["SAT", "ACT", "IELTS", "TOEFL"],
                "min_ielts": 7.0,
                "min_sat": 1500,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": [
                    "Business case competitions",
                    "Entrepreneurship clubs",
                    "Investment clubs",
                ],
            },
            "deadlines": {
                "application_open": "2025-08-01",
                "application_close": "2026-01-01",
                "exam_deadline": "2025-12-15",
                "decision_date": "2026-03-20",
            },
            "grants": [
                {
                    "name": "Stern Leadership Scholarship",
                    "amount": "$20,000/year",
                    "conditions": "Top applicants, merit and leadership",
                },
            ],
        },
    ],
    "University College London": [
        {
            "name": "Computer Science (BSc)",
            "direction_slug": "it-development",
            "language": "English",
            "cost_per_year": 35000,
            "description": (
                "UCL's Computer Science program in central London covers algorithms, "
                "software engineering, AI, and security with strong industry links."
            ),
            "who_its_for": (
                "International students who want a top London university experience "
                "combined with deep technical training and global career prospects."
            ),
            "career_options": [
                "Software Engineer", "AI Engineer", "Cybersecurity Analyst",
                "Backend Developer", "Research Scientist",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["A-Levels", "IB", "IELTS"],
                "min_ielts": 6.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Maths/CS competitions", "Personal projects"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2026-01-15",
                "exam_deadline": "2026-01-15",
                "decision_date": "2026-04-30",
            },
            "grants": [
                {
                    "name": "UCL Global Undergraduate Scholarship",
                    "amount": "£5,000/year",
                    "conditions": "International students with outstanding academics",
                },
            ],
        },
        {
            "name": "Neuroscience (BSc)",
            "direction_slug": "medicine-biology",
            "language": "English",
            "cost_per_year": 35000,
            "description": (
                "UCL is one of the world's top neuroscience destinations; this program "
                "covers brain function, cognitive science, and neural disorders."
            ),
            "who_its_for": (
                "Students fascinated by the brain and mind who want to pursue "
                "research, medicine, or careers in clinical neuroscience."
            ),
            "career_options": [
                "Neuroscientist", "Clinical Researcher", "Psychiatrist",
                "Cognitive Scientist", "Biotech Specialist",
            ],
            "requirements": {
                "min_gpa": 3.8,
                "exams": ["A-Levels", "IB", "IELTS"],
                "min_ielts": 7.0,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": True,
                "extracurriculars": ["Biology/chemistry olympiads", "Lab volunteering"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2026-01-15",
                "exam_deadline": "2026-01-15",
                "decision_date": "2026-04-30",
            },
            "grants": [
                {
                    "name": "UCL Global Undergraduate Scholarship",
                    "amount": "£5,000/year",
                    "conditions": "International students with outstanding academics",
                },
            ],
        },
    ],
    "University of Edinburgh": [
        {
            "name": "Informatics (BSc / BEng)",
            "direction_slug": "it-development",
            "language": "English",
            "cost_per_year": 26500,
            "description": (
                "Edinburgh's School of Informatics is Europe's largest informatics "
                "department, offering world-class programs in CS, AI, and cognitive science."
            ),
            "who_its_for": (
                "Students who want breadth across computing, AI, and cognitive science "
                "from one of the UK's most innovative universities."
            ),
            "career_options": [
                "Software Engineer", "AI Engineer", "Data Scientist",
                "UX Researcher", "Research Scientist",
            ],
            "requirements": {
                "min_gpa": 3.6,
                "exams": ["A-Levels", "IB", "IELTS"],
                "min_ielts": 6.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Maths/CS Olympiads", "Coding competitions"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2026-01-15",
                "exam_deadline": "2026-01-15",
                "decision_date": "2026-05-01",
            },
            "grants": [
                {
                    "name": "Edinburgh Global Research Scholarship",
                    "amount": "£10,000 (one-off)",
                    "conditions": "Outstanding academic record for international students",
                },
            ],
        },
        {
            "name": "Artificial Intelligence (MSc)",
            "direction_slug": "artificial-intelligence",
            "language": "English",
            "cost_per_year": 28500,
            "description": (
                "Edinburgh's 1-year MSc in AI covers machine learning, NLP, "
                "computer vision, and AI planning, offered by a world-leading AI school."
            ),
            "who_its_for": (
                "CS or engineering graduates who want to specialise in AI "
                "and enter the rapidly growing AI industry or pursue a PhD."
            ),
            "career_options": [
                "ML Engineer", "AI Researcher", "NLP Scientist",
                "Computer Vision Engineer", "AI Consultant",
            ],
            "requirements": {
                "min_gpa": 3.5,
                "exams": ["IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["ML projects on GitHub", "Kaggle competitions", "Research papers"],
            },
            "deadlines": {
                "application_open": "2025-10-01",
                "application_close": "2026-03-31",
                "exam_deadline": "2026-03-01",
                "decision_date": "2026-05-15",
            },
            "grants": [
                {
                    "name": "School of Informatics Scholarship",
                    "amount": "£5,000",
                    "conditions": "Academic merit, limited places",
                },
            ],
        },
    ],
    "University of Manchester": [
        {
            "name": "Computer Science (BSc)",
            "direction_slug": "it-development",
            "language": "English",
            "cost_per_year": 26500,
            "description": (
                "Manchester's CS program covers software engineering, algorithms, "
                "networks, and AI with strong industrial placement opportunities."
            ),
            "who_its_for": (
                "Students who want a well-rounded CS education in a major UK city "
                "with excellent graduate employment outcomes."
            ),
            "career_options": [
                "Software Developer", "Systems Analyst", "DevOps Engineer",
                "AI Engineer", "IT Consultant",
            ],
            "requirements": {
                "min_gpa": 3.5,
                "exams": ["A-Levels", "IB", "IELTS"],
                "min_ielts": 6.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Programming projects", "Hackathons"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2026-01-15",
                "exam_deadline": "2026-01-15",
                "decision_date": "2026-04-30",
            },
            "grants": [
                {
                    "name": "Manchester Global Excellence Award",
                    "amount": "£2,000–£5,000",
                    "conditions": "International students, academic merit",
                },
            ],
        },
        {
            "name": "Data Science (MSc)",
            "direction_slug": "data-science",
            "language": "English",
            "cost_per_year": 27500,
            "description": (
                "1-year MSc covering machine learning, big data analytics, data "
                "engineering, and statistical modelling with industry project."
            ),
            "who_its_for": (
                "Graduates from STEM disciplines who want to transition into "
                "data science roles in industry or research."
            ),
            "career_options": [
                "Data Scientist", "ML Engineer", "Data Analyst",
                "Business Intelligence Analyst", "Data Engineer",
            ],
            "requirements": {
                "min_gpa": 3.3,
                "exams": ["IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Data projects", "Kaggle", "Python/R experience"],
            },
            "deadlines": {
                "application_open": "2025-10-01",
                "application_close": "2026-06-30",
                "exam_deadline": "2026-06-01",
                "decision_date": "2026-07-31",
            },
            "grants": [
                {
                    "name": "Manchester Postgraduate Scholarship",
                    "amount": "£3,000",
                    "conditions": "Merit-based",
                },
            ],
        },
    ],
    "Delft University of Technology": [
        {
            "name": "Computer Science and Engineering (BSc)",
            "direction_slug": "it-development",
            "language": "English",
            "cost_per_year": 11170,
            "description": (
                "TU Delft's CS&E program in the Netherlands combines deep software "
                "engineering fundamentals with practical design and research."
            ),
            "who_its_for": (
                "Students who want a top European technical education at "
                "affordable fees, with strong links to Dutch and global tech industry."
            ),
            "career_options": [
                "Software Engineer", "Systems Developer", "Research Engineer",
                "Product Engineer", "Data Engineer",
            ],
            "requirements": {
                "min_gpa": 3.5,
                "exams": ["IELTS", "TOEFL", "SAT"],
                "min_ielts": 6.5,
                "min_sat": 1350,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Maths/CS competitions", "Programming projects"],
            },
            "deadlines": {
                "application_open": "2025-10-01",
                "application_close": "2026-01-15",
                "exam_deadline": "2026-01-01",
                "decision_date": "2026-04-01",
            },
            "grants": [
                {
                    "name": "Holland Scholarship",
                    "amount": "€5,000 (one-off)",
                    "conditions": "Non-EU students with outstanding academics",
                },
                {
                    "name": "TU Delft Excellence Scholarship",
                    "amount": "Full tuition + €12,000/year living",
                    "conditions": "Top 5% applicants internationally",
                },
            ],
        },
        {
            "name": "Computer Engineering (MSc)",
            "direction_slug": "engineering-architecture",
            "language": "English",
            "cost_per_year": 18750,
            "description": (
                "TU Delft's MSc in Computer Engineering covers embedded systems, "
                "computer architecture, and hardware-software co-design."
            ),
            "who_its_for": (
                "Engineering graduates interested in low-level systems, "
                "embedded computing, and hardware design."
            ),
            "career_options": [
                "Embedded Systems Engineer", "Hardware Engineer", "Systems Architect",
                "FPGA Developer", "IoT Engineer",
            ],
            "requirements": {
                "min_gpa": 3.5,
                "exams": ["IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Electronics projects", "Robotics clubs"],
            },
            "deadlines": {
                "application_open": "2025-10-01",
                "application_close": "2026-04-01",
                "exam_deadline": "2026-03-01",
                "decision_date": "2026-05-15",
            },
            "grants": [
                {
                    "name": "Holland Scholarship",
                    "amount": "€5,000 (one-off)",
                    "conditions": "Non-EU students",
                },
            ],
        },
    ],
    "Ludwig Maximilian University of Munich": [
        {
            "name": "Computer Science (BSc)",
            "direction_slug": "it-development",
            "language": "German / English",
            "cost_per_year": 258,
            "description": (
                "LMU Munich's CS program is tuition-free (semester fees only), "
                "offering strong theoretical foundations and research opportunities."
            ),
            "who_its_for": (
                "Students who want a world-class CS education at near-zero cost "
                "and are willing to learn German or study in English-track courses."
            ),
            "career_options": [
                "Software Engineer", "Research Scientist", "Backend Developer",
                "Systems Programmer", "Algorithm Engineer",
            ],
            "requirements": {
                "min_gpa": 3.5,
                "exams": ["TestDaF", "IELTS", "Abitur / IB"],
                "min_ielts": 6.0,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": False,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Maths olympiads", "Programming projects"],
            },
            "deadlines": {
                "application_open": "2026-05-01",
                "application_close": "2026-07-15",
                "exam_deadline": "2026-06-30",
                "decision_date": "2026-08-15",
            },
            "grants": [
                {
                    "name": "DAAD Scholarship",
                    "amount": "€850/month + travel allowance",
                    "conditions": "International students, competitive academic record",
                },
            ],
        },
        {
            "name": "Informatics (MSc)",
            "direction_slug": "it-development",
            "language": "English",
            "cost_per_year": 258,
            "description": (
                "LMU + TU Munich joint MSc in Informatics — one of Germany's most "
                "prestigious graduate CS programs, practically tuition-free."
            ),
            "who_its_for": (
                "International graduates seeking a research-oriented MSc in Europe "
                "without tuition costs, with pathways to leading German tech companies."
            ),
            "career_options": [
                "Research Engineer", "ML Engineer", "Software Architect",
                "PhD Candidate", "AI Scientist",
            ],
            "requirements": {
                "min_gpa": 3.5,
                "exams": ["IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Research projects", "GitHub portfolio", "Publications"],
            },
            "deadlines": {
                "application_open": "2025-11-15",
                "application_close": "2026-01-15",
                "exam_deadline": "2026-01-01",
                "decision_date": "2026-03-31",
            },
            "grants": [
                {
                    "name": "DAAD Scholarship",
                    "amount": "€850/month",
                    "conditions": "International graduates, merit-based",
                },
            ],
        },
    ],
    "ETH Zurich": [
        {
            "name": "Computer Science (BSc)",
            "direction_slug": "it-development",
            "language": "German",
            "cost_per_year": 730,
            "description": (
                "ETH Zurich's CS program is one of the world's best, offering "
                "rigorous training in algorithms, systems, and AI at near-zero cost."
            ),
            "who_its_for": (
                "Top students with exceptional mathematical ability who want "
                "a world-class education in one of Europe's safest and most liveable cities."
            ),
            "career_options": [
                "Software Engineer", "Algorithm Engineer", "Research Scientist",
                "Systems Architect", "Quant Developer",
            ],
            "requirements": {
                "min_gpa": 3.8,
                "exams": ["Matura", "IB", "TestDaF"],
                "min_ielts": 7.0,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": False,
                "needs_recommendations": False,
                "needs_interview": True,
                "extracurriculars": ["Maths/CS olympiads", "Strong academic record"],
            },
            "deadlines": {
                "application_open": "2025-11-01",
                "application_close": "2026-01-15",
                "exam_deadline": "2026-01-15",
                "decision_date": "2026-05-01",
            },
            "grants": [
                {
                    "name": "ETH Excellence Scholarship",
                    "amount": "CHF 12,000/year + tuition waiver",
                    "conditions": "Top MSc applicants, competitive",
                },
            ],
        },
        {
            "name": "Data Science (MSc)",
            "direction_slug": "data-science",
            "language": "English",
            "cost_per_year": 730,
            "description": (
                "ETH's MSc in Data Science covers ML, statistics, big data systems, "
                "and interdisciplinary data applications. Taught entirely in English."
            ),
            "who_its_for": (
                "STEM graduates who want a top-tier data science education in Europe "
                "at minimal tuition cost with excellent career prospects."
            ),
            "career_options": [
                "Data Scientist", "ML Researcher", "Quantitative Analyst",
                "AI Engineer", "Data Engineer",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["IELTS", "TOEFL"],
                "min_ielts": 7.0,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["ML research projects", "Publications", "Kaggle top rankings"],
            },
            "deadlines": {
                "application_open": "2025-11-01",
                "application_close": "2025-12-15",
                "exam_deadline": "2025-12-01",
                "decision_date": "2026-04-15",
            },
            "grants": [
                {
                    "name": "ETH Excellence Scholarship",
                    "amount": "CHF 12,000/year + tuition waiver",
                    "conditions": "Top MSc applicants, competitive",
                },
            ],
        },
    ],
    "EPFL": [
        {
            "name": "Computer Science (BSc)",
            "direction_slug": "it-development",
            "language": "French / English",
            "cost_per_year": 730,
            "description": (
                "EPFL's CS program is one of Europe's finest, known for its rigour "
                "in algorithms, programming theory, and interdisciplinary projects."
            ),
            "who_its_for": (
                "Highly motivated students who thrive in a rigorous, challenging "
                "environment and want a world-class Swiss engineering education."
            ),
            "career_options": [
                "Software Engineer", "Research Engineer", "Blockchain Developer",
                "Systems Programmer", "Product Engineer",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["Maturité", "IB", "IELTS"],
                "min_ielts": 6.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": False,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Maths/CS olympiads", "Robotics projects"],
            },
            "deadlines": {
                "application_open": "2026-01-15",
                "application_close": "2026-04-30",
                "exam_deadline": "2026-04-01",
                "decision_date": "2026-06-01",
            },
            "grants": [
                {
                    "name": "EPFL Excellence Fellowship",
                    "amount": "CHF 20,000/year",
                    "conditions": "Top MSc applicants from any country",
                },
            ],
        },
        {
            "name": "Data Science (MSc)",
            "direction_slug": "data-science",
            "language": "English",
            "cost_per_year": 730,
            "description": (
                "EPFL's MSc in Data Science is a 2-year program combining machine "
                "learning, applied mathematics, and large-scale data systems."
            ),
            "who_its_for": (
                "Strong quantitative graduates who want to solve complex data problems "
                "and access EPFL's world-class research ecosystem."
            ),
            "career_options": [
                "Data Scientist", "ML Engineer", "Applied Researcher",
                "Quantitative Developer", "AI Product Manager",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["IELTS", "TOEFL"],
                "min_ielts": 7.0,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Kaggle competitions", "Research internships", "Open-source ML"],
            },
            "deadlines": {
                "application_open": "2025-10-15",
                "application_close": "2025-12-15",
                "exam_deadline": "2025-12-01",
                "decision_date": "2026-03-31",
            },
            "grants": [
                {
                    "name": "EPFL Excellence Fellowship",
                    "amount": "CHF 20,000/year",
                    "conditions": "Top MSc applicants from any country",
                },
            ],
        },
    ],
    "University of Toronto": [
        {
            "name": "Computer Science (BSc)",
            "direction_slug": "it-development",
            "language": "English",
            "cost_per_year": 47260,
            "description": (
                "UofT's CS program — home of deep learning pioneers Hinton, LeCun, and Bengio — "
                "offers world-leading AI, systems, and theory research opportunities."
            ),
            "who_its_for": (
                "Students who want to study CS where deep learning was invented, "
                "with access to top research labs and Toronto's growing tech hub."
            ),
            "career_options": [
                "Software Engineer", "ML Researcher", "AI Engineer",
                "Research Scientist", "Tech Entrepreneur",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["SAT", "IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": 1400,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["CS competitions", "Research projects", "Hackathons"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2026-01-13",
                "exam_deadline": "2026-01-01",
                "decision_date": "2026-05-01",
            },
            "grants": [
                {
                    "name": "Lester B. Pearson International Scholarship",
                    "amount": "Full tuition + living expenses",
                    "conditions": "Top international students, exceptional academic and leadership",
                },
                {
                    "name": "University of Toronto Scholars Program",
                    "amount": "$7,500/year",
                    "conditions": "Top incoming students",
                },
            ],
        },
        {
            "name": "Artificial Intelligence (MSc)",
            "direction_slug": "artificial-intelligence",
            "language": "English",
            "cost_per_year": 21890,
            "description": (
                "UofT's MSc in Applied Computing with AI specialisation — "
                "a 1-year industry-focused program at the birthplace of modern deep learning."
            ),
            "who_its_for": (
                "CS graduates who want to build AI systems for industry "
                "and benefit from UofT's unmatched deep learning research ecosystem."
            ),
            "career_options": [
                "ML Engineer", "AI Researcher", "Deep Learning Engineer",
                "NLP Engineer", "Applied Scientist",
            ],
            "requirements": {
                "min_gpa": 3.5,
                "exams": ["IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["ML projects", "Kaggle", "AI research internships"],
            },
            "deadlines": {
                "application_open": "2025-10-01",
                "application_close": "2026-02-01",
                "exam_deadline": "2026-01-15",
                "decision_date": "2026-04-15",
            },
            "grants": [
                {
                    "name": "Ontario Graduate Scholarship",
                    "amount": "CAD $15,000",
                    "conditions": "Academic merit",
                },
            ],
        },
    ],
    "University of British Columbia": [
        {
            "name": "Computer Science (BSc)",
            "direction_slug": "it-development",
            "language": "English",
            "cost_per_year": 40310,
            "description": (
                "UBC's CS program in beautiful Vancouver offers strong fundamentals, "
                "AI specialisations, and excellent co-op work experience options."
            ),
            "who_its_for": (
                "Students who want a top Canadian CS degree with access to "
                "co-op placements at major tech companies and Vancouver's tech scene."
            ),
            "career_options": [
                "Software Developer", "Data Engineer", "AI Engineer",
                "Full-Stack Developer", "Product Manager",
            ],
            "requirements": {
                "min_gpa": 3.6,
                "exams": ["SAT", "IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": 1380,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Programming clubs", "Hackathons", "Science fairs"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2026-01-15",
                "exam_deadline": "2026-01-01",
                "decision_date": "2026-04-30",
            },
            "grants": [
                {
                    "name": "International Major Entrance Scholarship",
                    "amount": "$10,000–$40,000",
                    "conditions": "Top international students by academic standing",
                },
            ],
        },
        {
            "name": "Data Science (MSc)",
            "direction_slug": "data-science",
            "language": "English",
            "cost_per_year": 9690,
            "description": (
                "UBC's Master of Data Science is a 10-month intensive program "
                "covering statistical learning, ML, and data visualisation."
            ),
            "who_its_for": (
                "Quantitative graduates who want to quickly transition into "
                "data science careers in Canada's thriving tech ecosystem."
            ),
            "career_options": [
                "Data Scientist", "ML Engineer", "Data Analyst",
                "Research Analyst", "Business Intelligence Analyst",
            ],
            "requirements": {
                "min_gpa": 3.3,
                "exams": ["IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Data projects", "Python/R experience", "Statistics coursework"],
            },
            "deadlines": {
                "application_open": "2025-10-01",
                "application_close": "2026-02-28",
                "exam_deadline": "2026-02-01",
                "decision_date": "2026-04-30",
            },
            "grants": [
                {
                    "name": "UBC Graduate Award",
                    "amount": "CAD $6,000",
                    "conditions": "Academic merit",
                },
            ],
        },
    ],
    "National University of Singapore": [
        {
            "name": "Computer Science (BSc)",
            "direction_slug": "it-development",
            "language": "English",
            "cost_per_year": 17550,
            "description": (
                "NUS CS is Asia's top-ranked program, offering specialisations in "
                "AI, software engineering, security, and multimedia at world-class facilities."
            ),
            "who_its_for": (
                "Students from across Asia and the world who want an elite CS "
                "education with access to Singapore's thriving tech industry."
            ),
            "career_options": [
                "Software Engineer", "AI Engineer", "Cybersecurity Analyst",
                "Full-Stack Developer", "Research Scientist",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["A-Levels", "IB", "SAT", "IELTS"],
                "min_ielts": 6.5,
                "min_sat": 1450,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Programming olympiads", "Research projects", "Hackathons"],
            },
            "deadlines": {
                "application_open": "2025-10-01",
                "application_close": "2026-02-28",
                "exam_deadline": "2026-02-01",
                "decision_date": "2026-04-30",
            },
            "grants": [
                {
                    "name": "ASEAN Undergraduate Scholarship",
                    "amount": "Full tuition + living allowance",
                    "conditions": "ASEAN nationals with outstanding academics",
                },
                {
                    "name": "NUS Study Award",
                    "amount": "SGD $5,000",
                    "conditions": "International students with financial need",
                },
            ],
        },
        {
            "name": "Business Analytics (MSc)",
            "direction_slug": "data-science",
            "language": "English",
            "cost_per_year": 37000,
            "description": (
                "NUS's 1-year MSc in Business Analytics combines data science, "
                "analytics, and business strategy to develop industry-ready analysts."
            ),
            "who_its_for": (
                "Graduates from any discipline who want to combine data skills "
                "with business acumen and work in analytics-driven organisations."
            ),
            "career_options": [
                "Business Analyst", "Data Analyst", "Analytics Consultant",
                "BI Manager", "Strategy Analyst",
            ],
            "requirements": {
                "min_gpa": 3.3,
                "exams": ["GMAT", "GRE", "IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": True,
                "extracurriculars": ["Business projects", "Analytics internships"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2026-03-31",
                "exam_deadline": "2026-03-01",
                "decision_date": "2026-05-31",
            },
            "grants": [
                {
                    "name": "NUS Business School Scholarship",
                    "amount": "Partial tuition",
                    "conditions": "Academic and professional merit",
                },
            ],
        },
    ],
    "KAIST": [
        {
            "name": "Computer Science (BSc)",
            "direction_slug": "it-development",
            "language": "English / Korean",
            "cost_per_year": 4400,
            "description": (
                "KAIST's CS program is South Korea's best, offering research-intensive "
                "training in AI, systems, and algorithms with English-track options."
            ),
            "who_its_for": (
                "High-achieving students interested in science and technology "
                "who want a research university experience in Asia at low cost."
            ),
            "career_options": [
                "Software Engineer", "ML Researcher", "Systems Engineer",
                "AI Engineer", "Research Scientist",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["SAT", "IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": 1400,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": True,
                "extracurriculars": ["Math/CS olympiads", "Research projects"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2025-11-01",
                "exam_deadline": "2025-10-31",
                "decision_date": "2025-12-15",
            },
            "grants": [
                {
                    "name": "KAIST International Scholarship",
                    "amount": "Full tuition + monthly stipend",
                    "conditions": "Outstanding international students",
                },
            ],
        },
        {
            "name": "Electrical Engineering (BSc)",
            "direction_slug": "engineering-architecture",
            "language": "English / Korean",
            "cost_per_year": 4400,
            "description": (
                "KAIST's EE program covers circuits, signal processing, semiconductors, "
                "and communications — foundational for hardware and chip design careers."
            ),
            "who_its_for": (
                "Students passionate about electronics, hardware systems, "
                "and semiconductor technology in the world's top chip-producing nation."
            ),
            "career_options": [
                "Hardware Engineer", "Chip Designer", "Signal Processing Engineer",
                "Embedded Systems Engineer", "RF Engineer",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["SAT", "IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": 1350,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": True,
                "extracurriculars": ["Physics/maths olympiads", "Electronics projects"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2025-11-01",
                "exam_deadline": "2025-10-31",
                "decision_date": "2025-12-15",
            },
            "grants": [
                {
                    "name": "KAIST International Scholarship",
                    "amount": "Full tuition + monthly stipend",
                    "conditions": "Outstanding international students",
                },
            ],
        },
    ],
    "Imperial College London": [
        {
            "name": "Computing (MEng)",
            "direction_slug": "it-development",
            "language": "English",
            "cost_per_year": 37900,
            "description": (
                "Imperial's 4-year MEng in Computing is one of the UK's most rigorous "
                "CS programs, covering AI, systems, graphics, and software engineering."
            ),
            "who_its_for": (
                "Top students who want an integrated master's degree from a "
                "global top-10 university in the heart of London."
            ),
            "career_options": [
                "Software Engineer", "AI Researcher", "Systems Architect",
                "Quant Developer", "Technology Consultant",
            ],
            "requirements": {
                "min_gpa": 3.9,
                "exams": ["A-Levels", "IB", "IELTS"],
                "min_ielts": 7.0,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Maths/CS olympiads", "Research or open-source projects"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2026-01-15",
                "exam_deadline": "2026-01-15",
                "decision_date": "2026-04-30",
            },
            "grants": [
                {
                    "name": "Imperial President's Scholarship",
                    "amount": "Full tuition + £5,000/year",
                    "conditions": "Top PhD applicants; partial funding available for UG",
                },
            ],
        },
        {
            "name": "Biomedical Engineering (MEng)",
            "direction_slug": "medicine-biology",
            "language": "English",
            "cost_per_year": 37900,
            "description": (
                "Imperial's MEng in Biomedical Engineering combines engineering "
                "principles with medical applications, from devices to biosensors."
            ),
            "who_its_for": (
                "Students at the intersection of engineering and medicine who "
                "want to design devices, develop diagnostics, or pursue clinical engineering."
            ),
            "career_options": [
                "Biomedical Engineer", "Medical Device Designer", "Clinical Engineer",
                "Biosensor Developer", "Healthcare Tech Entrepreneur",
            ],
            "requirements": {
                "min_gpa": 3.8,
                "exams": ["A-Levels", "IB", "IELTS"],
                "min_ielts": 7.0,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Biology/chemistry lab experience", "Engineering projects"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2026-01-15",
                "exam_deadline": "2026-01-15",
                "decision_date": "2026-04-30",
            },
            "grants": [
                {
                    "name": "Imperial College Trust Scholarship",
                    "amount": "£10,000",
                    "conditions": "International students with exceptional academics",
                },
            ],
        },
    ],
    "Seoul National University": [
        {
            "name": "Computer Science and Engineering (BSc)",
            "direction_slug": "it-development",
            "language": "Korean / English",
            "cost_per_year": 5500,
            "description": (
                "SNU's CSE program is South Korea's most prestigious, combining "
                "strong theoretical foundations with major research and industry connections."
            ),
            "who_its_for": (
                "High-achieving students interested in software, AI, or systems "
                "who want South Korea's top university at accessible cost."
            ),
            "career_options": [
                "Software Engineer", "AI Engineer", "Systems Developer",
                "Research Scientist", "Tech Entrepreneur",
            ],
            "requirements": {
                "min_gpa": 3.8,
                "exams": ["CSAT", "SAT", "IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": 1400,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": True,
                "extracurriculars": ["CS / maths olympiads", "Research internships"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2025-11-15",
                "exam_deadline": "2025-11-01",
                "decision_date": "2025-12-20",
            },
            "grants": [
                {
                    "name": "SNU Global Scholarship",
                    "amount": "Full tuition",
                    "conditions": "Outstanding international students",
                },
            ],
        },
        {
            "name": "Industrial Engineering (BSc)",
            "direction_slug": "engineering-architecture",
            "language": "Korean / English",
            "cost_per_year": 5500,
            "description": (
                "SNU's Industrial Engineering program covers operations research, "
                "supply chain, systems engineering, and management science."
            ),
            "who_its_for": (
                "Students interested in optimising complex systems — from logistics "
                "to manufacturing — using quantitative and engineering methods."
            ),
            "career_options": [
                "Operations Research Analyst", "Supply Chain Manager", "Systems Engineer",
                "Management Consultant", "Project Manager",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["CSAT", "SAT", "IELTS", "TOEFL"],
                "min_ielts": 6.0,
                "min_sat": 1350,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Maths olympiads", "Robotics / engineering clubs"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2025-11-15",
                "exam_deadline": "2025-11-01",
                "decision_date": "2025-12-20",
            },
            "grants": [
                {
                    "name": "SNU Global Scholarship",
                    "amount": "Full tuition",
                    "conditions": "Outstanding international students",
                },
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# Seed logic
# ---------------------------------------------------------------------------

async def main() -> None:
    async with async_session() as db:
        uni_inserted = uni_updated = uni_skipped = 0
        prog_inserted = prog_updated = prog_skipped = 0

        for uni_data in UNIVERSITIES:
            result = await db.execute(
                select(University).where(University.name == uni_data["name"])
            )
            existing_uni = result.scalar_one_or_none()

            if existing_uni is None:
                existing_uni = University(**uni_data)
                db.add(existing_uni)
                await db.flush()
                uni_inserted += 1
            else:
                changed = False
                for field in ("country", "city", "website", "ranking", "description"):
                    if getattr(existing_uni, field) != uni_data.get(field):
                        setattr(existing_uni, field, uni_data[field])
                        changed = True
                if changed:
                    uni_updated += 1
                else:
                    uni_skipped += 1

            programs = PROGRAMS_BY_UNIVERSITY.get(uni_data["name"], [])
            for prog_data in programs:
                result = await db.execute(
                    select(Program).where(
                        Program.university_id == existing_uni.id,
                        Program.name == prog_data["name"],
                    )
                )
                existing_prog = result.scalar_one_or_none()

                if existing_prog is None:
                    prog = Program(university_id=existing_uni.id, **prog_data)
                    db.add(prog)
                    prog_inserted += 1
                else:
                    changed = False
                    for field in (
                        "direction_slug", "language", "cost_per_year", "description",
                        "who_its_for", "career_options", "requirements", "deadlines", "grants",
                    ):
                        if getattr(existing_prog, field) != prog_data.get(field):
                            setattr(existing_prog, field, prog_data[field])
                            changed = True
                    if changed:
                        prog_updated += 1
                    else:
                        prog_skipped += 1

        await db.commit()

    total_unis = len(UNIVERSITIES)
    total_progs = sum(len(v) for v in PROGRAMS_BY_UNIVERSITY.values())
    print(
        f"Universities — inserted: {uni_inserted}, updated: {uni_updated}, "
        f"skipped: {uni_skipped}. Total in bank: {total_unis}"
    )
    print(
        f"Programs — inserted: {prog_inserted}, updated: {prog_updated}, "
        f"skipped: {prog_skipped}. Total in bank: {total_progs}"
    )


if __name__ == "__main__":
    asyncio.run(main())
