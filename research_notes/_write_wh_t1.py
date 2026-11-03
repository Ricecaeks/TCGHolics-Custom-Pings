import base64, pathlib
s = (
    "import sys\n"
    "sys.path.insert(0, 'research_notes')\n"
    "from _wh_snippets import P1_CONSTS, P1_DOC\n"
    "PATH = 'tcgpings/retailers/warehouse.py'\n"
    "src = open(PATH, encoding='utf-8').read()\n"
    "src = src.replace('import re\\nfrom urllib.parse import quote', 'import re\\nfrom importlib import resources\\nfrom urllib.parse import quote', 1)\n"
    "old_consts = 'GONE_AFTER_SCANS = 3  # listings can flicker, so a product must be missing this many scans in a row'\n"
    "assert old_consts in src\n"
    "src = src.replace(old_consts, P1_CONSTS.rstrip(), 1)\n"
    "acc = chr(0xE9)\n"
    "old_bullet = '  - Per-store stock: the store-availability call needs a signed per-product token, and hot\\n    Pok' + chr(0xE9) + 'mon products sit behind a Cloudflare challenge. Left out deliberately.\\n'\n"
    "assert old_bullet in src, 'bullet not found'\n"
    "src = src.replace(old_bullet, P1_DOC, 1)\n"
    "open(PATH, 'w', encoding='utf-8', newline='').write(src)\n"
    "print('part 1 done')\n"
)
pathlib.Path("research_notes/_wh_t1.py").write_text(s, encoding="utf-8")
print("generator written")
