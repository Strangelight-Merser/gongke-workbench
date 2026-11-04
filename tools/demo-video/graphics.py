"""只用于影片的示意动画和证据文字页；不生成或冒充产品界面。"""
from PIL import Image, ImageDraw, ImageFilter, ImageOps
from functools import lru_cache
from pathlib import Path
import math

@lru_cache(None)
def asset(path):
 return Image.open(path).convert('RGB')

def card(canvas,pic,box,active):
 x,y,w,h=map(round,box)
 layer=Image.new('RGBA',canvas.size)
 ImageDraw.Draw(layer).rounded_rectangle((x-4,y+10,x+w+4,y+h+14),24,fill=(0,0,0,110))
 layer=layer.filter(ImageFilter.GaussianBlur(16));canvas.paste(layer,(0,0),layer)
 fitted=ImageOps.contain(pic,(w,h),Image.Resampling.LANCZOS)
 pic=Image.new('RGB',(w,h),pic.getpixel((0,0)));pic.paste(fitted,((w-fitted.width)//2,(h-fitted.height)//2))
 mask=Image.new('L',(w,h));ImageDraw.Draw(mask).rounded_rectangle((0,0,w-1,h-1),18,fill=255)
 canvas.paste(pic,(x,y),mask)
 if active:ImageDraw.Draw(canvas).rounded_rectangle((x-3,y-3,x+w+3,y+h+3),21,outline='#72d8cc',width=4)

def opening(canvas,t,root,font,ease):
 # 两张真实素材在同一舞台切换视觉焦点。图纸只裁切，不重绘、不改标注。
 pdf=asset(str(root/'out/demo-video/v2-assets/robot4.png'))
 w,h=pdf.size;pdf=pdf.crop((w*.10,h*.025,w*.45,h*.415))
 cad=asset(str(root/'out/demo-video/v2-main-02/opening-cad.png'))
 w,h=cad.size;cad=cad.crop((w*.24,h*.43,w*.64,h*.79))
 phase=min(3,int(t/3));u=ease(min(1,(t%3)/.85))
 target=phase%2
 previous=(phase-1)%2 if phase else 0
 focus=previous+(target-previous)*u
 # 抽象舞台卡片，标题位于产品截图之外。
 for i,pic in enumerate((pdf,cad)):
  prominence=1-abs(i-focus);width=625+155*prominence;height=550+90*prominence
  center=510 if i==0 else 1410
  card(canvas,pic,(center-width/2,520-height/2,width,height),prominence>.75)
 d=ImageDraw.Draw(canvas)
 d.text((160,110),'读尺寸，切窗口，再核对。',font=font(51,650),fill='#eef5fa')
 d.text((510,875),'图纸',font=font(35,600),fill='#77d6cd' if focus<.5 else '#9fb2c6',anchor='mm')
 d.text((1410,875),'CAD',font=font(35,600),fill='#77d6cd' if focus>.5 else '#9fb2c6',anchor='mm')
 # 方向随真实素材的视觉焦点改变；不是产品内点击或操作回执。
 right=phase%2==1
 start,end=(870,1050) if right else (1050,870)
 d.line((start,520,end,520),fill='#77d6cd',width=5)
 sign=1 if right else -1
 d.line((end-18*sign,506,end,520,end-18*sign,534),fill='#77d6cd',width=5)
 labels=['读取图纸尺寸','切到 CAD 建模','回到图纸复核','再切回模型']
 d.text((960,940),labels[phase],font=font(28,550),fill='#b9cbd9',anchor='mm')

def evidence(canvas,t,root,font,ease):
 d=ImageDraw.Draw(canvas)
 d.text((170,135),'可以运行，也可以交付',font=font(58,650),fill='#eef5fa')
 for i,(title,subtitle,items,foot) in enumerate([
  ('Windows','安装验收通过',['中文账户环境','result.json · ok = true'],'CI 41822011858 · 历史版本 41ec469'),
  ('macOS','本地打包验收通过',['1366 × 768 / 1920 × 1080','空工程 · 建模保存 · 重启打开 · 工程隔离'],'两种窗口宽度 · 四轮通用流程')
 ]):
  x=170+i*810;y=300
  active=(t<7.5)==(i==0)
  d.rounded_rectangle((x,y,x+770,y+530),radius=24,fill='#1b3045',outline='#77d6cd' if active else '#365067',width=3)
  d.text((x+42,y+40),title,font=font(46,650),fill='#77d6cd')
  d.text((x+42,y+120),subtitle,font=font(39,600),fill='#eef5fa')
  for j,line in enumerate(items):d.text((x+42,y+235+j*65),line,font=font(28 if i else 32),fill='#d5e3ec')
  d.text((x+42,y+450),foot,font=font(24),fill='#a7bdcf')
 d.text((170,900),'Windows 为历史版本证据；macOS 为本地流程验收。',font=font(28),fill='#a7bdcf')
