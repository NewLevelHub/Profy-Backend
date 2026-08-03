import sys

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    for filename in ['scripts/seed_astana_universities.py', 'scripts/seed_almaty_universities.py']:
        with open(filename, encoding='utf-8') as f:
            content = f.read()
        lines = content.splitlines()
        
        # We want to find program blocks.
        # A simple way is to parse lines and keep track of current program name and its direction_slugs.
        current_program = None
        for i, line in enumerate(lines):
            if '"name":' in line:
                current_program = line.strip()
            elif '"direction_slugs":' in line:
                # parse the list
                # e.g., "direction_slugs": ["finance-accounting", "akinator-business-sales"],
                parts = line.split('[')[1].split(']')[0].replace('"', '').replace("'", '').split(',')
                slugs = [s.strip() for s in parts if s.strip()]
                
                # Check if it has any section tag (starts with akinator-) AND any leaf tag (doesn't start with akinator-)
                section_tags = [s for s in slugs if s.startswith('akinator-')]
                leaf_tags = [s for s in slugs if not s.startswith('akinator-')]
                
                if section_tags and leaf_tags:
                    print(f"{filename}:{i+1}: {current_program} has mixed tags: {slugs}")

if __name__ == '__main__':
    main()
