import sys

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    with open('scripts/seed_akinator_content.py', encoding='utf-8') as f:
        content = f.read()

    lines = content.splitlines()
    for i, line in enumerate(lines):
        if '"slug": "finance-accounting"' in line or '"slug": "marketing-advertising"' in line or '"slug": "marketing"' in line:
            print(f"=== Line {i+1}: {line.strip()} ===")
            for j in range(1, 25):
                if i+j < len(lines):
                    l = lines[i+j]
                    print(l)
                    if '"professions"' in l or '"subjects_required"' in l:
                        break

if __name__ == '__main__':
    main()
