"""
Add CTC and Notice Period columns to users table.
"""

import asyncio
from sqlalchemy import text
from app.database import engine

async def migrate():
    async with engine.begin() as conn:
        for col, col_type, default in [
            ("current_ctc", "FLOAT", "0"),
            ("expected_ctc", "FLOAT", "0"),
            ("notice_period_days", "INTEGER", "0"),
        ]:
            try:
                await conn.execute(text(
                    f"ALTER TABLE users ADD COLUMN {col} {col_type} DEFAULT {default}"
                ))
                print(f"  [OK] Added column: {col}")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print(f"  [SKIP] Column already exists: {col}")
                else:
                    print(f"  [ERR] Error adding {col}: {e}")

    print("\nMigration complete!")

if __name__ == "__main__":
    asyncio.run(migrate())
