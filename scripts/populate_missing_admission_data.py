import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select

from app.database import async_session
from app.models.program import Program
from app.models.university import University

async def main() -> None:
    async with async_session() as db:
        # Find Esil University
        result = await db.execute(select(University).where(University.name.ilike('%Esil%')))
        university = result.scalar_one_or_none()
        
        if not university:
            print("Esil University not found")
            return
            
        print(f"Updating {university.name}...")
        
        # Update university contacts
        university.contacts = {
            "address": "г. Астана, ул. Ахмета Жубанова, 7",
            "phone": "+7 708 227 0101",
            "whatsapp": "+7 708 017 3173",
            "instagram": "@esil_university"
        }
        
        # Update Мировая экономика
        result = await db.execute(select(Program).where(Program.university_id == university.id).where(Program.name.ilike('%Мировая экономика%')))
        program = result.scalar_one_or_none()
        
        if program:
            print(f"Updating {program.name}...")
            requirements = dict(program.requirements or {})
            requirements["min_ent_paid"] = 50
            requirements["duration_years"] = 4
            requirements["has_dual_degree"] = True
            requirements["grants_allocated_count"] = 150
            requirements["grant_scores"] = {
                "Общий конкурс": "82",
                "Сельская квота": "75"
            }
            # Remove dummy description if it's "Направления"
            if program.description and program.description.strip().lower() == "направления":
                program.description = "Программа готовит специалистов в области международной экономики, внешнеэкономической деятельности и международных финансов."
                
            program.requirements = requirements
            
        await db.commit()
        print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
