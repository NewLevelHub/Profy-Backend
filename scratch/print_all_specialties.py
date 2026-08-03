import sys
from scripts.seed_akinator_content import SPECIALTIES

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    print(f"SPECIALTIES count: {len(SPECIALTIES)}")
    for spec in SPECIALTIES[:10]:
        print(f"Slug: {spec.get('slug')}, Section: {spec.get('section')}")

if __name__ == '__main__':
    main()
