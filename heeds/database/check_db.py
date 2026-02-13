import sqlite3
import os

conn = sqlite3.connect(r'D:\thesis_database\thesis_results.db')
c = conn.cursor()

print('=== DATABASE SUMMARY ===')
for row in c.execute('SELECT study_name, COUNT(case_id) FROM studies s LEFT JOIN cases c ON s.study_id = c.study_id GROUP BY s.study_id'):
    print(f'{row[0]}: {row[1]} cases')

print()
print('Cases:', c.execute('SELECT COUNT(*) FROM cases').fetchone()[0])
print('PSD rows:', c.execute('SELECT COUNT(*) FROM psd_data').fetchone()[0])
print('Peak rows:', c.execute('SELECT COUNT(*) FROM peaks').fetchone()[0])
print('DB size:', round(os.path.getsize(r'D:\thesis_database\thesis_results.db') / 1024 / 1024, 1), 'MB')

conn.close()
