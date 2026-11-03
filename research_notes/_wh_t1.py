import sys
sys.path.insert(0, 'research_notes')
from _wh_snippets import P1_CONSTS, P1_DOC
PATH = 'tcgpings/retailers/warehouse.py'
src = open(PATH, encoding='utf-8').read()
src = src.replace('import re\nfrom urllib.parse import quote', 'import re\nfrom importlib import resources\nfrom urllib.parse import quote', 1)
old_consts = 'GONE_AFTER_SCANS = 3  # listings can flicker, so a product must be missing this many scans in a row'
assert old_consts in src
src = src.replace(old_consts, P1_CONSTS.rstrip(), 1)
acc = chr(0xE9)
old_bullet = '  - Per-store stock: the store-availability call needs a signed per-product token, and hot\n    Pok' + chr(0xE9) + 'mon products sit behind a Cloudflare challenge. Left out deliberately.\n'
assert old_bullet in src, 'bullet not found'
src = src.replace(old_bullet, P1_DOC, 1)
open(PATH, 'w', encoding='utf-8', newline='').write(src)
print('part 1 done')
