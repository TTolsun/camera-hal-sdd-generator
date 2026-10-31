"""Record visible narrative and evidence inventories from the normal renderer."""
import argparse
import json
from html.parser import HTMLParser
from pathlib import Path
from sdd.config import load, section_output
from sdd.facts.model import KnowledgeModel
from sdd import glossary
from sdd.export_site import _prepare_page_body, source_link_template
from sdd.site_markdown import _render
from sdd.runtime_evidence import sha256

class Window(HTMLParser):
    def __init__(self,fragment=False):
        super().__init__();self.inside=fragment;self.depth=0;self.text=[];self.links=[];self.folded=[];self.diagram=False;self.diagrams=[];self.lists=[];self.ordered=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='article':self.inside=True
        if not self.inside:return
        if tag=='details':
            self.depth+=1;self.folded.append(dict(attrs))
        if tag=='a' and attrs.get('href'):self.links.append(attrs['href'])
        if tag=='pre' and attrs.get('class')=='mermaid':self.diagram=True
        if not self.depth and tag in ['ol','ul']:
            record=dict(start=int(attrs.get('start','1')),items=0) if tag=='ol' else None
            if record is not None:self.ordered.append(record)
            self.lists.append(record)
        if not self.depth and tag=='li' and self.lists and self.lists[-1] is not None:
            record=self.lists[-1];record['items']+=1
            self.text.append('\n'+str(record['start']+record['items']-1)+'. ')
        if not self.depth and tag in ['p','li','h2','h3','br']:self.text.append('\n')
    def handle_endtag(self,tag):
        if tag=='details' and self.inside:self.depth-=1
        if tag=='pre':self.diagram=False
        if self.inside and not self.depth and tag in ['ol','ul'] and self.lists:self.lists.pop()
        if tag=='article':self.inside=False
    def handle_data(self,text):
        if self.inside and self.diagram:self.diagrams.append(text)
        elif self.inside and not self.depth:self.text.append(text)

parser=argparse.ArgumentParser()
parser.add_argument('--out',type=Path,required=True)
parser.add_argument('--site',type=Path)
args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=False)
root=Path(__file__).resolve().parents[4];work=root/'build/issue211-reader'
rel='official-cam-validation.md'
if args.site:
    inputs={lang:args.site/('en/' if lang=='en' else '')/rel.replace('.md','.html') for lang in ['ko','en']}
else:
    cfg=load(work/'publication.yaml');model=KnowledgeModel.load(cfg.facts_path)
    sections={section_output(s):s for s in cfg.sections()}
    texts={name:(cfg.sdd_dir/name).read_text(encoding='utf-8') for name in sections if (cfg.sdd_dir/name).is_file()}
    title,meta,body,_,_=_prepare_page_body(cfg,rel,texts,sections,glossary.load(cfg),model)
    rendered,_,_=_render(body,rel,set(texts),model,str(cfg.site.source_url),meta['source_commit'],source_link_template(cfg.site))
    path=args.out/'fragment.html';path.write_text(rendered,encoding='utf-8')
    inputs={'ko':path}
inventory={}
for lang,path in inputs.items():
    p=Window(fragment=not args.site);p.feed(path.read_text(encoding='utf-8'))
    text=''.join(p.text)
    if any(marker in text for marker in ['434','449','464','callback-entry','cancelled_callbacks','"schema"']):
        raise ValueError('Raw observation details leaked into visible prose')
    (args.out/(lang+'.txt')).write_text(text,encoding='utf-8')
    inventory[lang]=dict(html_sha256=sha256(path),characters=len(text),links=p.links,folded=p.folded,diagram_sources=p.diagrams,ordered_lists=p.ordered,
                         scope='All visible article narrative; all details contents excluded here and inventoried, not removed from the site.')
(args.out/'inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print({lang:row['characters'] for lang,row in inventory.items()})
