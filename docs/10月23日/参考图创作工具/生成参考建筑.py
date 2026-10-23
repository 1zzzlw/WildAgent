"""本批三份已保存设计的确定性作者脚本；不是自然语言建筑生成器。

只依赖Python标准库。 --case 13/14/15；输出位置相对本脚本，不依赖原仓库盘符。
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PI = math.pi


def clean(value):
    if isinstance(value, float):
        value = round(value, 5)
        return int(value) if value.is_integer() else value
    if isinstance(value, list): return [clean(x) for x in value]
    if isinstance(value, dict): return {k: clean(v) for k, v in value.items() if v is not None}
    return value


class Author:
    def __init__(self, plan):
        self.plan, self.e, self.c, self.walls = plan, [], [], {}
        self.serial = 0
        self.materials = {}
        for name, color, rough, metal in [
            ('ivory', [.86,.84,.77], .78,0), ('trim', [.93,.91,.84], .66,0),
            ('roof', [.13,.16,.18], .72,0), ('tile_edge', [.20,.23,.25], .62,0),
            ('stone', [.62,.64,.61], .78,0), ('paving', [.76,.75,.69], .83,0),
            ('soil', [.12,.085,.055], .95,0), ('metal', [.075,.09,.095], .3,.65),
            ('wood', [.31,.15,.075], .53,0), ('oak', [.62,.44,.25], .5,0),
            ('fabric', [.64,.58,.45], .91,0), ('leaf', [.18,.30,.085], .88,0),
            ('leaf_light', [.30,.40,.12], .91,0), ('grass', [.23,.33,.12], .95,0),
            ('pink', [.71,.22,.36], .85,0), ('cream', [.96,.84,.47], .85,0),
            ('pot', [.47,.24,.13], .85,0), ('dark', [.045,.05,.055], .6,0),
        ]:
            self.materials[name] = dict(baseColor=color,roughness=rough,metallic=metal,albedo=1,lightingCondition='D65_noon')
        self.materials['glass'] = dict(baseColor=[.86,.94,.97],roughness=.07,metallic=0,albedo=1,lightingCondition='D65_noon',materialClass='glass',surfaceFamily='glass',transmission=.92,ior=1.5,thickness=.012)
        self.materials['oak'].update(surfaceFamily='wood',surfacePattern='planks',clearcoat=.12,clearcoatRoughness=.32)
        self.materials['quartz'] = dict(baseColor=[.88,.86,.80],roughness=.24,metallic=0,albedo=1,lightingCondition='D65_noon',surfaceFamily='mineral',surfacePattern='quartz',materialClass='clearcoat',clearcoat=.2,clearcoatRoughness=.18)
        self.materials['glow'] = dict(baseColor=[1,.81,.48],roughness=.45,metallic=0,albedo=1,lightingCondition='D65_noon',emissive=[1,.61,.22],emissiveIntensity=1.7)

    def add(self, kind, id=None, **kw):
        self.serial += 1
        row = dict(type=kind,id=id or f'{kind}_{self.serial}',**kw)
        self.e.append(row)
        return row

    def box(self, x,y,z,w,h,d,mat='trim',id=None,**kw):
        return self.add('primitive',id,shape='box',position=[x,y,z],dimensions=[w,h,d],material=mat,**kw)

    def sphere(self,x,y,z,r,mat='leaf',scale=None):
        return self.add('primitive',shape='sphere',position=[x,y,z],radius=r,segments=12,heightSegments=8,material=mat,scale=scale)

    def cyl(self,x,y,z,r,h,mat='wood',top=None):
        return self.add('primitive',shape='cylinder',position=[x,y,z],radiusBottom=r,radiusTop=r if top is None else top,height=h,segments=12,material=mat)

    def rod(self,a,b,r=.025,mat='metal'):
        d=[b[i]-a[i] for i in range(3)]; length=math.sqrt(sum(t*t for t in d))
        return self.box(*[(a[i]+b[i])/2 for i in range(3)],2*r,length,2*r,mat,
                        rotation=[math.atan2(d[2],d[1]),0,-math.asin(d[0]/length)])

    def sweep(self,path,r=.025,mat='tile_edge'):
        return self.add('primitive',shape='profile_sweep',position=[0,0,0],path=path,radius=r,segments=6,material=mat)

    def slab(self,id,x1,z1,x2,z2,top,th=.22,mat='ivory'):
        return self.add('floor',id,**{'from':[x1,top-th,z1],'to':[x2,top-th,z2]},thickness=th,material=mat)

    def wall(self,id,x1,z1,x2,z2,y,h,mat='ivory',th=.24):
        row=self.add('wall',id,**{'from':[x1,y,z1],'to':[x2,y+h,z2]},thickness=th,material=mat)
        self.walls[id]=row
        return id

    def shell(self,prefix,x1,z1,x2,z2,y,h):
        self.wall(prefix+'_front',x1,z1,x2,z1,y,h)
        self.wall(prefix+'_right',x2,z1,x2,z2,y,h)
        self.wall(prefix+'_back',x2,z2,x1,z2,y,h)
        self.wall(prefix+'_left',x1,z2,x1,z1,y,h)

    def opening(self,wall,x,z,y,w,h,door=False,style='black',mullions=1):
        host=self.walls[wall]; a,b=host['from'],host['to']; dx,dz=b[0]-a[0],b[2]-a[2]; length=math.hypot(dx,dz)
        u=[dx/length,dz/length]; along=(x-a[0])*u[0]+(z-a[2])*u[1]-w/2
        self.serial+=1
        c=dict(type='door' if door else 'window',id=f'opening_{self.serial}',parentWall=wall,**{'from':[along,y,0]},width=w,height=h,frameWidth=.065,frameDepth=.26,frameMaterial='wood' if style=='wood' else 'metal')
        if door:
            c.update(leafMaterial='glass',doorStyle='double' if w>1.8 else 'single',leafRows=2,interaction=dict(mode='swing',hingeSide='left',openAngle=85,initiallyOpen=False))
        else: c.update(glassMaterial='glass',verticalMullions=mullions,horizontalMullions=1 if h<1.8 else 2,mullionWidth=.028)
        self.c.append(c)
        # Four pieces around the actual aperture, no decorative panel across the glass.
        nx,nz=-u[1],u[0]
        for off in (-w/2-.075,w/2+.075):
            self.box(x+u[0]*off+nx*.025,y+h/2,z+u[1]*off+nz*.025,
                     .12 if abs(dx)<.001 else .15,h+.24,.15 if abs(dx)<.001 else .12,'trim')
        if abs(dx)>.001:
            self.box(x,y-.06,z,w+.3,.12,.38,'trim')
            self.box(x,y+h+.08,z,w+.32,.14,.32,'trim')
        else:
            self.box(x,y-.06,z,.38,.12,w+.3,'trim')
            self.box(x,y+h+.08,z,.32,.14,w+.32,'trim')

    def rail(self,path,y=None,wood=False,glass=False):
        if y is not None: path=[[x,y,z] for x,z in path]
        self.serial+=1
        kw=dict(type='railing',id=f'rail_{self.serial}',path=path,height=1.03,postSpacing=.75 if wood else .24,postRadius=.035 if wood else .017,railRadius=.035 if wood else .022,railLevels=[.15,.87,1],material='wood' if wood else 'metal')
        if glass: kw.update(postSpacing=1.35,infillType='glass',infillMaterial='glass',infillThickness=.015,infillTopRatio=.9)
        self.c.append(kw)
        if wood:
            for a,b in zip(path,path[1:]):
                length=math.hypot(b[0]-a[0],b[2]-a[2]); n=max(1,round(length/.7))
                for k in range(n):
                    t=(k+.5)/n; x=a[0]+(b[0]-a[0])*t; z=a[2]+(b[2]-a[2])*t
                    ux,uz=(b[0]-a[0])/length,(b[2]-a[2])/length
                    for side in (-1,1):
                        off=side*.21
                        self.rod([x+ux*off,a[1]+.3,z+uz*off],[x+ux*off,a[1]+.73,z+uz*off],.018,'wood')
                    self.rod([x-ux*.21,a[1]+.52,z-uz*.21],[x+ux*.21,a[1]+.52,z+uz*.21],.018,'wood')

    def lamp(self,x,y,z):
        self.box(x,y,z,.19,.4,.18,'metal')
        self.box(x,y+.24,z,.25,.07,.24,'metal')
        self.box(x,y,z-.101,.12,.26,.025,'glow',lightSource=dict(intensity=8,distance=4,initiallyOn=True,offset=[0,0,-.14],color=[1,.78,.44]))

    def pot(self,x,y,z,scale=.8,flower=False):
        self.cyl(x,y+.2*scale,z,.25*scale,.4*scale,'pot',.31*scale)
        self.cyl(x,y+.405*scale,z,.275*scale,.025*scale,'soil')
        self.sphere(x,y+.67*scale,z,.35*scale,'leaf', [1,.9,1])
        if flower:
            for i in range(5):
                a=i*2*PI/5
                self.sphere(x+.22*scale*math.cos(a),y+.9*scale,z+.22*scale*math.sin(a),.09*scale,'pink')

    def shrub(self,x,z,r=.6,mat='leaf',y=.15):
        self.sphere(x,y+r*.65,z,r,mat,[1,.78,1])

    def bed(self,x1,z1,x2,z2,flowers=False):
        self.box((x1+x2)/2,.12,(z1+z2)/2,x2-x1,.24,z2-z1,'stone')
        self.box((x1+x2)/2,.26,(z1+z2)/2,x2-x1-.14,.05,z2-z1-.14,'soil')
        n=max(2,round(max(x2-x1,z2-z1)/.65))
        for i in range(n):
            t=(i+.5)/n; x=x1+.35+(x2-x1-.7)*t; z=z1+.35+(z2-z1-.7)*t
            self.shrub(x,z,.28 if flowers else .45,'leaf_light' if i%3==0 else 'leaf',.27)
            if flowers: self.sphere(x+.12,.68,z,.12,'pink' if i%2 else 'cream')

    def furniture(self,kind,x,y,z,w,d,h,mat='oak',yaw=0):
        return self.add('furniture',subtype=kind,position=[x,y,z],dimensions=dict(width=w,depth=d,height=h),material=mat,rotation=[0,yaw,0])

    def lounge(self,x,y,z):
        self.furniture('sofa',x,y,z,2.6,.9,.82,'fabric')
        self.furniture('table',x,y,z-1.25,1.35,.65,.43,'wood')
        self.box(x,y+.45,z-1.25,.37,.05,.28,'cream')
        self.furniture('tv_cabinet',x,y,z-2.4,2.4,.4,.52,'wood')
        self.box(x,y+1.15,z-2.5,1.7,.95,.06,'dark')

    def bedroom(self,x,y,z):
        self.furniture('bed',x,y,z,1.8,2.15,.6,'fabric')
        for side in (-1,1): self.furniture('nightstand',x+side*1.2,y,z+.65,.45,.45,.48,'wood')
        self.furniture('wardrobe',x+1.55,y,z+1.6,1.6,.58,2.25,'wood',PI/2)

    def dining(self,x,y,z):
        self.cyl(x,y+.75,z,.95,.08,'quartz')
        self.cyl(x,y+.35,z,.2,.7,'metal')
        for k in range(6):
            a=k*PI/3
            self.furniture('chair',x+1.25*math.sin(a),y,z+1.25*math.cos(a),.5,.56,.9,'wood',a+PI)

    def kitchen(self,x,y,z,w=3):
        self.box(x,y+.44,z,w,.88,.64,'wood')
        self.box(x,y+.91,z,w+.06,.06,.7,'quartz')
        for i in range(round(w/.6)):
            self.box(x-w/2+(i+.5)*w/round(w/.6),y+.48,z-.33,.45,.025,.025,'metal')
        self.box(x+.5,y+.95,z,.65,.025,.42,'metal')
        self.box(x-.7,y+.95,z,.5,.025,.4,'dark')
        self.box(x,y+1.9,z,w,.65,.38,'wood')

    def stairs(self,x,z,lower,upper):
        # U stair: two 1.1m flights, central landing, top return; true slab opening recorded below.
        half=(upper-lower)/2; n=10; run=2.8
        self.add('stair',**{'from':[x,lower,z],'to':[x,lower+half,z+run]},width=1.05,stepCount=n,stepHeight=half/n,stepDepth=run/n,material='stone')
        self.slab('landing_'+str(self.serial),x-.6,z+run,x+1.75,z+run+1.1,lower+half,.16,'stone')
        self.add('stair',**{'from':[x+1.15,lower+half,z+run],'to':[x+1.15,upper,z]},width=1.05,stepCount=n,stepHeight=half/n,stepDepth=run/n,material='stone')
        self.rail([[x-.57,lower,z],[x-.57,lower+half,z+run]])
        self.rail([[x+1.72,lower+half,z+run],[x+1.72,upper,z]])

    def floor_with_stair(self,id,x1,z1,x2,z2,y,sx,sz):
        self.add('floor',id,shape='polygon',**{'from':[x1,y-.23,z1]},polygon=[[0,0],[x2-x1,0],[x2-x1,z2-z1],[0,z2-z1]],
                 holes=[[[sx-.62-x1,sz-.08-z1],[sx+1.75-x1,sz-.08-z1],[sx+1.75-x1,sz+4-z1],[sx-.62-x1,sz+4-z1]]],thickness=.23,material='ivory')

    def hip(self,id,cx,cz,w,d,y,h):
        self.add('roof',id,roofType='hip',span=w,depth=d,height=h,thickness=.14,position=[cx,y,cz],material='roof')
        r=min(w,d)/2
        def top(x,z): return y+h*max(0,min((w/2-abs(x-cx))/r,(d/2-abs(z-cz))/r))+.025
        # Longitudinal barrel tiles; points are derived from this exact roof surface.
        for i in range(1,round(w/.29)):
            x=cx-w/2+i*w/round(w/.29)
            self.sweep([[x,top(x,z),z] for z in [cz-d/2+j*d/16 for j in range(17)]],.022)
        for sign in (-1,1):
            for k in range(1,round(d/.32)):
                z=cz-d/2+k*d/round(d/.32)
                if abs(z-cz)>max(0,(d-w)/2): continue
                self.sweep([[cx+sign*(w/2-t*w/2),top(cx+sign*(w/2-t*w/2),z)+.01,z] for t in (0,.25,.5,.75,1)],.017)
        # Horizontal courses on all four roof faces.
        for k in range(1,7):
            inset=r*k/7
            x1,x2=cx-w/2+inset,cx+w/2-inset;z1,z2=cz-d/2+inset,cz+d/2-inset
            self.sweep([[x1,top(x1,z1)+.006,z1],[x2,top(x2,z1)+.006,z1],[x2,top(x2,z2)+.006,z2],[x1,top(x1,z2)+.006,z2],[x1,top(x1,z1)+.006,z1]],.012,'roof')
        for ax,az in [(-1,-1),(1,-1),(-1,1),(1,1)]:
            ex=cx+ax*(w/2-r);ez=cz+az*(d/2-r)
            self.sweep([[cx+ax*w/2,y+.04,cz+az*d/2],[ex,y+h+.04,ez]],.055)
        if w>d: self.sweep([[cx-(w-d)/2,y+h+.055,cz],[cx+(w-d)/2,y+h+.055,cz]],.065)
        elif d>w: self.sweep([[cx,y+h+.055,cz-(d-w)/2],[cx,y+h+.055,cz+(d-w)/2]],.065)

    def chinese_roof(self,id,cx,cz,w,d,y,h):
        # Thin closed shell: ridge runs along X to match the reference, not the native Z ridge.
        def height(z):
            t=abs(z-cz)/(d/2)
            return y+h*max(0,1-t)**1.25+.10*t**6
        zs=[cz-d/2+i*d/24 for i in range(25)]
        section=[[-(z-cz),height(z)-y] for z in zs]
        profile=section+[[u,v-.12] for u,v in reversed(section)]
        self.add('primitive',id,shape='profile_sweep',position=[0,0,0],path=[[cx-w/2,y,cz],[cx+w/2,y,cz]],profile=profile,closedProfile=True,caps=True,material='roof')
        for k in range(round(w/.26)+1):
            x=cx-w/2+k*w/round(w/.26)
            self.sweep([[x,height(z)+.025,z] for z in zs],.024)
        for sign in (-1,1):
            for k in range(1,10):
                z=cz+sign*d/2*k/10
                self.sweep([[cx-w/2,height(z)+.01,z],[cx+w/2,height(z)+.01,z]],.012,'roof')
        self.sweep([[cx-w/2-.15,y+h+.3,cz],[cx-w/2+.5,y+h+.06,cz],[cx+w/2-.5,y+h+.06,cz],[cx+w/2+.15,y+h+.3,cz]],.09,'tile_edge')
        for sign in (-1,1):
            x=cx+sign*w/2
            self.sweep([[x,height(z)+.06,z] for z in zs],.075)
        for sign in (-1,1):
            self.box(cx,y-.07,cz+sign*d/2,w,.21,.18,'wood')

    def steps(self,x,z,width,top=.45):
        n=5; depth=.32
        for i in range(n):
            h=top*(i+1)/n
            self.box(x,h/2,z+i*depth,width,h,depth+.015,'stone')

    def sign(self,x,y,z,name):
        self.box(x,y,z,1.7,.48,.08,'wood',label=dict(text=name,color=[.94,.83,.56],fontFamily='serif'),rotation=[0,PI,0])

    def site(self):
        self.slab('site',-11,-9,11,17,0,.15,'paving')
        self.slab('street',-11,-11,11,-9,-.02,.18,'dark')
        # Paving joints are selective; no thousands of individual paving stones.
        for x in range(-10,11,2): self.box(x,.006,-4,.015,.008,9.7,'stone')
        for z in (-8,-6,-4,-2): self.box(0,.006,z,21.6,.008,.015,'stone')

    def output(self):
        return clean(dict(meta=dict(version='1.1',type='building',name=self.plan['name'],author='Codex',style=self.plan['parameters']['kind']),
                          geometry=dict(elements=self.e,components=self.c),materials=self.materials))


def classical(a):
    f=a.plan['massing']['ground_finish']; u=a.plan['massing']['upper_finish']
    a.site()
    a.slab('ground',-6.75,0,6.75,13,f)
    # Side wings and recessed central facade; no duplicate internal wall across the hall.
    for lv,y in enumerate((f,u)):
        p=f'l{lv+1}'
        a.wall(p+'_left',-6.75,13,-6.75,0,y,3.15)
        a.wall(p+'_right',6.75,0,6.75,13,y,3.15)
        a.wall(p+'_back',6.75,13,-6.75,13,y,3.15)
        a.wall(p+'_front_l',-6.75,0,-3.8,0,y,3.15)
        a.wall(p+'_front_r',3.8,0,6.75,0,y,3.15)
        a.wall(p+'_recess_l',-3.8,0,-3.8,2.6,y,3.15)
        a.wall(p+'_recess_r',3.8,2.6,3.8,0,y,3.15)
        a.wall(p+'_entry',-3.8,2.6,3.8,2.6,y,3.15)
        for x in (-5.27,5.27): a.opening(p+('_front_l' if x<0 else '_front_r'),x,0,y+.52,1.65,2.25,mullions=1)
        a.opening(p+'_entry',0,2.6,y,3.2,2.65,door=True)
        for side in ('left','right'):
            xx=-6.75 if side=='left' else 6.75
            for z in (4.6,8.2,11.3): a.opening(p+'_'+side,xx,z,y+.8,1.6,1.9)
        for x in (-4.8,0,4.8): a.opening(p+'_back',x,13,y+.85,1.6,1.8)
        # Major interior partitions contain their own door apertures.
        for x in (-3.25,3.25):
            wall=a.wall(p+'_partition_'+str(int(x*100)).replace('-','n'),x,4,x,12.85,y,3.15,th=.14)
            a.opening(wall,x,6,y,1,2.15,True)
    a.floor_with_stair('upper_floor',-6.75,0,6.75,13,u,3.95,8.1)
    a.slab('terrace',-4.6,-.65,4.6,2.6,u,.24)
    # Porch columns, carved bases and capitals are separate construction layers.
    for x in (-3.95,3.95):
        a.box(x,1.92,-.22,.38,2.55,.38)
        for y,w,h in [(.55,.67,.2),(.75,.53,.12),(3.15,.5,.12),(3.3,.65,.18)]: a.box(x,y,-.22,w,h,w)
        a.lamp(x,2.0,-.46)
    for y,width,h in [(3.44,9.65,.17),(3.61,9.85,.13)]: a.box(0,y,-.45,width,h,.46)
    # A shallow arch soffit follows the reference without placing a solid wall behind it.
    xs=[-3.65+i*7.3/32 for i in range(33)]
    arch=[[x,3.23+.24*(1-(x/3.65)**2),-.23] for x in xs]
    a.sweep(arch,.06,'trim')
    a.rail([[-4.4,u,-.48],[4.4,u,-.48],[4.4,u,2.35]])
    a.rail([[-4.4,u,-.48],[-4.4,u,2.35]])
    for x in (-4.4,4.4):
        a.box(x,u+.5,-.48,.38,1,.38)
        a.box(x,u+1.03,-.48,.54,.12,.54)
        a.cyl(x,u+1.2,-.48,.37,.2,'trim',.015)
    for x in (-6.55,6.55):
        for z in (.08,12.9):
            a.box(x,3.85,z,.32,6.8,.3)
            for y in (3.5,6.9,7.03): a.box(x,y,z,.47,.12,.46)
    a.hip('roof_main',0,7.7,14.35,11.5,7.35,1.9)
    for x in (-5.13,5.13): a.hip('roof_front_'+str(x),x,.95,4.1,3.4,7.35,1.05)
    a.steps(0,-2.35,6.7)
    a.stairs(3.95,8.1,f,u)
    a.lounge(.4,f,6.5); a.kitchen(-4.9,f,12.3,2.8);a.dining(-4.9,f,9.2)
    a.bedroom(-5,f,3.1)
    for x,z in [(-4.8,4.5),(-4.8,10),(0,10.5)]: a.bedroom(x,u,z)
    a.lounge(.1,u,6)
    for x in (-2.8,2.8): a.pot(x,u,.2,.8)
    for x in (-8.3,8.3): a.bed(x-.8,-3,x+.8,10,True)
    for x in (-4.7,4.7): a.bed(x-1,-4.5,x+1,-2)
    a.sign(2.65,1.6,2.39,a.plan['name'])
    for x in (-2.4,2.4): a.lamp(x,2.4,2.38)


def terrace(a):
    f=a.plan['massing']['ground_finish']; u=a.plan['massing']['upper_finish']
    a.site();a.slab('ground',-7,1,7,11,f)
    a.slab('garage_ground',-7,-3,-1,1,f)
    for lv,y in enumerate((f,u)):
        p=f'l{lv+1}';a.shell(p,-7,1,7,11,y,3.12)
        for x in (-4.8,0,4.8): a.opening(p+'_front',x,1,y+.1,3.15,2.75,door=True)
        for side,x in [('left',-7),('right',7)]:
            for z in (4,8): a.opening(p+'_'+side,x,z,y+.7,2.2,2.05)
        for x in (-4.7,0,4.7): a.opening(p+'_back',x,11,y+.85,1.8,1.8)
        wall=a.wall(p+'_divide',-.9,4,-.9,10.8,y,3.12,th=.14)
        a.opening(wall,-.9,6,y,1,2.2,True)
    a.floor_with_stair('upper_floor',-7,1,7,11,u,3.8,6.8)
    a.slab('terrace_front',-7.1,-1.1,7.1,1.1,u,.25)
    a.slab('terrace_garage',-7.1,-3.2,-1.1,-1.1,u,.25)
    a.wall('garage_left',-7,1,-7,-3,f,3.1);a.wall('garage_right',-1,-3,-1,1,f,3.1)
    a.wall('garage_front',-7,-3,-1,-3,f,3.1)
    a.opening('garage_front',-4,-3,f,5.2,2.7,True,mullions=0)
    a.rail([[-7,u,1],[-7,u,-3.12],[-1.15,u,-3.12],[-1.15,u,-1.02],[7,u,-1.02],[7,u,1]],glass=True)
    for x in (-.8,4.3): a.box(x,1.99,-.65,.32,3.08,.32)
    a.box(3.1,3.48,-.65,8.1,.23,.36)
    a.hip('main_roof',0,6.05,15,11.3,7.15,1.8)
    a.box(5.4,8.6,8.1,.45,1.35,.55)
    a.box(5.4,9.32,8.1,.61,.12,.72,'metal')
    a.stairs(3.8,6.8,f,u)
    a.lounge(3,f,4.7);a.kitchen(-4.8,f,10.35,3.6);a.dining(-4.8,f,7.4)
    a.bedroom(-4.6,u,7.5);a.bedroom(.2,u,7.9)
    a.furniture('table',4.7,u,3.7,1.6,.7,.75,'wood');a.furniture('chair',4.7,u,4.6,.5,.6,.9,'fabric')
    a.furniture('table',-4.6,u,-1.75,1.6,.8,.73,'oak')
    for z in (-2.6,-.7):
        for x in (-5.3,-3.9): a.furniture('chair',x,u,z,.53,.58,.86,'wood',0 if z< -1 else PI)
    for x in (-6.2,6): a.pot(x,u,-.6,.75,True)
    for x in (-6.4,-2.45,2.4,6.4):
        a.lamp(x,2.65,.8);a.lamp(x,5.9,.8)
    a.steps(1.5,-2.0,4.1)
    a.bed(7.6,-6,9.6,11,True)
    a.bed(-9.6,-3,-7.8,10,True)
    a.bed(3.5,-7.9,8.7,-4.1,True)
    a.shrub(6,-5.5,.95);a.shrub(4.5,-6.6,.55)
    for z in range(-6,12,2): a.box(8,.3,z,1.25,.1,1.25,'stone')
    # Small procedural car as scale cue; it is not a downloaded model.
    a.box(-2,.61,-5.8,1.8,.5,3.7,'stone')
    a.box(-2,1.07,-5.5,1.55,.43,1.9,'glass')
    a.box(-2,1.32,-5.5,1.55,.08,1.9,'metal')
    for x in (-2.92,-1.08):
        for z in (-6.9,-4.7): a.cyl(x,.4,z,.32,.17,'dark')['rotation']=[0,0,PI/2]
    a.sign(.5,1.6,.8,a.plan['name'])


def courtyard(a):
    f=a.plan['massing']['ground_finish']; u=a.plan['massing']['upper_finish']
    a.site();a.slab('rear_ground',-7,6,7,14,f)
    for lv,y in enumerate((f,u)):
        p=f'rear{lv+1}';a.shell(p,-7,6,7,14,y,3.12)
        for x in (-4.5,0,4.5): a.opening(p+'_front',x,6,y+.1,2.5,2.55,door=(x==0),style='wood',mullions=2)
        for side,x in [('left',-7),('right',7)]:
            for z in (8.5,12): a.opening(p+'_'+side,x,z,y+.85,1.65,1.85,style='wood')
        for x in (-4.5,0,4.5): a.opening(p+'_back',x,14,y+.85,1.6,1.8,style='wood')
        wall=a.wall(p+'_partition',2.5,8,2.5,13.8,y,3.12,th=.14)
        a.opening(wall,2.5,10,y,1,2.15,True,style='wood')
    a.floor_with_stair('rear_upper',-7,6,7,14,u,4.2,8.6)
    a.slab('main_balcony',-6.8,4.6,6.8,6.1,u,.22)
    a.rail([[-6.6,u,4.75],[2.5,u,4.75]],wood=True)
    a.rail([[3.7,u,4.75],[6.6,u,4.75],[6.6,u,6]],wood=True)
    # Roof is a hollow curved shell so no solid wedge fills the upper rooms.
    a.chinese_roof('rear_roof',0,10,15.4,9.4,7.15,1.65)
    a.shell('side',-7,-1.4,-2.5,6,f,3.12)
    a.opening('side_right',-2.5,2,f,1.6,2.35,True,style='wood')
    a.opening('side_front',-4.75,-1.4,f+.7,1.7,1.8,style='wood')
    a.slab('side_terrace',-7.2,-1.6,-2.3,6,u,.22)
    a.rail([[-7.05,u,5.8],[-7.05,u,-1.45],[-2.45,u,-1.45],[-2.45,u,3.8]],wood=True)
    # Pavilion at the back of the side terrace leaves the front seating open.
    for x in (-6.7,-2.8):
        for z in (2.75,5.65):
            a.cyl(x,u+1.3,z,.105,2.6,'wood')
            a.cyl(x,u+.12,z,.18,.24,'stone')
    a.box(-4.75,u+2.62,4.2,4.35,.22,.22,'wood')
    a.chinese_roof('pavilion_roof',-4.75,4.2,5.2,4.2,u+2.78,.75)
    a.stairs(4.2,8.6,f,u)
    # Exterior access to left terrace: two flights parallel to courtyard edge, full landing.
    a.stairs(-6.35,1.1,f,u)
    # Hole in side roof/terrace for the staircase, using explicit local polygon coordinates.
    terrace=next(e for e in a.e if e['id']=='side_terrace')
    a.e.remove(terrace)
    a.floor_with_stair('side_terrace',-7.2,-1.6,-2.3,6,u,-6.35,1.1)
    # Courtyard walls and tiled entrance gateway; doorway remains a genuine opening.
    a.wall('court_front',-7,-3.6,7,-3.6,.0,2.65)
    a.opening('court_front',0,-3.6,0,2.25,2.45,True,style='wood')
    a.c[-1]['leafMaterial']='wood';a.c[-1]['leafRows']=4
    for x in (-4.7,4.7): a.opening('court_front',x,-3.6,.8,1.3,1.25,style='wood',mullions=2)
    a.wall('court_right',7,-3.6,7,6,0,2.4)
    for z in (-.2,3.8): a.opening('court_right',7,z,.7,1.4,1.3,style='wood')
    a.chinese_roof('gate_roof',0,-3.6,4,2.2,2.85,.65)
    for x in (-4.7,4.7): a.chinese_roof('wall_cap_'+str(x),x,-3.6,5.15,1.15,2.72,.35)
    # Side roof cap rotated geometrically with primitive transforms, without inventing roof.rotation.
    start=len(a.e);a.chinese_roof('side_wall_cap',0,0,9.7,1.12,2.52,.35)
    for e in a.e[start:]:
        x,y,z=e['position']
        e['position']=[7+z,y,1.2-x]
        e['rotation']=[0,PI/2,0]
    for x in (-2.7,2.7):
        a.box(x,1.9,5.1,.25,2.9,.25,'stone')
        a.lamp(x,2.6,5.75)
    a.slab('porch',-3.2,4.6,3.2,6,f,.2,'stone')
    a.steps(0,3,4.5)
    a.lounge(-2.6,f,10.5);a.kitchen(-4.5,f,13.4,3.1);a.dining(-4.6,f,8.1)
    a.bedroom(4.4,f,7.8);a.bedroom(-4.3,u,10.7);a.bedroom(.3,u,11)
    for x,z,y in [(-4.8,.2,u),(3.7,1.7,0)]:
        a.furniture('table',x,y,z,1.3,.85,.72,'wood')
        for dx,dz,yaw in [(-.9,0,PI/2),(.9,0,-PI/2)]: a.furniture('chair',x+dx,y,z+dz,.55,.6,.88,'wood',yaw)
    for x,z in [(-1.6,4.9),(1.6,4.9),(-1.65,-1.1),(5.8,3),(5.8,-1.8),(-6.4,1),(-6.4,5.4)]: a.pot(x,f if z>4 else 0,z,.8,True)
    for x in (-5,5): a.bed(x-1,-5.1,x+1,-4,True)
    a.bed(8,-3,9.4,14,True);a.bed(-9.3,-2,-8,13,True)
    for x in (-2,2): a.lamp(x,2.0,-3.85)
    for x in (-5,5): a.lamp(x,5.95,5.8)
    a.sign(0,2.72,-4.18,a.plan['name'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=['13','14','15'],required=True)
    args=parser.parse_args()
    folder=next(p for p in ROOT.iterdir() if p.is_dir() and p.name.startswith(args.case+'-'))
    design_path=folder/'01-需求与设计/设计输入.json'
    plan=json.loads(design_path.read_text(encoding='utf-8'))
    author=Author(plan)
    {'13':classical,'14':terrace,'15':courtyard}[args.case](author)
    blueprint=author.output()
    target=folder/(plan['name']+'.wild')
    target.write_text(json.dumps(blueprint,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n',encoding='utf-8')
    report=dict(name=plan['name'],design_sha256=hashlib.sha256(design_path.read_bytes()).hexdigest(),wild_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),bytes=target.stat().st_size,elements=len(author.e),components=len(author.c),materials=len(author.materials),method='手工设计事实 → Python标准库确定性几何展开 → 自足WILD；没有调用LangGraph/RAG/模型API/外部模型资产',validation='本报告仅为写出统计；不代表编译或视觉通过')
    (folder/'03-过程记录/生成统计.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__': main()
