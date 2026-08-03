import sys
from scripts.seed_akinator_content import SPECIALTIES

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    for spec in SPECIALTIES:
        if spec['section'] == 'akinator-business-sales':
            print(f"{spec['slug']}: {spec['name']} (professions: {spec.get('professions')})")

if __name__ == '__main__':
    main()
