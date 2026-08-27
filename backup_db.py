import psycopg2
from psycopg2 import extensions
import ssl
import os
import sys
from datetime import datetime

DB_URL = "postgresql://patilidunya_user:q4qIYS4Nk3zc8RlEXYxdttSvycigbibh@dpg-d9ih0djtqb8s738ss6mg-a.virginia-postgres.render.com/patilidunya"

print("Veritabanina baglaniliyor (psycopg2-binary)...")

try:
    conn = psycopg2.connect(DB_URL, sslmode='require')
    print("Baglanti basarili!")
except Exception as e:
    print(f"HATA: {e}")
    print("\nDatabase uykuda olabilir. Render'da PostgreSQL servisine git ve 'Manual Deploy' de.")
    input("Devam icin Enter...")
    sys.exit(1)

cur = conn.cursor()

cur.execute("""
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'public' ORDER BY table_name
""")
tables = [row[0] for row in cur.fetchall()]
print(f"Tablolar: {tables}")

backup_file = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"

with open(backup_file, 'w', encoding='utf-8') as f:
    f.write(f"-- Patili Dunya DB Backup - {datetime.now()}\n\n")
    
    for table in tables:
        print(f"  {table} export ediliyor...")
        
        cur.execute(f"SELECT * FROM {table}")
        rows = cur.fetchall()
        
        cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name='{table}' ORDER BY ordinal_position")
        columns = [row[0] for row in cur.fetchall()]
        
        f.write(f"\n-- {table} ({len(rows)} satir)\n")
        f.write(f"TRUNCATE {table} CASCADE;\n")
        
        if rows:
            col_str = ', '.join(columns)
            for row in rows:
                vals = []
                for v in row:
                    if v is None:
                        vals.append('NULL')
                    elif isinstance(v, bool):
                        vals.append('TRUE' if v else 'FALSE')
                    elif isinstance(v, (int, float)):
                        vals.append(str(v))
                    else:
                        escaped = str(v).replace("'", "''")
                        vals.append(f"'{escaped}'")
                f.write(f"INSERT INTO {table} ({col_str}) VALUES ({', '.join(vals)});\n")
        
        print(f"    -> {len(rows)} satir")

conn.close()
print(f"\nBackup tamamlandi: {backup_file}")
print(f"Boyut: {os.path.getsize(backup_file)} byte")

input("\nDevam etmek icin Enter'a bas...")
