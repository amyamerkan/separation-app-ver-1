"""Extract body page numbers for cached Word TOC and figure/table references."""
import argparse,json,re
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('pdf',type=Path);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
manifest=json.loads((ROOT/'data/index_manifest.json').read_text())
norm=lambda s:re.sub(r'\s+','',s).replace('–','-').replace('−','-')
pages=[p.extract_text() or '' for p in PdfReader(a.pdf).pages]
start=next(i for i,t in enumerate(pages) if '1.1Bốicảnhvàlýdochọnđềtài' in norm(t) and 'Mộtbảnnhạchoànchỉnh' in norm(t))
items=[t for _,t in manifest['headings']]+manifest['figures']+manifest['tables']
result={}
for item in items:
    for idx,t in enumerate(pages[start:],1):
        if norm(item) in norm(t):result[item]=idx;break
missing=set(items)-set(result)
if missing:raise RuntimeError(f'Missing index targets: {sorted(missing)}')
a.output.parent.mkdir(exist_ok=True,parents=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({'physical_pages':len(pages),'body_starts_physical':start+1,'entries':len(result),'map':str(a.output)},ensure_ascii=False))
