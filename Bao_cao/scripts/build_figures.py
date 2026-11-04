"""Rebuild report diagrams and charts from explicit, cited data.

Requires matplotlib and Pillow. No application files or model weights are edited.
"""
from pathlib import Path
import csv
import json
import math
import shutil
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, Ellipse, Circle, FancyArrowPatch
from matplotlib import font_manager
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'figures'
DATA = ROOT / 'data'
OUT.mkdir(exist_ok=True)
DATA.mkdir(exist_ok=True)
font_path = Path('/System/Library/Fonts/Supplemental/Times New Roman.ttf')
if font_path.exists():
    for p in font_path.parent.glob('Times New Roman*.ttf'):
        font_manager.fontManager.addfont(str(p))
plt.rcParams.update({'font.family': 'Times New Roman', 'font.size': 13,
                     'axes.spines.top': False, 'axes.spines.right': False,
                     'svg.fonttype': 'none', 'mathtext.fontset': 'stix'})
INK, BLUE, PALE, GRAY = '#172432', '#365a7a', '#edf2f6', '#6c7782'

def canvas(w=7.4, h=5):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, w); ax.set_ylim(0, h); ax.axis('off')
    fig.subplots_adjust(0.015, 0.015, 0.985, 0.985)
    return fig, ax

def box(ax, x, y, w, h, text, size=13, fill=PALE, rounded=True, dashed=False):
    kw=dict(edgecolor=BLUE, facecolor=fill, linewidth=1.15, linestyle='--' if dashed else '-')
    patch=FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.02,rounding_size=0.06',**kw) if rounded else Rectangle((x,y),w,h,**kw)
    ax.add_patch(patch); ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=size,color=INK,linespacing=1.3)

def arrow(ax, p, q, text='', dashed=False, rad=0, size=11.5, offset=(0,0.12), head=True):
    ar=FancyArrowPatch(p,q,arrowstyle='-|>' if head else '-',mutation_scale=11,
                      linewidth=1.0, color=GRAY,linestyle='--' if dashed else '-',
                      connectionstyle=f'arc3,rad={rad}',shrinkA=2,shrinkB=2)
    ax.add_patch(ar)
    if text: ax.text((p[0]+q[0])/2+offset[0],(p[1]+q[1])/2+offset[1],text,
                     fontsize=size,ha='center',va='center',color=INK,
                     bbox=dict(facecolor='white',edgecolor='none',pad=1.5))

def save(fig,name):
    fig.savefig(OUT/f'{name}.png',dpi=230,facecolor='white')
    fig.savefig(OUT/f'{name}.svg',facecolor='white')
    plt.close(fig)

# Use case: actual UML actor, boundary, ellipses, include dependencies.
fig,ax=canvas(7.4,5.5)
ax.add_patch(Rectangle((1.65,.18),5.55,5.12,fill=False,edgecolor=BLUE,lw=1.2))
ax.text(4.4,5.07,'Hệ thống DemucsLite',ha='center',fontweight='bold',fontsize=15)
ax.add_patch(Circle((.63,3.0),.16,fill=False,ec=INK,lw=1.3))
ax.plot([.63,.63],[2.84,2.3],c=INK); ax.plot([.28,.98],[2.65,2.65],c=INK)
ax.plot([.63,.32],[2.3,1.92],c=INK);ax.plot([.63,.94],[2.3,1.92],c=INK)
ax.text(.63,1.7,'Người dùng',ha='center',fontsize=13)
cases=[(3.25,4.25,2.5,.64,'Tách nhạc từ tệp'),(3.25,3.30,2.5,.64,'Theo dõi tác vụ'),
       (3.25,2.35,2.5,.72,'Nghe và điều chỉnh\nâm lượng / solo / mute'),(3.25,1.4,2.5,.64,'Lưu WAV kết quả'),
       (3.05,.57,2.1,.54,'Cấu hình server'),(5.65,.57,2.1,.54,'Chạy demo offline')]
for x,y,w,h,t in cases:
    ax.add_patch(Ellipse((x,y),w,h,fc=PALE,ec=BLUE,lw=1.1)); ax.text(x,y,t,ha='center',va='center',fontsize=12.5)
    if t == 'Chạy demo offline':
        ax.plot([.99,1.36,1.36,4.6],[2.65,2.65,.26,.26],color=GRAY,lw=1)
        arrow(ax,(4.6,.26),(4.72,.43),head=False)
    else:
        arrow(ax,(.99,2.65),(x-w/2,y),head=False)
for x,y,t in [(6.03,4.55,'Kiểm tra tệp'),(6.03,3.55,'Phân tách\nbằng mô hình')]:
    ax.add_patch(Ellipse((x,y),1.9,.65,fc='white',ec=BLUE,lw=1.1)); ax.text(x,y,t,ha='center',va='center',fontsize=12)
arrow(ax,(4.5,4.35),(5.08,4.5),'«include»',dashed=True,size=10,offset=(0,.21))
arrow(ax,(4.5,4.10),(5.1,3.65),'«include»',dashed=True,size=10,offset=(.12,-.17))
ax.text(5.75,2.1,'Nghe / lưu yêu cầu\ncác stem sẵn sàng',ha='center',va='center',fontsize=12,color=GRAY)
save(fig,'usecase')

fig,ax=canvas(7.4,5.4)
ax.add_patch(Rectangle((.12,2.0),2.05,3.12,fill=False,ec=BLUE,lw=1.1))
ax.text(1.15,4.87,'Thiết bị Android',ha='center',fontweight='bold',fontsize=14)
box(ax,.28,3.55,1.72,.92,'Java + XML\nStudioSession')
box(ax,.28,2.25,1.72,.9,'OkHttp\nCache + Player')
arrow(ax,(1.15,3.55),(1.15,3.15))
ax.add_patch(Rectangle((3.03,1.55),4.2,3.57,fill=False,ec=BLUE,lw=1.1))
ax.text(5.13,4.87,'Máy chủ • một tiến trình / worker',ha='center',fontweight='bold',fontsize=13.5)
box(ax,3.22,3.7,1.68,.75,'FastAPI\nAPI tác vụ')
box(ax,5.22,3.7,1.8,.75,'JobStore\nDictionary RAM')
box(ax,3.22,2.05,3.80,1.02,'BackgroundTasks + khóa suy luận\nDecode → V2 → overlap-add → WAV')
arrow(ax,(2.02,4.05),(3.22,4.05),'HTTP',offset=(0,.19))
arrow(ax,(4.9,4.08),(5.22,4.08))
arrow(ax,(4.05,3.7),(4.05,3.07))
arrow(ax,(6.12,3.07),(6.12,3.7),'trạng thái',offset=(.48,0),size=11)
box(ax,.28,.2,2.35,.84,'Checkpoint V2\nbest_model.pth')
box(ax,3.23,.2,1.77,.84,'Storage local\n/files/...')
box(ax,5.34,.2,1.73,.84,'S3 / GCS\nmở rộng',dashed=True,fill='white')
arrow(ax,(2.63,.75),(3.32,2.05),'nạp model',offset=(-.2,.1),size=11)
arrow(ax,(4.1,2.05),(4.1,1.04))
arrow(ax,(6.2,2.05),(6.2,1.04),dashed=True)
ax.text(.25,1.48,'Upload • polling • tải WAV',fontsize=11,color=GRAY)
save(fig,'architecture')

fig,ax=canvas(8,6.7)
xs=[.65,2.12,3.85,5.7,7.25]
labels=['Người dùng','Android','FastAPI\nJobStore','Pipeline\nModel','Storage']
for x,t in zip(xs,labels):
    box(ax,x-.59,6.0,1.18,.6,t,size=11.5)
    ax.plot([x,x],[.10,6.0],ls='--',lw=.8,color='#a5adb4')
steps=[(0,1,5.55,'Chọn tệp và bắt đầu',False),
       (1,2,5.1,'POST /separate + file',False),
       (2,1,4.65,'job_id, pending',True),
       (2,3,4.2,'Giao tác vụ nền',False),
       (1,2,3.75,'GET /status/{id}',False),
       (2,1,3.3,'pending / processing',True),
       (3,4,2.5,'Ghi 4 WAV',False),
       (3,2,2.05,'Cập nhật done và URLs',True),
       (2,1,1.55,'Lần poll sau: done + URLs',True),
       (1,4,1.0,'GET lần lượt 4 WAV',False),
       (4,1,.59,'Nội dung WAV',True),
       (1,0,.18,'Mở mixer',True)]
for a,b,y,t,d in steps: arrow(ax,(xs[a],y),(xs[b],y),t,dashed=d,size=11.4,offset=(0,.17))
ax.add_patch(Rectangle((1.4,3.0),3.1,1.0,fc='none',ec=BLUE,lw=1))
ax.text(1.44,3.04,'Lặp 1,8 giây đến done / failed',fontsize=10.5,color=BLUE)
ax.text(5.7,3.27,'Decode\nOverlap-add\nXuất PCM16',ha='center',va='center',fontsize=11.3,
        bbox=dict(fc=PALE,ec=BLUE,pad=4))
save(fig,'sequence')

fig,ax=canvas(7.4,3.7)
ax.add_patch(Circle((.35,2.45),.09,color=INK))
box(ax,.9,2.1,1.65,.7,'pending');box(ax,3.15,2.1,1.8,.7,'processing')
box(ax,5.65,2.1,1.45,.7,'done');box(ax,5.65,.63,1.45,.7,'failed',fill='#f7eeee')
arrow(ax,(.45,2.45),(.9,2.45));arrow(ax,(2.55,2.45),(3.15,2.45),'nhận khóa',size=10.5,offset=(0,.3))
arrow(ax,(4.95,2.45),(5.65,2.45),'thành công',size=10.5,offset=(0,.3))
arrow(ax,(4.95,2.15),(5.65,.99),'lỗi',size=11,offset=(.25,0))
ax.text(3.1,.42,'Server chưa có trạng thái canceled.\nRestart tiến trình làm mất trạng thái trong RAM.',ha='center',va='center',fontsize=12,color=GRAY)
save(fig,'job_state')

def classbox(ax,x,y,w,h,title,body,size=10.7):
    ax.add_patch(Rectangle((x,y),w,h,fc='white',ec=BLUE,lw=1.05))
    ax.add_patch(Rectangle((x,y+h-.52),w,.52,fc=PALE,ec=BLUE,lw=1.05))
    ax.text(x+w/2,y+h-.26,title,ha='center',va='center',fontsize=size+1,fontweight='bold')
    ax.text(x+.12,y+h-.65,body,ha='left',va='top',fontsize=size,linespacing=1.42)
fig,ax=canvas(7.8,6.2)
classbox(ax,.12,4.15,2.15,1.8,'MainActivity','session: StudioSession\nplayers: MediaPlayer[4]\nplay() / pause()\nexportTracks()')
classbox(ax,2.85,4.15,2.15,1.8,'StudioSession','phase / stems / serverUrl\nstart() / cancel()\nselect() / setServer()\nAndroidViewModel')
classbox(ax,5.6,4.15,2.05,1.8,'Stem','key / file / envelope\nvolume / solo / muted',size=10.5)
arrow(ax,(2.27,5.1),(2.85,5.1));arrow(ax,(5,5.1),(5.6,5.1),'4',offset=(0,.17),size=11)
classbox(ax,.12,1.88,2.15,1.6,'«module» main','separate_audio()\nget_status()\nhealth_check()')
classbox(ax,2.85,1.88,2.15,1.6,'«module» pipeline','decode_audio()\nrun_separation_pipeline()\nexport_pcm_stems()',size=9.7)
classbox(ax,5.6,1.88,2.05,1.6,'JobStore','_jobs: dict\ncreate() / get()\nupdate()')
arrow(ax,(2.27,2.7),(2.85,2.7));arrow(ax,(5,2.7),(5.6,2.7))
arrow(ax,(3.1,4.15),(1.6,3.48),'HTTP',dashed=True,size=10.5,offset=(0,.03))
box(ax,.12,.2,2.15,.95,'«module» model_loader\nNạp DemucsLiteV2',size=11.5)
box(ax,2.85,.2,2.15,.95,'«module» cloud_storage\nLưu tệp và trả URL',size=11.3)
box(ax,5.6,.2,2.05,.95,'Job: bản ghi dict\nstatus / urls / error',size=11.5)
arrow(ax,(3.1,1.88),(2.02,1.15),dashed=True);arrow(ax,(3.9,1.88),(3.9,1.15),dashed=True)
arrow(ax,(6.62,1.88),(6.62,1.15),'lưu nhiều job',size=10,offset=(.47,0))
save(fig,'classes')

fig,ax=canvas(7.4,5.85)
box(ax,.2,4.75,2.08,.83,'Waveform [B,2,T]\nChuẩn hóa + padding',size=12)
box(ax,5.15,4.75,2.05,.83,'Cắt và hoàn nguyên\n[B,4,2,T]',size=12)
for i,(c,y) in enumerate(zip([32,64,128,256,512],[3.97,3.23,2.49,1.75,1.01])):
    box(ax,.5,y,1.55,.50,f'Encoder {i+1} • {c}',size=12)
    out=[8,32,64,128,256][i]
    box(ax,5.38,y,1.55,.50,f'Decoder • {out}',size=12)
    arrow(ax,(2.05,y+.25),(5.38,y+.25),'skip +',dashed=True,size=10.5,offset=(0,.12))
    if i==0:
        arrow(ax,(1.27,4.75),(1.27,4.47));arrow(ax,(6.16,4.47),(6.16,4.75))
    else:
        arrow(ax,(1.27,y+.74),(1.27,y+.5));arrow(ax,(6.16,y+.5),(6.16,y+.74))
box(ax,2.55,.15,2.25,.64,'BiLSTM 2 lớp + Linear\n256 ẩn mỗi chiều',size=12)
arrow(ax,(1.27,1.01),(2.55,.47));arrow(ax,(4.8,.47),(6.16,1.01))
ax.text(3.7,4.9,'Kernel 8 • stride 4\n10.309.704 tham số',ha='center',fontsize=12,color=GRAY)
ax.text(3.7,1.6,'DConv ở 3 mức sâu',ha='center',fontsize=11.5,color=GRAY)
save(fig,'model')

fig,ax=canvas(7.4,5.65)
box(ax,1.9,4.75,3.6,.65,'MUSDB18-HQ → audit → manifest',size=13)
arrow(ax,(3.7,4.75),(3.7,4.35))
box(ax,.3,3.55,2.2,.8,'86 bài train\nCrop + augmentation',size=12.5)
box(ax,2.65,3.55,2.1,.8,'14 bài validation\nCrop cố định',size=12.5)
box(ax,5.12,3.55,2,.8,'50 bài test\nGiữ riêng',size=12.5)
arrow(ax,(2.35,4.75),(1.4,4.35));arrow(ax,(5.05,4.75),(6.1,4.35))
box(ax,.3,2.05,2.2,.85,'Forward → loss\nBackward → AdamW',size=12.5)
box(ax,2.65,2.05,2.1,.85,'So raw và EMA\nValidation SNR',size=12.5)
arrow(ax,(1.4,3.55),(1.4,2.9));arrow(ax,(3.7,3.55),(3.7,2.9));arrow(ax,(2.5,2.48),(2.65,2.48))
box(ax,1.15,.48,3.7,.88,'last.pth / best.pth\nXuất best_model.pth khi cải thiện',size=12.5)
arrow(ax,(1.4,2.05),(1.95,1.36));arrow(ax,(3.7,2.05),(3.7,1.36))
box(ax,5.12,.48,2,1.02,'Cố định model\nFull-track test\nSNR / SI-SDR',size=12)
arrow(ax,(6.12,3.55),(6.12,1.5));arrow(ax,(4.85,.94),(5.12,.94))
ax.text(3.68,1.65,'Scheduler / dừng sớm',ha='center',fontsize=11,color=GRAY)
save(fig,'training')

# Data extraction retains the metric's original name and provenance.
week=[('Vocals',1.854,2.329,31.393,-11.089),('Drums',1.945,1.740,42.673,-20.083),('Bass',.765,1.828,38.165,-8.554)]
with (DATA/'ket_qua_tuan4.csv').open('w',newline='',encoding='utf-8-sig') as f:
    wr=csv.writer(f);wr.writerow(['source','reported_sdr_mean_db','reported_sdr_median_db','phase_mae_deg','reported_leakage_db','metric_note','provenance'])
    for row in week: wr.writerow([*row,'Historical SDR label; waveform SNR definition; not confirmed BSS Eval','Progress PDF p14; reported test 50 tracks; not remeasured'])
fig,ax=plt.subplots(figsize=(7.4,4.3))
x=list(range(3));w=.33
b1=ax.bar([v-w/2 for v in x],[r[1] for r in week],w,label='Trung bình',color=BLUE)
b2=ax.bar([v+w/2 for v in x],[r[2] for r in week],w,label='Trung vị',color='#a6bacb',hatch='//',edgecolor=BLUE,lw=.6)
for bars in [b1,b2]:
    ax.bar_label(bars,labels=[f'{b.get_height():.3f}'.replace('.',',') for b in bars],padding=4,fontsize=12)
ax.set_xticks(x,[r[0] for r in week]);ax.set_ylabel('SDR* theo báo cáo (dB)')
ax.set_ylim(0,2.8);ax.legend(frameon=False,ncol=2,loc='upper center')
ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
fig.subplots_adjust(left=.12,right=.98,top=.93,bottom=.22)
fig.text(.5,.07,'* Công thức SNR waveform; số trích báo cáo tuần 4, trang 14.\n50 bài test được báo; chưa có số Other. Không phải điểm test V2.',ha='center',fontsize=11)
save(fig,'week4_sdr')

lit={'Spleeter MWF':[6.86,6.71,5.51,4.55],'Open-Unmix':[6.32,5.73,5.23,4.02],'Demucs':[7.05,7.08,6.70,4.47]}
with (DATA/'sdr_nghien_cuu.csv').open('w',newline='',encoding='utf-8-sig') as f:
    wr=csv.writer(f);wr.writerow(['model','vocals_db','drums_db','bass_db','other_db','provenance'])
    for k,v in lit.items():wr.writerow([k,*v,'Spleeter paper 2020 comparison table; https://github.com/deezer/spleeter/blob/master/paper.md'])
fig,ax=plt.subplots(figsize=(7.4,4.5)); w=.24
for i,(name,vals) in enumerate(lit.items()):
    bars=ax.bar([j+(i-1)*w for j in range(4)],vals,w,label=name,color=[BLUE,'#a8b8c6','#d8dfe5'][i],edgecolor=BLUE,lw=.4,hatch=['','//','..'][i])
    ax.bar_label(bars,labels=[f'{v:.2f}'.replace('.',',') for v in vals],padding=3,fontsize=10.3)
ax.set_xticks(range(4),['Vocals','Drums','Bass','Other']);ax.set_ylabel('SDR công bố (dB)');ax.set_ylim(0,8.6)
ax.legend(frameon=False,ncol=3,loc='upper center',fontsize=11.5);ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
fig.subplots_adjust(left=.10,right=.99,top=.97,bottom=.21)
fig.text(.5,.06,'Nguồn: bảng đối sánh trong công trình Spleeter (2020).\nSố tham khảo từ nghiên cứu; không phải benchmark chạy trong dự án.',ha='center',fontsize=11)
save(fig,'literature_sdr')

# Equations rendered as high resolution, correctly typeset math.
eqs={
'eq_mixture':(r'$x_c(t)\approx\sum_{k=1}^{4}s_{k,c}(t),\qquad \hat{\mathbf{s}}=f_{\theta}(\mathbf{x})$',.58),
'eq_loss':(r'$\mathcal{L}=\mathcal{L}_{\mathrm{src}}+0.1\mathcal{L}_{\mathrm{mix}}+0.05\mathcal{L}_{\mathrm{STFT}}$'+'\n'+r'$\qquad +\;0.01\left(\mathcal{L}_{\mathrm{SI}}+\mathcal{L}_{\mathrm{sil}}\right)$',.95),
'eq_snr':(r'$\mathrm{SNR}=10\log_{10}\frac{\mathrm{mean}(s^2)+\varepsilon}{\mathrm{mean}((s-\hat{s})^2)+\varepsilon}$',.75),
'eq_sisdr':(r'$\alpha=\frac{\langle\hat{s},s\rangle}{\Vert s\Vert^2},\qquad\mathrm{SI\!\! -\!\! SDR}=10\log_{10}\frac{\Vert\alpha s\Vert^2}{\Vert\hat{s}-\alpha s\Vert^2}$',.75),
'eq_ola':(r'$\hat{s}(t)=\frac{\sum_m w(t-mH)\,\hat{s}_m(t-mH)}{\sum_m w(t-mH)+\varepsilon}$',.75)
}
for name,(eq,h) in eqs.items():
    fig,ax=canvas(7.4,h);ax.text(3.7,h/2,eq,ha='center',va='center',fontsize=17);save(fig,name)

# Existing UI screenshots, assembled without changing the screens themselves.
project=ROOT.parent
files=[project/'reports/ui-preview/02-upload.png',project/'reports/ui-preview/04-mixer.png']
imgs=[Image.open(p).convert('RGB') for p in files]
height=1500
imgs=[im.resize((round(im.width*height/im.height),height)) for im in imgs]
gap=80
sheet=Image.new('RGB',(sum(im.width for im in imgs)+gap,height),'white')
x=0
for im in imgs:sheet.paste(im,(x,0));x+=im.width+gap
sheet.save(OUT/'app_ui.png')
print(f'Created figures in {OUT}')
