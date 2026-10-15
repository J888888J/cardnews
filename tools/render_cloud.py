import glob, json, sys
from PIL import Image, ImageDraw, ImageFont
import numpy as np
S="/tmp/claude-0/-home-user-cardnews/9eafd48f-0477-53cd-9868-cd535f179bcb/scratchpad"
CARDS="/home/user/cardnews/cards"
def P(n): return glob.glob(f"{S}/npm/node_modules/@expo-google-fonts/**/{n}.ttf",recursive=True)[0]
BHS=P("BlackHanSans_400Regular"); JR=P("MPLUSRounded1c_800ExtraBold"); JB=P("MPLUSRounded1c_900Black")
NK=P("NotoSansKR_500Medium"); NB=P("NotoSansKR_900Black")
BG=(16,15,14); OR=(253,133,5); GRAY=(142,136,130); BROWN=(92,50,4); W=1080; H=1350
CFG=dict(ko_s0=227, ko_stroke=0.075, ko_maxw=904, yomi_s=43.5, ja_s=66, maxw=900)
def font(p,s): return ImageFont.truetype(p,max(8,int(round(s))))
def fit(text,p,s0,maxw,stroke=0.0):
    s=s0
    while s>10:
        f=font(p,s); sw=int(round(stroke*s))
        b=f.getbbox(text,stroke_width=sw)
        if b[2]-b[0]<=maxw: return f,sw
        s-=1
    return f,sw
def draw_top(d, y, x0, text, f, fill, sw=0):
    """원하는 글리프 윗면 y에 맞춰 그린다. 글리프 bbox 반환"""
    t=Image.new("L",(W*2,600),0); td=ImageDraw.Draw(t)
    td.text((50,50),text,font=f,fill=255,stroke_width=sw,stroke_fill=255)
    b=t.getbbox()
    d.text((x0-(b[0]-50), y-(b[1]-50)), text, font=f, fill=fill, stroke_width=sw, stroke_fill=fill)
    return (x0, y, x0+b[2]-b[0], y+b[3]-b[1])
LOGO_BODY=Image.open(f"{CARDS}/d03_insta_01.png").crop((440,1200,640,1310))
LOGO_COVER=Image.open(f"{CARDS}/d03_insta_00.png").crop((440,1200,640,1310))
KO_SQ=0.875
def draw_ko(im, y, x0, text, s0=270, maxw=900):
    s=s0
    while s>10:
        f=font(BHS,s); b=f.getbbox(text)
        if (b[2]-b[0])*KO_SQ<=maxw: break
        s-=1
    t=Image.new("L",(W*2,800),0); td=ImageDraw.Draw(t); td.text((50,50),text,font=f,fill=255)
    bb=t.getbbox(); t=t.crop(bb)
    t=t.resize((round(t.width*KO_SQ),t.height),Image.LANCZOS)
    im.paste(Image.new("RGB",t.size,OR),(x0,y),t)
    return (x0,y,x0+t.width,y+t.height),f
def label_font(): return font(JR if False else P("MPLUSRounded1c_700Bold"),34)
def body(topic,idx,c,box=False):
    im=Image.new("RGB",(W,H),BG); d=ImageDraw.Draw(im)
    d.rectangle((0,0,W,14),fill=OR)
    draw_top(d,76,88,topic,font(P("MPLUSRounded1c_700Bold"),34),OR)
    draw_top(d,174,88,f"{idx:02d}",font(NB,72),OR)
    ko,f=draw_ko(im,446,91,c["ko"])
    y=ko[3]+0.1*f.size
    fy=font(NK,CFG["yomi_s"]); yb=draw_top(d,round(y),88,c["yomi"],fy,GRAY)
    fj,_=fit(c["mean"],JR,CFG["ja_s"],CFG["maxw"])
    draw_top(d,yb[3]+51,88,c["mean"],fj,(255,255,255))
    im.paste(LOGO_BODY,(440,1200))
    return im
def cover(topic,hero,lead,sub):
    im=Image.new("RGB",(W,H),OR); d=ImageDraw.Draw(im)
    d.rectangle((0,0,W,14),fill=BG)
    draw_top(d,76,88,topic,font(P("MPLUSRounded1c_700Bold"),34),BROWN)
    fh,_=fit(hero,JB,W*0.215,900)
    hb=draw_top(d,449,93,hero,fh,BG)
    fl,_=fit(lead,JB,88,900)
    lb=draw_top(d,691,91,lead,fl,BG)
    d.rectangle((81,814,275,828),fill=BG)
    draw_top(d,860,83,sub,font(NK,43.5),BROWN)
    im.paste(LOGO_COVER,(440,1200))
    return im
if __name__=="__main__":
    day=int(sys.argv[1]); out=sys.argv[2]
    plan=[x for x in json.load(open("/home/user/cardnews/계획.json")) if x["day"]==day][0]
    import os; os.makedirs(out,exist_ok=True)
    cover(plan["topic"],plan["hero"],plan["lead"],plan["sub"]).save(f"{out}/d{day:02d}_insta_00.png")
    for i,c in enumerate(plan["cards"],1):
        body(plan["topic"],i,c).save(f"{out}/d{day:02d}_insta_{i:02d}.png")
