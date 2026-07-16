import asyncio
import json
import os
from sqlalchemy import select, text
from app.config import settings
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

async def export_table(session: AsyncSession, table_name: str, output_path: str):
    try:
        # Check if table exists in DB first
        check_stmt = text(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table_name}')")
        exists = (await session.execute(check_stmt)).scalar()
        if not exists:
            print(f"Table {table_name} does not exist in the database, skipping export.")
            return

        result = await session.execute(text(f"SELECT * FROM {table_name}"))
        rows = result.mappings().all()
        # Convert rows to dicts, handling UUIDs, datetimes, and other types
        data = []
        for row in rows:
            row_dict = {}
            for k, v in row.items():
                if hasattr(v, "isoformat"):
                    row_dict[k] = v.isoformat()
                elif hasattr(v, "hex"):
                    row_dict[k] = str(v)
                else:
                    row_dict[k] = v
            data.append(row_dict)
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Exported {len(data)} rows from {table_name} to {output_path}")
    except Exception as e:
        print(f"Failed to export {table_name}: {e}")

async def main():
    engine = create_async_engine(settings.DATABASE_URL)
    os.makedirs("snapshots", exist_ok=True)
    
    tables = ["questions", "user_responses", "analysis_results", "roadmaps", "direction_inquiries"]
    
    async with AsyncSession(engine) as session:
        for table in tables:
            await export_table(session, table, f"snapshots/{table}.json")
            
if __name__ == "__main__":
    asyncio.run(main())
