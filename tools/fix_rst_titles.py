from pathlib import Path

MARKS = set('=-~^"')
folder = Path(r'C:\Users\rokin\Downloads\image_batch_studio_day13-14') / 'docs' / 'source'
fixed = 0
for path in sorted(folder.glob('*.rst')):
    lines = path.read_text(encoding='utf-8').split('\n')
    changed = False
    for index in range(1, len(lines)):
        previous, current = lines[index - 1], lines[index]
        if len(current) >= 2 and len(set(current)) == 1 and current[0] in MARKS:
            if previous.strip() and len(current) < len(previous.rstrip()):
                lines[index] = current[0] * len(previous.rstrip())
                changed = True
    if changed:
        path.write_text('\n'.join(lines), encoding='utf-8')
        fixed += 1
        print('исправлено:', path.name)
print('файлов исправлено:', fixed)
