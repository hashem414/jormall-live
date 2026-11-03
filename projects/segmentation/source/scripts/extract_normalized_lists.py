import csv

path = 'data/processed_segments.csv'
with open(path, newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        value = row.get('Raw List')
        if value is not None:
            print(value)
