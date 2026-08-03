import sys

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    for filename in ['scripts/seed_astana_universities.py', 'scripts/seed_almaty_universities.py']:
        with open(filename, encoding='utf-8') as f:
            content = f.read()
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if 'akinator-business-sales' in line:
                prog_name = 'Unknown'
                for j in range(i, -1, -1):
                    if '"name"' in lines[j]:
                        prog_name = lines[j].strip()
                        break
                print(f'{filename}:{i+1}: {prog_name} -> {line.strip()}')

if __name__ == '__main__':
    main()
