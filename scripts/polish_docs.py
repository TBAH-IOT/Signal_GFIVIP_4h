from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
replacements={
    '241lệnh':'241 lệnh','284quyết định':'284 quyết định','17.268mốc':'17.268 mốc',
    '308lệnh':'308 lệnh','20coin':'20 coin','500USDT':'500 USDT','10.000USDT':'10.000 USDT',
    '10bps':'10 bps','5thẻ':'5 thẻ','5tín hiệu':'5 tín hiệu','5signal':'5 signal',
    '5card':'5 card','5notification':'5 notification','20tests':'20 tests','7tests':'7 tests',
    '96marks':'96 marks','168quan sát':'168 quan sát','672nến':'672 nến','16nến':'16 nến',
    '17điểm':'17 điểm','5mẫu':'5 mẫu','2user':'2 user','theo2user':'theo 2 user',
    'có>=5':'có >=5','dưới5':'dưới 5','trong120s':'trong 120s','>=60s':'>=60s',
    '16:15UTC':'16:15 UTC','Python3.13':'Python 3.13','pip>=22.3':'pip >=22.3',
    '25/04–22/10/2026 gồm241':'25/04–22/10/2026 gồm 241','chuông/unread':'chuông/unread',
    'WRgross':'WR gross','WRnet':'WR net','MaxDD':'Max DD','20.000mốc':'20.000 mốc',
    'nến15m':'nến 15m','mỗi15m':'mỗi 15m','khoảng5s':'khoảng 5s',
    'giữ4h':'giữ 4h','hết4h':'hết 4h','đúng4h':'đúng 4h',
}
for p in [ROOT/'README.md',*(ROOT/'docs').glob('*.md')]:
    text=p.read_text(encoding='utf-8')
    for a,b in replacements.items():text=text.replace(a,b)
    p.write_text(text,encoding='utf-8')
print('Polished public Markdown spacing; signal/API identifiers unchanged')
