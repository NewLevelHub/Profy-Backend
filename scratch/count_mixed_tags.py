import sys

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    for filename in ['scripts/seed_astana_universities.py', 'scripts/seed_almaty_universities.py']:
        with open(filename, encoding='utf-8') as f:
            content = f.read()
        lines = content.splitlines()
        
        count = 0
        current_program = None
        for i, line in enumerate(lines):
            if '"name":' in line:
                current_program = line.strip()
            elif '"direction_slugs":' in line:
                parts = line.split('[')[1].split(']')[0].replace('"', '').replace("'", '').split(',')
                slugs = [s.strip() for s in parts if s.strip()]
                
                section_tags = [s for s in slugs if s.startswith('akinator-')]
                leaf_tags = [s for s in slugs if not s.startswith('akinator-')]
                
                if section_tags and leaf_tags:
                    count += 1
        print(f"{filename}: {count} programs with mixed tags")

if __name__ == '__main__':
    main()
