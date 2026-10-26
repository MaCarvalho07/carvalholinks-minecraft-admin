"""Reassemble catalog fragments into the buildless Cockpit page."""
from pathlib import Path

root=Path(__file__).parent
p=root/'index.html';html=p.read_text(encoding='utf-8')
catalog=(root/'catalog.html').read_text(encoding='utf-8')
dialog=(root/'catalog-dialog.html').read_text(encoding='utf-8')
start=html.index('<section id="explore"')
end=html.index('<section id="addons"',start)
html=html[:start]+catalog+'\n'+html[end:]
start=html.index('<dialog id="cf-dialog"')
end=html.index('</dialog>',start)+len('</dialog>')
html=html[:start]+dialog+html[end:]
p.write_text(html,encoding='utf-8')
print('Catalog fragments assembled into index.html')
