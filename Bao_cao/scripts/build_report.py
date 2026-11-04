"""Build the editable Vietnamese project report from BAO_CAO_DU_AN.md.

Use the bundled Python runtime. Cached index pages can be supplied after rendering.
Only report artifacts are created; application source is not modified.
"""
from pathlib import Path
import argparse
import json
import re
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.enum.section import WD_SECTION_START
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.style import WD_STYLE_TYPE
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT.parent
ap=argparse.ArgumentParser()
ap.add_argument('--page-map', type=Path)
ap.add_argument('--output', type=Path, default=ROOT/'Bao_cao_du_an_DemucsLite.docx')
args=ap.parse_args()
PAGES=json.loads(args.page_map.read_text()) if args.page_map else {}
text=(ROOT/'BAO_CAO_DU_AN.md').read_text()
front,body=text.split('<!-- BODY_START -->')
headings=[];figures=[];tables=[]
for line in body.splitlines():
    if line.startswith('# '):headings.append((1,line[2:]))
    elif line.startswith('## '):headings.append((2,line[3:]))
    elif line.startswith('![Hình '):figures.append(re.match(r'!\[(.+?)\]',line).group(1))
    elif re.match(r'^Bảng [\dA-Z]+\.\d+ ',line):tables.append(line)
bookmark_map={t:f'h_{i}' for i,(_,t) in enumerate(headings)}
bookmark_map.update({t:f'f_{i}' for i,t in enumerate(figures)})
bookmark_map.update({t:f't_{i}' for i,t in enumerate(tables)})
doc=Document()
doc.core_properties.title='Xây dựng ứng dụng Android tách nguồn âm nhạc bằng mô hình DemucsLite'
doc.core_properties.subject='Báo cáo dự án công nghệ thông tin'
doc.core_properties.author=''
doc.core_properties.keywords='DemucsLite, Android, FastAPI, MUSDB18-HQ'
doc.core_properties.comments=''

def font(st,size=13,bold=False,italic=False):
    st.font.name='Times New Roman';st.font.size=Pt(size);st.font.bold=bold;st.font.italic=italic;st.font.color.rgb=RGBColor(0,0,0)
    rpr=st.element.get_or_add_rPr()
    rf=rpr.find(qn('w:rFonts'))
    if rf is None:rf=OxmlElement('w:rFonts');rpr.append(rf)
    for key in ['ascii','hAnsi','eastAsia','cs']:rf.set(qn('w:'+key),'Times New Roman')
    for key in ['asciiTheme','hAnsiTheme','eastAsiaTheme','cstheme']:
        rf.attrib.pop(qn('w:'+key),None)

for st in doc.styles:
    if st.type in (WD_STYLE_TYPE.PARAGRAPH,WD_STYLE_TYPE.CHARACTER):
        font(st)
normal=doc.styles['Normal'];normal.paragraph_format.line_spacing=1.5
normal.paragraph_format.space_after=Pt(4);normal.paragraph_format.first_line_indent=Cm(1)
normal.paragraph_format.alignment=WD_ALIGN_PARAGRAPH.JUSTIFY
normal.paragraph_format.widow_control=True
for name,size in [('Heading 1',16),('Heading 2',14),('Heading 3',13)]:
    st=doc.styles[name];font(st,size,True)
    pf=st.paragraph_format;pf.first_line_indent=Cm(0);pf.space_before=Pt(12);pf.space_after=Pt(8)
    pf.line_spacing=1.2;pf.keep_with_next=True;pf.keep_together=True
    pf.alignment=WD_ALIGN_PARAGRAPH.LEFT
doc.styles['Heading 1'].paragraph_format.page_break_before=True
font(doc.styles['Title'],20,True)
doc.styles['Title'].paragraph_format.first_line_indent=Cm(0)
doc.styles['Title'].paragraph_format.alignment=WD_ALIGN_PARAGRAPH.CENTER
font(doc.styles['Caption'],11.5,False,True)
doc.styles['Caption'].paragraph_format.first_line_indent=Cm(0)
doc.styles['Caption'].paragraph_format.line_spacing=1.15
doc.styles['Caption'].paragraph_format.space_after=Pt(7)
doc.styles['Caption'].paragraph_format.alignment=WD_ALIGN_PARAGRAPH.CENTER
for name,size in [('TOC 1',12),('TOC 2',12),('Index Entry',11.5),('Small',11.5),('Code',10.5)]:
    st=doc.styles[name] if name in doc.styles else doc.styles.add_style(name,WD_STYLE_TYPE.PARAGRAPH)
    font(st,size,bold=name=='TOC 1')
    pf=st.paragraph_format;pf.first_line_indent=Cm(0);pf.line_spacing=1.1;pf.space_after=Pt(5)
    pf.keep_with_next=False;pf.alignment=WD_ALIGN_PARAGRAPH.LEFT
    if name=='TOC 2':pf.left_indent=Cm(.5)
    if name=='Code':pf.line_spacing=1.05;pf.space_after=Pt(3)
    if name=='TOC 1':pf.space_before=Pt(7)
for sec in doc.sections:
    sec.page_width=Cm(21);sec.page_height=Cm(29.7)
    sec.top_margin=Cm(2.5);sec.bottom_margin=Cm(2.5);sec.left_margin=Cm(3);sec.right_margin=Cm(2)
    sec.header_distance=Cm(1.1);sec.footer_distance=Cm(1.2)

def field(p,instruction,value='1'):
    r=p.add_run();b=OxmlElement('w:fldChar');b.set(qn('w:fldCharType'),'begin');r._r.append(b)
    r=p.add_run();ins=OxmlElement('w:instrText');ins.set(qn('xml:space'),'preserve');ins.text=' '+instruction+' ';r._r.append(ins)
    r=p.add_run();s=OxmlElement('w:fldChar');s.set(qn('w:fldCharType'),'separate');r._r.append(s)
    p.add_run(value)
    r=p.add_run();e=OxmlElement('w:fldChar');e.set(qn('w:fldCharType'),'end');r._r.append(e)

def section_page_numbers(sec,fmt='decimal',start=1):
    el=sec._sectPr.find(qn('w:pgNumType'))
    if el is None:el=OxmlElement('w:pgNumType');sec._sectPr.append(el)
    el.set(qn('w:fmt'),fmt);el.set(qn('w:start'),str(start))
    sec.footer.is_linked_to_previous=False
    p=sec.footer.paragraphs[0];p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.first_line_indent=Cm(0)
    field(p,'PAGE','1')
    for r in p.runs:r.font.size=Pt(11)

bookmark_id=0
def bookmark(p,name):
    global bookmark_id
    bookmark_id+=1
    b=OxmlElement('w:bookmarkStart');b.set(qn('w:id'),str(bookmark_id));b.set(qn('w:name'),name)
    e=OxmlElement('w:bookmarkEnd');e.set(qn('w:id'),str(bookmark_id))
    p._p.insert(0,b);p._p.append(e)

def link(p,label,target):
    h=OxmlElement('w:hyperlink');h.set(qn('w:anchor'),target);h.set(qn('w:history'),'1')
    r=OxmlElement('w:r');rpr=OxmlElement('w:rPr');rf=OxmlElement('w:rFonts')
    rf.set(qn('w:ascii'),'Times New Roman');rf.set(qn('w:hAnsi'),'Times New Roman');rpr.append(rf)
    color=OxmlElement('w:color');color.set(qn('w:val'),'000000');rpr.append(color);r.append(rpr)
    t=OxmlElement('w:t');t.text=label;r.append(t);h.append(r);p._p.append(h)

def plain_title(t):
    p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.first_line_indent=Cm(0)
    p.paragraph_format.space_after=Pt(16);p.paragraph_format.keep_with_next=True
    r=p.add_run(t);r.bold=True;r.font.size=Pt(16)
    return p

def prose(t,style=None):
    p=doc.add_paragraph(style=style)
    # Preserve code tokens without visible Markdown delimiters.
    chunks=re.split(r'(`[^`]+`)',t)
    for s in chunks:
        r=p.add_run(s[1:-1] if s.startswith('`') else s)
        if s.startswith('`'):r.font.size=Pt(11.5)
    return p

def index(title,entries,toc=False):
    plain_title(title)
    rows=[]
    for lev,t in entries:
        p=doc.add_paragraph(style=('TOC 1' if lev==1 else 'TOC 2') if toc else 'Index Entry')
        p.paragraph_format.tab_stops.add_tab_stop(Cm(15.8),WD_TAB_ALIGNMENT.RIGHT,WD_TAB_LEADER.DOTS)
        p.paragraph_format.keep_together=True
        if toc and t.startswith('3.5 '):p.paragraph_format.page_break_before=True
        link(p,t,bookmark_map[t]);p.add_run('\t')
        field(p,'PAGEREF '+bookmark_map[t]+' \\h',str(PAGES.get(t,'1')))
        rows.append(p)
    if toc and rows:
        # A real TOC field with a complete cached representation for headless readers.
        elems=[]
        for kind,val in [('fldChar','begin'),('instrText',' TOC \\o "1-2" \\h \\z \\u '),('fldChar','separate')]:
            r=OxmlElement('w:r');el=OxmlElement('w:'+kind)
            if kind=='fldChar':el.set(qn('w:fldCharType'),val)
            else:el.set(qn('xml:space'),'preserve');el.text=val
            r.append(el);elems.append(r)
        pos=1 if rows[0]._p.pPr is not None else 0
        for r in reversed(elems):rows[0]._p.insert(pos,r)
        r=OxmlElement('w:r');el=OxmlElement('w:fldChar');el.set(qn('w:fldCharType'),'end');r.append(el);rows[-1]._p.append(r)

def table(rows):
    n=len(rows[0]);t=doc.add_table(rows=1,cols=n);t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
    widths={2:[5.2,10.8],3:[3.3,5.2,7.5],4:[6.1,3.3,3.3,3.3],5:[4.4,2.9,2.9,2.9,2.9]}.get(n,[16/n]*n)
    if n==4 and rows[0][0]=='Nhóm':widths=[3.3,6.6,3.05,3.05]
    if n==4 and rows[0][0].startswith('Mô hình'):widths=[5.3,3.6,3.6,3.5]
    for c,w in zip(t.columns,widths):c.width=Cm(w)
    for idx,vals in enumerate(rows):
        row=t.rows[0] if idx==0 else t.add_row()
        pr=row._tr.get_or_add_trPr();ns=OxmlElement('w:cantSplit');pr.append(ns)
        if idx==0:
            rep=OxmlElement('w:tblHeader');pr.append(rep)
        for j,(cell,val,w) in enumerate(zip(row.cells,vals,widths)):
            cell.width=Cm(w);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            cp=cell._tc.get_or_add_tcPr()
            margins=OxmlElement('w:tcMar')
            for edge in ['top','left','bottom','right']:
                el=OxmlElement('w:'+edge);el.set(qn('w:w'),'75' if edge in ['top','bottom'] else '100');el.set(qn('w:type'),'dxa');margins.append(el)
            cp.append(margins)
            shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'344C61' if idx==0 else ('F3F5F7' if idx%2==0 else 'FFFFFF'));cp.append(shade)
            borders=OxmlElement('w:tcBorders')
            for side in ['top','left','bottom','right']:
                el=OxmlElement('w:'+side);el.set(qn('w:val'),'single');el.set(qn('w:sz'),'4');el.set(qn('w:color'),'D9D9D9');borders.append(el)
            cp.append(borders)
            p=cell.paragraphs[0];p.paragraph_format.first_line_indent=Cm(0);p.paragraph_format.line_spacing=1.12
            p.paragraph_format.space_before=Pt(1);p.paragraph_format.space_after=Pt(1)
            p.paragraph_format.keep_with_next=(idx<3 or idx==len(rows)-2)
            numeric=bool(re.fullmatch(r'[−\-\d.,% ]+',val))
            p.alignment=WD_ALIGN_PARAGRAPH.CENTER if numeric else WD_ALIGN_PARAGRAPH.LEFT
            r=p.add_run(val);r.font.size=Pt(11.5);r.bold=idx==0
            if idx==0:r.font.color.rgb=RGBColor(255,255,255)
    p=doc.add_paragraph();p.paragraph_format.space_after=Pt(0);p.paragraph_format.space_before=Pt(0);p.paragraph_format.line_spacing=1
    p.add_run().font.size=Pt(2)
    return t

# Cover: personal information intentionally blank.
for t in ['TRƯỜNG ................................................................','KHOA .....................................................................']:
    p=doc.add_paragraph(t);p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.first_line_indent=Cm(0)
    p.paragraph_format.space_after=Pt(5)
    for r in p.runs:r.bold=True;r.font.size=Pt(14)
p=doc.add_paragraph('BÁO CÁO DỰ ÁN',style='Title');p.paragraph_format.space_before=Pt(62);p.paragraph_format.space_after=Pt(28)
p=doc.add_paragraph('XÂY DỰNG ỨNG DỤNG ANDROID\nTÁCH NGUỒN ÂM NHẠC\nBẰNG MÔ HÌNH DEMUCSLITE',style='Title')
p.paragraph_format.line_spacing=1.35;p.paragraph_format.space_before=Pt(18);p.paragraph_format.space_after=Pt(48)
for label in ['Sinh viên thực hiện','Mã số sinh viên','Lớp','Giảng viên hướng dẫn']:
    p=doc.add_paragraph(label+': ................................................................')
    p.paragraph_format.first_line_indent=Cm(0);p.paragraph_format.left_indent=Cm(1.15);p.paragraph_format.space_after=Pt(10)
p=doc.add_paragraph('Tháng 11 năm 2026');p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.first_line_indent=Cm(0);p.paragraph_format.space_before=Pt(45)

sec=doc.add_section(WD_SECTION_START.NEW_PAGE);section_page_numbers(sec,'lowerRoman',1)
plain_title('TÓM TẮT')
for paragraph in front.split('## Tóm tắt',1)[1].strip().split('\n\n'):prose(paragraph)
doc.add_page_break();index('MỤC LỤC',headings,True)
doc.add_page_break();index('DANH MỤC HÌNH',[(1,t) for t in figures])
doc.add_page_break();index('DANH MỤC BẢNG',[(1,t) for t in tables])
doc.add_page_break();plain_title('DANH MỤC TỪ VIẾT TẮT')
table([['Viết tắt','Diễn giải'],['API','Application Programming Interface - giao diện lập trình ứng dụng'],
       ['AMP','Automatic Mixed Precision - tính toán hỗn hợp độ chính xác'],['BiLSTM','Bidirectional Long Short-Term Memory - LSTM hai chiều'],
       ['CNN','Convolutional Neural Network - mạng nơ-ron tích chập'],['EMA','Exponential Moving Average - trung bình trượt hàm mũ'],
       ['GLU','Gated Linear Unit - đơn vị tuyến tính có cổng'],['GPU','Graphics Processing Unit - bộ xử lý đồ họa'],
       ['MSS','Music Source Separation - tách nguồn âm nhạc'],['PCM','Pulse-Code Modulation - biểu diễn âm thanh mã xung'],
       ['RAM','Random Access Memory - bộ nhớ truy cập ngẫu nhiên'],['RTF','Real-Time Factor - thời gian xử lý / thời lượng âm thanh'],
       ['SDR','Signal-to-Distortion Ratio - tỷ số tín hiệu trên méo'],['SI-SDR','Scale-Invariant SDR - SDR bất biến theo tỷ lệ'],
       ['SNR','Signal-to-Noise Ratio - tỷ số tín hiệu trên nhiễu/sai số'],['STFT','Short-Time Fourier Transform - biến đổi Fourier ngắn hạn'],
       ['WAV','Waveform Audio File Format - định dạng tệp âm thanh']])

sec=doc.add_section(WD_SECTION_START.NEW_PAGE);section_page_numbers(sec,'decimal',1)
lines=body.strip().splitlines();i=0;first=True;in_refs=False
while i<len(lines):
    s=lines[i].strip()
    if not s:i+=1;continue
    if s.startswith('# '):
        h=s[2:];p=doc.add_paragraph(h,style='Heading 1')
        if first:p.paragraph_format.page_break_before=False;first=False
        p.alignment=WD_ALIGN_PARAGRAPH.CENTER
        bookmark(p,bookmark_map[h]);in_refs=h=='TÀI LIỆU THAM KHẢO';i+=1;continue
    if s.startswith('## '):
        h=s[3:];p=doc.add_paragraph(h,style='Heading 2');bookmark(p,bookmark_map[h]);i+=1;continue
    if s.startswith('!['):
        m=re.match(r'!\[(.+?)\]\((.+?)\)',s);caption,path=m.groups();img=ROOT/path
        p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.first_line_indent=Cm(0)
        p.paragraph_format.line_spacing=1;p.paragraph_format.space_before=Pt(5);p.paragraph_format.space_after=Pt(0)
        p.paragraph_format.keep_with_next=True
        im=Image.open(img);iw,ih=im.size;w=16;h=w*ih/iw
        if caption.startswith('Công thức'):maxh=2.4
        elif 'app_ui' in path:maxh=14
        else:maxh=13.8
        if h>maxh:w*=maxh/h
        shape=p.add_run().add_picture(str(img),width=Cm(w));shape._inline.docPr.set('descr',caption)
        c=doc.add_paragraph(caption,style='Caption')
        if caption in bookmark_map:bookmark(c,bookmark_map[caption])
        i+=1;continue
    if s.startswith('|'):
        rows=[]
        while i<len(lines) and lines[i].strip().startswith('|'):
            raw=[v.strip() for v in lines[i].strip().strip('|').split('|')]
            if not all(re.fullmatch(r':?-+:?',v.replace(' ','')) for v in raw):rows.append(raw)
            i+=1
        table(rows);continue
    if re.match(r'^Bảng [\dA-Z]+\.\d+ ',s):
        p=doc.add_paragraph(s,style='Caption');p.paragraph_format.keep_with_next=True;bookmark(p,bookmark_map[s]);i+=1;continue
    if s.startswith('```'):
        i+=1
        while i<len(lines) and not lines[i].startswith('```'):
            cmd=lines[i]
            # Break long command options at spaces; visible continuation marker for shell.
            if len(cmd)>90 and cmd.startswith('python '):
                parts=re.split(r' (?=--)',cmd)
                for k,x in enumerate(parts):
                    p=prose(('    ' if k else '')+x+(' \\' if k<len(parts)-1 else ''),'Code')
                    p.paragraph_format.keep_with_next=k<len(parts)-1
            else:prose(cmd,'Code')
            i+=1
        i+=1;continue
    p=prose(s,'Small' if in_refs or s.startswith('Nguồn:') or s.startswith('SDR* là') else None)
    if in_refs:
        p.paragraph_format.space_after=Pt(5);p.paragraph_format.keep_together=True
        for r in p.runs:r.font.size=Pt(11)
    i+=1

# Language and field refresh hints.
for style in ['Normal','Heading 1','Heading 2','Caption']:
    rp=doc.styles[style].element.get_or_add_rPr();lang=OxmlElement('w:lang');lang.set(qn('w:val'),'vi-VN');rp.append(lang)
settings=doc.settings.element
upd=OxmlElement('w:updateFields');upd.set(qn('w:val'),'true');settings.append(upd)
# The bundled base template can carry a blue border in Title; remove all
# paragraph borders from styles and body so the academic cover stays plain.
for root in [doc.styles.element,doc.element]:
    for border in list(root.iter(qn('w:pBdr'))):border.getparent().remove(border)
args.output.parent.mkdir(parents=True,exist_ok=True);doc.save(args.output)
(ROOT/'data/index_manifest.json').write_text(json.dumps({'headings':headings,'figures':figures,'tables':tables,'bookmarks':bookmark_map},ensure_ascii=False,indent=2))
print(args.output)
print(f'Headings: {len(headings)}; figures: {len(figures)}; tables: {len(tables)}')
