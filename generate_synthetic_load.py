import sqlite3
import random

def generate_load():
    conn = sqlite3.connect('mock_sap.db')
    cursor = conn.cursor()

    edge_case_data = []
    for i in range(1000):
        tenant_id = random.choice(['Tenant_A', 'Tenant_B'])
        # Edge cases: negative quantity, null/zero transit times, huge spot rates
        quantity = random.choice([-500, 0, 1000000])
        transit_time = random.choice([0, -5, 365])
        spot_rate = random.choice([0.0, 999999.99, -150.0])
        supplier_id = f"EDGE_SUP_{i}"

        edge_case_data.append((tenant_id, f"Edge_Item_{i}", quantity, transit_time, spot_rate, supplier_id))

    cursor.executemany('''
        INSERT INTO inventory (tenant_id, item_name, quantity, transit_time, spot_rate, supplier_id)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', edge_case_data)

    conn.commit()
    conn.close()
    print("Injected 1,000 synthetic edge-case rows into the database.")

if __name__ == '__main__':
    generate_load()
