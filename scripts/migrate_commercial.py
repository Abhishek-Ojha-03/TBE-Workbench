"""One-time migration: add commercial price columns to bidders table."""
import sqlite3, os

db_path = os.path.join(os.path.dirname(__file__), '..', 'tbe_workbench.db')
con = sqlite3.connect(db_path)
cur = con.cursor()

cols = [r[1] for r in cur.execute('PRAGMA table_info(bidders)').fetchall()]
print('Existing cols:', cols)

if 'quoted_price' not in cols:
    cur.execute('ALTER TABLE bidders ADD COLUMN quoted_price REAL')
    print('Added quoted_price')
else:
    print('quoted_price already exists')

if 'price_currency' not in cols:
    cur.execute("ALTER TABLE bidders ADD COLUMN price_currency VARCHAR(10) DEFAULT 'INR'")
    print('Added price_currency')
else:
    print('price_currency already exists')

if 'commercial_rank' not in cols:
    cur.execute('ALTER TABLE bidders ADD COLUMN commercial_rank INTEGER')
    print('Added commercial_rank')
else:
    print('commercial_rank already exists')

con.commit()

# Verify
cols_after = [r[1] for r in cur.execute('PRAGMA table_info(bidders)').fetchall()]
print('Cols after migration:', cols_after)
con.close()
print('Migration complete.')
