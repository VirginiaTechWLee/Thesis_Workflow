"""
Generate baseline Bush.blk configuration
Bolt 1: K4=1e8 (driving CBUSH), K5=1e12, K6=1e12
Bolts 2-10: K4=1e12, K5=1e12, K6=1e12 (all healthy)
All bolts: K1=1e6, K2=1e6, K3=1e6 (translational)
"""

def generate_baseline_bush():
    with open('Bush.blk', 'w') as f:
        # Bolt 1 - Driving CBUSH
        f.write("PBUSH   1       K       1.+6    1.+6    1.+6    1.+8    1.+12   1.+12\n")
        
        # Bolts 2-10 - All healthy
        for bolt_id in range(2, 11):
            f.write(f"PBUSH   {bolt_id}       K       1.+6    1.+6    1.+6    1.+12   1.+12   1.+12\n")
    
    print("Generated baseline Bush.blk")
    print("  Bolt 1:  K4=1e8 (driving), K5=1e12, K6=1e12")
    print("  Bolts 2-10: K4=1e12, K5=1e12, K6=1e12 (healthy)")

if __name__ == "__main__":
    generate_baseline_bush()
