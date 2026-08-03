import sys

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    filename = 'scripts/seed_almaty_universities.py'
    with open(filename, encoding='utf-8') as f:
        content = f.read()
    
    lines = content.splitlines()
    all_slugs = set()
    for line in lines:
        if '"direction_slugs":' in line:
            parts = line.split('[')[1].split(']')[0].replace('"', '').replace("'", '').split(',')
            for s in parts:
                if s.strip():
                    all_slugs.add(s.strip())
                    
    print(f"Unique slugs in {filename}:")
    for s in sorted(all_slugs):
        print(f"  {s}")

if __name__ == '__main__':
    main()
