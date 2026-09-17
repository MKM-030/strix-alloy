import re
p = r'C:/Projects/strix-alloy-clean/README.md'
t = open(p, encoding='utf-8').read()
nums = ['1,031', '812', '251,904', '28.3', '32.6', '125B', 'PROJFIX', '74.0', '5.4',
        '133 GB', '4.219', 'IQ4_NL', '32,768', 'olliehm', 'stew675', 'pwilkin', 'halogen',
        '51B', '200', '236']
print(f"bytes={len(t)}  lines={t.count(chr(10))+1}")
for n in nums:
    print(f"  {n:<12} {'present x'+str(t.count(n)) if n in t else 'MISSING'}")
print("\nheadings:")
for line in t.splitlines():
    if line.startswith('#'):
        print('  ' + line)
print(f"\ntables: {sum(1 for l in t.splitlines() if l.startswith('| '))} table rows")
