from pathlib import Path
root=Path(__file__).parent
p=root/'index.html';html=p.read_text(encoding='utf-8')
fragment=(root/'history.html').read_text(encoding='utf-8')
if '<section id="history"' in html:
 start=html.index('<section id="history"');end=html.index('<section id="players"',start)
 html=html[:start]+fragment+'\n'+html[end:]
else:html=html.replace('<section id="players"',fragment+'\n<section id="players"',1)
if 'history.css' not in html:html=html.replace('<link rel="stylesheet" href="catalog.css">','<link rel="stylesheet" href="catalog.css"><link rel="stylesheet" href="history.css">')
if 'history.js' not in html:html=html.replace('<script src="catalog.js" defer></script>','<script src="catalog.js" defer></script><script src="history.js" defer></script>')
if 'href="#history"' not in html:html=html.replace('<a href="#players">','<a href="#history">◷ <span>Desempenho</span></a><a href="#players">',1)
p.write_text(html,encoding='utf-8')
print('History layout assembled')
