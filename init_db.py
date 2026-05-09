import sqlite3

def init_db():
    conn = sqlite3.connect('mock_sap.db')
    cursor = conn.cursor()

    # Create inventory table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            item_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            transit_time INTEGER NOT NULL,
            spot_rate REAL NOT NULL,
            supplier_id TEXT NOT NULL
        )
    ''')

    # Create task_queue table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS task_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            status TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Seed data
    cursor.execute('DELETE FROM inventory')

    seed_data = [
        # Tenant A
        ('Tenant_A', 'Semiconductors', 500, 14, 1500.50, 'SUP_001'),
        ('Tenant_A', 'Copper Wire', 2000, 7, 300.00, 'SUP_002'),
        ('Tenant_A', 'Lithium Batteries', 100, 21, 2500.00, 'SUP_003'),
        ('Tenant_A', 'Steel Plates', 10000, 30, 800.25, 'SUP_004'),
        ('Tenant_A', 'Plastic Casing', 5000, 5, 100.00, 'SUP_005'),
        # Tenant B
        ('Tenant_B', 'Cotton Yarn', 3000, 10, 200.00, 'SUP_006'),
        ('Tenant_B', 'Synthetic Dye', 500, 12, 450.75, 'SUP_007'),
        ('Tenant_B', 'Zippers', 10000, 5, 50.00, 'SUP_008'),
        ('Tenant_B', 'Denim Fabric', 1500, 15, 600.00, 'SUP_009'),
        ('Tenant_B', 'Packaging Boxes', 8000, 3, 20.00, 'SUP_010'),
    ]

    cursor.executemany('''
        INSERT INTO inventory (tenant_id, item_name, quantity, transit_time, spot_rate, supplier_id)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', seed_data)

    conn.commit()
    conn.close()
    print("Database initialized and seeded.")

if __name__ == '__main__':
    init_db()
