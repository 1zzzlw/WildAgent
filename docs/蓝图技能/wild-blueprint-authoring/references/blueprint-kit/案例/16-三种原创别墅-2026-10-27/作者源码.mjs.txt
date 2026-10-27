import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { createHash } from 'node:crypto'

const here = dirname(fileURLToPath(import.meta.url))
const catalog = JSON.parse(await readFile(new URL('../../../wild-core/material-presets.json', import.meta.url), 'utf8'))
const presets = Object.fromEntries(catalog.map(p => [p.id, p.material]))
const basic = (color, roughness = .8) => ({ baseColor: color, roughness, metallic: 0, albedo: 1, lightingCondition: 'D65_noon' })

class Blueprint {
  constructor(name) {
    this.data = { meta: { version: '1.1', type: 'building', name }, geometry: { elements: [], components: [] }, materials: {
      wall: structuredClone(presets.plaster_lime), stone: structuredClone(presets.stone_travertine), paving: structuredClone(presets.tiles_limestone),
      concrete: structuredClone(presets.concrete_fair), oak: structuredClone(presets.planks_oak), walnut: structuredClone(presets.planks_walnut),
      glass: structuredClone(presets.glass_clear), metal: { ...presets.metal_brushed, baseColor: [.14, .17, .18] },
      linen: structuredClone(presets.fabric_linen), quartz: structuredClone(presets.quartz_ivory), clay: structuredClone(presets.tiles_terracotta),
      grass: basic([.28, .36, .23]), leaf: basic([.23, .32, .19]), soil: basic([.28, .23, .17]),
      water: { ...basic([.42, .65, .62], .08), materialClass: 'glass', transmission: .95, ior: 1.333, thickness: .9, attenuationColor: [.56, .81, .75], attenuationDistance: 4 },
      glow: { ...basic([1, .86, .65], .35), emissive: [1, .71, .38], emissiveIntensity: 1.5 },
    } }
  }
  add(e) { this.data.geometry.elements.push(e); return e }
  comp(c) { this.data.geometry.components.push(c); return c }
  box(id, p, d, material, rotation) { return this.add({ type: 'primitive', id, shape: 'box', position: p, dimensions: d, material, ...(rotation ? { rotation } : {}) }) }
  cylinder(id, p, radius, height, material, top = radius) { return this.add({ type: 'primitive', id, shape: 'cylinder', position: p, radiusBottom: radius, radiusTop: top, height, segments: 16, material }) }
  slab(id, r, top, thickness, material, holes = []) {
    const [x0, x1, z0, z1] = r
    return this.add(holes.length ? { type: 'floor', id, shape: 'polygon', from: [x0, top - thickness, z0], thickness, polygon: [[0, 0], [x1 - x0, 0], [x1 - x0, z1 - z0], [0, z1 - z0]], holes: holes.map(([a,b,c,d]) => [[a-x0,c-z0],[b-x0,c-z0],[b-x0,d-z0],[a-x0,d-z0]]), material }
      : { type: 'floor', id, from: [x0, top - thickness, z0], to: [x1, top - thickness, z1], thickness, material })
  }
  wall(id, a, b, floor, top, material = 'wall', thickness = .26) { return this.add({ type: 'wall', id, from: [a[0], floor, a[1]], to: [b[0], top, b[1]], thickness, material }) }
  room(id, r, floor, top, material = 'wall') {
    const [a,b,c,d] = r
    return { n: this.wall(id+'_n',[a,c],[b,c],floor,top,material), e: this.wall(id+'_e',[b,c],[b,d],floor,top,material), s: this.wall(id+'_s',[b,d],[a,d],floor,top,material), w: this.wall(id+'_w',[a,d],[a,c],floor,top,material) }
  }
  opening(id, wall, center, bottom, width, height, { door = false, arched = false, leaf = 'glass', frame = 'metal', trim = false, fixed = false } = {}) {
    const dx = wall.to[0]-wall.from[0], dz = wall.to[2]-wall.from[2], len = Math.hypot(dx,dz), ux=dx/len, uz=dz/len
    const along = (center[0]-wall.from[0])*ux + (center[1]-wall.from[2])*uz - width/2
    if (along < -1e-6 || along+width > len+1e-6 || bottom+height > wall.to[1]+1e-6) throw Error('开口越界: '+id)
    const c = { type: door?'door':'window', id, parentWall: wall.id, from: [along,bottom,0], width, height, frameWidth: arched?.095:.055, frameDepth: wall.thickness+.02, frameMaterial: frame }
    if (door) Object.assign(c,{leafMaterial:leaf, leafDepth: .04, ...(arched?{openingStyle:'arched'}:{}), interaction: { mode:'swing',hingeSide:'left',openAngle:90,initiallyOpen:false }})
    else Object.assign(c,{glassMaterial:'glass',glassDepth:.012,verticalMullions:width>2.5?2:1,mullionWidth:.035,interaction:fixed?false:{mode:'swing',hingeSide:'left',openAngle:65,initiallyOpen:false}})
    this.comp(c)
    if (trim && !door) {
      const angle = -Math.atan2(uz,ux), p = [center[0]+uz*.13,bottom-.055,center[1]-ux*.13]
      this.box(id+'_sill',p,[width+.25,.11,.43],'stone',[0,angle,0])
      this.box(id+'_head',[p[0],bottom+height+.08,p[2]],[width+.25,.16,.35],'stone',[0,angle,0])
    }
    return c
  }
  roof(id, r, eave, rise, material='clay', type='hip') {
    const [a,b,c,d] = r
    return this.add({type:'roof',id,roofType:type,position:[(a+b)/2,eave,(c+d)/2],span:b-a,depth:d-c,height:rise,thickness:.18,material,...(type==='gable'?{ridgeAxis:'x'}:{})})
  }
  rail(id, path, material='metal', glass=true) { return this.comp({type:'railing',id,path,height:1.02,postSpacing:1.3,postRadius:.022,railRadius:.025,railLevels:[1],material,...(glass?{infillType:'glass',infillMaterial:'glass',infillThickness:.012}: {})}) }
  stair(id, a, b, width, count, material='stone') { return this.add({type:'stair',id,from:a,to:b,width,stepCount:count,stepHeight:(b[1]-a[1])/count,stepDepth:Math.hypot(b[0]-a[0],b[2]-a[2])/count,material}) }
  lamp(id, p, intensity=13, distance=5, spot=false) {
    const e = this.box(id,p,[.12,.055,.12],'glow')
    e.lightSource={lightType:spot?'spot':'point',intensity,distance,color:[1,.82,.61],offset:[0,-.065,0],...(spot?{angle:58,direction:[0,-1,0]}:{})}
    return e
  }
  pendant(id, p, ceiling, intensity=18) {
    this.cylinder(id+'_cord',[p[0],(p[1]+ceiling)/2,p[2]],.012,ceiling-p[1],'metal')
    this.cylinder(id+'_shade',[p[0],p[1]+.07,p[2]],.2,.12,'metal',.13)
    this.lamp(id,p,intensity,5)
  }
  sofa(id, x, y, z, width=2.6) {
    this.box(id+'_base',[x,y+.16,z],[width,.18,.92],'walnut')
    this.box(id+'_seat',[x,y+.37,z+.03],[width-.18,.23,.82],'linen')
    this.box(id+'_back',[x,y+.68,z-.37],[width,.48,.18],'linen')
    for (const side of [-1,1]) this.box(id+'_arm_'+side,[x+side*(width/2-.09),y+.54,z],[.18,.4,.95],'linen')
    for (let i=0;i<3;i++) this.box(id+'_cushion_'+i,[x+(i-1)*.64,y+.65,z-.22],[.55,.35,.13],'linen',[.12,0,0])
  }
  bed(id, x, y, z, width=1.7) {
    this.box(id+'_base',[x,y+.17,z],[width+.08,.3,2.12],'oak')
    this.box(id+'_mattress',[x,y+.43,z],[width,.25,2.05],'linen')
    this.box(id+'_head',[x,y+.73,z-.97],[width+.28,1.1,.12],'walnut')
    for(const s of [-1,1])this.box(id+'_pillow_'+s,[x+s*width*.23,y+.6,z-.6],[width*.4,.16,.45],'linen')
    this.box(id+'_cover',[x,y+.57,z+.32],[width+.02,.035,1.35],'linen')
    for(const s of [-1,1]) { this.box(id+'_table_'+s,[x+s*(width/2+.37),y+.25,z-.65],[.52,.5,.52],'oak');this.lamp(id+'_bedlamp_'+s,[x+s*(width/2+.37),y+.7,z-.65],3,2.8) }
  }
  table(id,x,y,z,width=1.8,depth=.9) { return this.add({type:'furniture',id,subtype:'table',position:[x,y,z],dimensions:{width,depth,height:.75},material:'oak'}) }
  chair(id,x,y,z,rotation=0) { return this.add({type:'furniture',id,subtype:'chair',position:[x,y,z],dimensions:{width:.52,depth:.56,height:.86},rotation:[0,rotation,0],material:'walnut'}) }
  tree(id,x,z,height=3) {
    this.cylinder(id+'_trunk',[x,height*.43,z],.095,height*.86,'walnut',.065)
    for(let i=0;i<5;i++){const a=i*2.4;this.add({type:'primitive',id:id+'_crown_'+i,shape:'sphere',position:[x+Math.cos(a)*.48,height*(.72+i*.045),z+Math.sin(a)*.48],radius:.7,segments:12,heightSegments:8,scale:[1,.56,1],material:'leaf'})}
  }
  planter(id,r,top=.43) {
    const [a,b,c,d]=r;this.box(id+'_body',[(a+b)/2,top/2,(c+d)/2],[b-a,top,d-c],'stone');this.slab(id+'_soil',[a+.09,b-.09,c+.09,d-.09],top+.015,.025,'soil')
    for(let i=0;i<6;i++){const x=a+.2+(b-a-.4)*i/5;this.add({type:'primitive',id:id+'_shrub_'+i,shape:'sphere',position:[x,top+.19,(c+d)/2],radius:.26,segments:10,heightSegments:6,scale:[1,.8,1],material:'leaf'})}
  }
  pond(id,r,waterY,depth) {
    const [a,b,c,d]=r
    this.slab(id+'_bottom',r,waterY-depth,.14,'paving')
    for(const [suffix,p,dim] of [['n',[(a+b)/2,waterY-depth/2,c-.07],[b-a+.28,depth,.14]],['s',[(a+b)/2,waterY-depth/2,d+.07],[b-a+.28,depth,.14]],['w',[a-.07,waterY-depth/2,(c+d)/2],[.14,depth,d-c]],['e',[b+.07,waterY-depth/2,(c+d)/2],[.14,depth,d-c]]])this.box(id+'_wall_'+suffix,p,dim,'stone')
    this.slab(id+'_water',r,waterY,.035,'water')
    this.slab(id+'_coping',[a-.3,b+.3,c-.3,d+.3],waterY+.14,.12,'stone',[r])
  }
  sign(id,text,p,width=2.1,material='walnut') { const e=this.box(id,p,[width,.35,.065],material);e.label={text,color:[.94,.87,.66],fontFamily:'serif'} }
  bathroom(id,r,y) {
    const [a,b,c,d]=r
    this.box(id+'_vanity',[(a+b)/2,y+.4,c+.4],[Math.min(1.25,b-a-.3),.8,.6],'oak')
    this.box(id+'_basin',[(a+b)/2,y+.85,c+.4],[.7,.1,.46],'quartz')
    this.cylinder(id+'_tap',[(a+b)/2,y+.98,c+.21],.023,.22,'metal')
    this.cylinder(id+'_wc',[a+.48,y+.25,d-.7],.23,.5,'quartz')
    this.box(id+'_cistern',[a+.48,y+.58,d-.95],[.43,.48,.17],'quartz')
    this.slab(id+'_shower_tray',[b-1.15,b-.1,d-1.25,d-.12],y+.04,.04,'paving')
    this.box(id+'_shower_screen',[b-1.15,y+1.05,d-.72],[.012,2.1,1.05],'glass')
  }
  fan(id,p,control) { this.comp({type:'fan',id,position:p,controlPosition:control,radius:.63,bladeCount:3,drop:.38,rpm:155,initiallyOn:false,material:'walnut',frameMaterial:'metal'}) }
  finish() {
    const used = new Set()
    for(const e of [...this.data.geometry.elements,...this.data.geometry.components])for(const [k,v]of Object.entries(e))if((k==='material'||k.endsWith('Material'))&&typeof v==='string')used.add(v)
    this.data.materials=Object.fromEntries(Object.entries(this.data.materials).filter(([k])=>used.has(k)))
    return this.data
  }
}

function modern() {
  const b=new Blueprint('澄屿叠院 · 现代悬挑别墅'),F=.36,U=3.76,pool=[0,11,7,10.5]
  b.slab('site',[-16,16,-14,14],.04,.24,'grass',[pool]);b.pond('pool',pool,.035,1.08)
  b.slab('ground_slab',[-9.14,7.74,-4.64,3.64],F,.25,'paving')
  b.slab('upper_slab',[-9.14,10.14,-4.64,5.8],U,.2,'oak',[[-4.5,-3.1,-2.7,3.1],[-8.15,-5.85,-4.31,-2.17]])
  const lower=b.room('lower',[-9,7.6,-4.5,3.5],F,U-.2,'stone'), upper=b.room('upper',[-9,10,-4.5,4.2],U,7.0)
  b.opening('entry',lower.s,[-2.2,3.5],F,1.35,2.6,{door:true,leaf:'walnut'})
  b.opening('living_glass',lower.s,[3.5,3.5],F+.05,6.6,2.85,{fixed:true})
  b.opening('guest_glass',lower.s,[-7,3.5],F+.55,2.5,2.1,{trim:true})
  b.opening('lower_east_glass',lower.e,[7.6,-.2],F+.05,5.4,2.85,{fixed:true})
  b.opening('kitchen_window',lower.n,[3,-4.5],F+1.2,5.6,1.4)
  b.opening('guest_west_window',lower.w,[-9,.8],F+.8,2.4,1.8)
  b.opening('upper_south_door',upper.s,[-3.8,4.2],U,1.3,2.6,{door:true})
  for(const x of [.4,6.8])b.opening('upper_south_'+x,upper.s,[x,4.2],U+.5,3.7,2.25,{fixed:true})
  b.opening('upper_east_window',upper.e,[10,-.6],U+.5,5.5,2.25,{fixed:true})
  for(const x of [.4,6.8])b.opening('upper_north_'+x,upper.n,[x,-4.5],U+.8,3.6,1.95)
  b.roof('flat_roof',[-9.5,10.5,-5,4.65],7,.22,'concrete','flat')
  for(const z of [-4.95,4.6])b.box('roof_lip_'+z,[.5,7.32,z],[20,.18,.12],'metal')
  b.box('upper_fascia',[.5,3.56,5.85],[19.6,.24,.13],'concrete')
  b.rail('terrace_guard',[[-9.05,U,4.25],[-9.05,U,5.65],[10.05,U,5.65],[10.05,U,4.25]])
  const guest=b.wall('guest_partition',[-5,-.75],[-5,3.5],F,U-.2)
  b.opening('guest_door',guest,[-5,1.8],F,.9,2.2,{door:true,leaf:'oak'})
  b.wall('guest_back',[-9,-.75],[-5,-.75],F,U-.2)
  b.bed('guest_bed',-7,F,1.0,1.5)
  const bedrooms=b.wall('bedrooms_front',[-2.8,1.4],[10,1.4],U,7)
  for(const x of [.4,6.8])b.opening('bedroom_door_'+x,bedrooms,[x,1.4],U,.9,2.25,{door:true,leaf:'oak'})
  b.wall('bedroom_divider',[3.8,-4.5],[3.8,1.4],U,7)
  b.wall('bedroom_west',[-2.8,-4.5],[-2.8,1.4],U,7)
  b.wall('bath_north',[-9,.2],[-5.2,.2],U,7)
  const bathDoor=b.wall('bath_east',[-5.2,.2],[-5.2,4.2],U,7)
  b.opening('bath_door',bathDoor,[-5.2,2.3],U,.85,2.2,{door:true,leaf:'oak'})
  b.opening('bath_window',upper.w,[-9,2.1],U+1.2,1.7,1.2)
  b.bathroom('bath',[-8.8,-5.4,.4,4],U)
  b.bed('master',6.8,U,-1.45);b.bed('second',.45,U,-1.45,1.5)
  b.box('master_wardrobe',[9.45,U+1.15,-1.4],[.65,2.3,3.3],'oak')
  b.stair('main_stair',[-3.8,F,-2.5],[-3.8,U,3.1],1.1,20,'concrete')
  b.rail('stair_guard',[[-4.5,U,3.1],[-4.5,U,-2.7],[-3.1,U,-2.7],[-3.1,U,3.1]],'metal',false)
  b.rail('stair_handrail',[[-4.38,F+.1,-2.5],[-4.38,U,3.1]],'metal',false)
  const landingWalls=[]
  for(let f=0;f<2;f++){const y=F+3.4*f;landingWalls.push(b.wall('shaft_front_'+f,[-8.15,-2.17],[-5.85,-2.17],y,y+3.2,'concrete',.14).id)}
  b.wall('shaft_left',[-8.15,-4.31],[-8.15,-2.17],F,7,'concrete',.14);b.wall('shaft_right',[-5.85,-2.17],[-5.85,-4.31],F,7,'concrete',.14);b.wall('shaft_back',[-5.85,-4.31],[-8.15,-4.31],F,7,'concrete',.14)
  b.comp({type:'elevator',id:'courtyard_lift',position:[-7,F,-3.15],dimensions:{width:1.8,depth:1.8,height:2.6},floorHeight:3.4,floorCount:2,initialFloor:0,landingWalls,material:'wall',frameMaterial:'metal',doorMaterial:'metal',floorMaterial:'quartz'})
  b.sofa('living_sofa',3.6,F,.05,2.8);b.table('coffee',3.6,F,1.75,1.45,.7)
  b.box('kitchen_base',[3,F+.44,-3.95],[5.7,.88,.66],'oak');b.box('kitchen_top',[3,F+.91,-3.95],[5.8,.08,.72],'quartz')
  b.box('island',[3.4,F+.45,-1.5],[2.8,.9,.85],'walnut');b.box('island_top',[3.4,F+.94,-1.5],[2.95,.08,1],'quartz')
  b.box('sink',[3.8,F+.989,-1.5],[.65,.018,.45],'metal');b.table('dining',.1,F,-.5,1.8,.88)
  for(let i=0;i<2;i++){b.chair('dining_n'+i,-.4+i,F,-1.35);b.chair('dining_s'+i,-.4+i,F,.35,Math.PI)}
  b.pendant('living_pendant',[3.6,2.95,1.7],3.56,20);b.lamp('kitchen_light',[3,3.47,-3],18,6,true)
  b.fan('living_fan',[4.2,3.1,-.4],[7.43,1.5,-2.6])
  b.lamp('porch_light',[-2.2,3.35,3.25],12,5,true);b.lamp('upper_terrace_light',[1.8,6.85,4.35],15,7,true)
  b.slab('south_deck',[-9.5,11.8,3.7,6.65],.18,.14,'oak');b.slab('east_pool_deck',[11.4,13,6.65,11.4],.18,.14,'oak')
  b.stair('entry_steps',[-2.2,.04,4.8],[-2.2,F,3.64],1.8,2)
  b.slab('arrival_path',[-3.2,-1.2,4.8,13],.045,.08,'paving')
  b.box('bench',[7,.45,5.2],[2.5,.28,.7],'oak');b.planter('terrace_planter',[-8.9,-6.4,4.1,5.35])
  b.sign('name','澄屿叠院',[-4.1,2.6,3.68],2.2)
  for(const [x,z,h]of [[-12,-7,4],[12,-6,3.6],[-11,9,3.5],[10,12,2.8]])b.tree('tree_'+x+'_'+z,x,z,h)
  b.planter('low_garden',[3,7,11.6,12.5]);b.lamp('garden_light',[-10,.55,6],6,4)
  return b.finish()
}

function chinese() {
  const b=new Blueprint('松雨回廊 · 新中式合院'),F=.32,pond=[-1.65,1.65,-.5,3.3]
  b.data.materials.wall.baseColor=[.87,.85,.78];b.data.materials.clay={...presets.tiles_terracotta,baseColor:[.23,.25,.25],roughness:.88}
  b.slab('site',[-15,15,-15,15],.03,.23,'grass',[pond]);b.pond('court_pond',pond,.035,.4)
  b.slab('court',[-10.5,10.5,-10.6,9.5],.16,.1,'paving',[pond])
  b.slab('north_floor',[-8.14,8.14,-10.14,-3.86],F,.22,'oak')
  b.slab('west_floor',[-10.14,-5.36,-3.54,6.14],F,.22,'oak');b.slab('east_floor',[5.36,10.14,-3.54,6.14],F,.22,'oak')
  const hall=b.room('hall',[-8,8,-10,-4],F,3.32),west=b.room('west',[-10,-5.5,-3.4,6],F,3.22),east=b.room('east',[5.5,10,-3.4,6],F,3.22)
  b.opening('hall_door',hall.s,[0,-4],F,3.4,2.5,{door:true,leaf:'glass',frame:'walnut'})
  for(const x of [-5.2,5.2]){b.opening('hall_window_'+x,hall.s,[x,-4],F+.55,3,1.85,{frame:'walnut',trim:true});b.opening('hall_back_'+x,hall.n,[x,-10],F+.9,2.4,1.5,{frame:'walnut'})}
  for(const [wall,x]of [[west.e,-5.5],[east.w,5.5]])for(const z of [-1.6,3.8])b.opening('wing_door_'+x+'_'+z,wall,[x,z],F,1.15,2.3,{door:true,leaf:'oak',frame:'walnut'})
  for(const [wall,x]of [[west.w,-10],[east.e,10]])for(const z of [-1.5,3.8])b.opening('wing_window_'+x+'_'+z,wall,[x,z],F+.85,1.7,1.55,{frame:'walnut',trim:true})
  const wpart=b.wall('west_divider',[-10,1.1],[-5.5,1.1],F,3.22);b.opening('west_internal',wpart,[-7.5,1.1],F,.9,2.2,{door:true,leaf:'oak',frame:'walnut'})
  const epart=b.wall('east_divider',[5.5,1.1],[10,1.1],F,3.22);b.opening('east_internal',epart,[7.5,1.1],F,.9,2.2,{door:true,leaf:'oak',frame:'walnut'})
  b.bed('west_bed_n',-7.7,F,-1.35,1.45);b.bed('west_bed_s',-7.7,F,3.7,1.6)
  b.box('tea_platform',[0,F+.1,-6.3],[4.4,.2,2.4],'walnut');b.table('tea_table',0,F+.2,-6.3,1.7,.8)
  b.chair('tea_chair_w',-1.45,F+.2,-6.3,-Math.PI/2);b.chair('tea_chair_e',1.45,F+.2,-6.3,Math.PI/2)
  b.sofa('hall_sofa',-5.4,F,-8.8,2.6);b.box('hall_cabinet',[2.7,F+.45,-9.4],[2.3,.9,.75],'walnut')
  const bathWall=b.wall('hall_service_west',[4.3,-10],[4.3,-7.3],F,3.32)
  b.wall('hall_service_south',[4.3,-7.3],[8,-7.3],F,3.32)
  b.opening('service_door',bathWall,[4.3,-8.6],F,.85,2.2,{door:true,leaf:'oak',frame:'walnut'})
  b.bathroom('service',[4.5,7.8,-9.8,-7.5],F)
  b.box('east_kitchen',[9.5,F+.45,-1.2],[.72,.9,3.8],'oak');b.box('east_counter',[9.5,F+.94,-1.2],[.78,.08,3.85],'quartz')
  b.table('east_dining',7.55,F,-1.1,1.6,.85);b.chair('east_dining_1',6.4,F,-1.1,-Math.PI/2);b.chair('east_dining_2',8.7,F,-1.1,Math.PI/2)
  b.table('study_desk',7.7,F,4.9,2,.75);b.chair('study_chair',7.7,F,3.9,Math.PI)
  b.add({type:'furniture',id:'study_shelf',subtype:'bookshelf',position:[9.5,F,3],dimensions:{width:.65,depth:.35,height:2.15},rotation:[0,-Math.PI/2,0],material:'walnut'})
  b.roof('hall_roof',[-8.8,8.8,-10.8,-3.2],3.5,2.05,'clay')
  b.roof('west_roof',[-10.7,-4.8,-4.1,6.7],3.4,1.5,'clay');b.roof('east_roof',[4.8,10.7,-4.1,6.7],3.4,1.5,'clay')
  b.box('hall_ridge',[0,5.61,-7],[10,.12,.18],'stone')
  for(const x of [-4.65,4.65]) {
    b.slab('walk_'+x,[x-.7,x+.7,-4.0,7.25],F,.18,'paving')
    b.roof('corridor_roof_'+x,[x-.82,x+.82,-4,7.5],2.95,.45,'clay')
    for(let i=0;i<5;i++) {
      const z=-3.4+i*2.5
      b.box('post_base_'+x+'_'+i,[x,.47,z],[.36,.3,.36],'stone')
      b.cylinder('post_'+x+'_'+i,[x,1.84,z],.11,2.44,'walnut')
      b.box('post_cap_'+x+'_'+i,[x,2.92,z],[.48,.14,.38],'walnut')
      if(i%2===0)b.lamp('corridor_light_'+x+'_'+i,[x,2.65,z],7,4)
    }
  }
  b.slab('north_walk',[-5.35,5.35,-4.0,-2.9],F,.18,'paving');b.slab('south_walk',[-5.35,5.35,6,7.3],F,.18,'paving')
  b.slab('stone_bridge',[-.7,.7,-1.05,4.1],F,.12,'stone')
  b.slab('central_path',[-.7,.7,3.95,9.4],F,.16,'paving');b.slab('hall_approach',[-1.2,1.2,-3.95,-.9],F,.16,'paving')
  b.wall('south_screen_w',[-10.4,8.8],[-1.3,8.8],.16,2.05,'wall',.24);b.wall('south_screen_e',[1.3,8.8],[10.4,8.8],.16,2.05,'wall',.24)
  b.box('screen_cap_w',[-5.85,2.1,8.8],[9.1,.16,.38],'clay');b.box('screen_cap_e',[5.85,2.1,8.8],[9.1,.16,.38],'clay')
  for(const x of [-1.3,1.3]){b.box('gate_base_'+x,[x,.44,8.8],[.55,.56,.55],'stone');b.cylinder('gate_post_'+x,[x,1.87,8.8],.14,2.56,'walnut')}
  b.roof('gate_roof',[-2.1,2.1,7.25,10.35],3.2,1.05,'clay');b.sign('gate_name','松雨回廊',[0,2.83,8.99],1.95)
  b.stair('arrival_steps',[0,.03,10.7],[0,F,9.6],2,2)
  b.slab('gate_threshold',[-1.1,1.1,9.15,9.65],F,.16,'paving')
  b.slab('arrival_path',[-1.1,1.1,10.7,14],.035,.08,'paving')
  for(const z of [-2,4.8]){b.planter('court_planter_'+z,[-3.65,-2.1,z-.5,z+.5],.48)}
  b.tree('court_pine',2.8,3.6,3.2);b.tree('west_tree',-12,-7,3.7);b.tree('east_tree',12,-8,3.8)
  b.pendant('hall_lantern',[0,2.83,-6.3],3.32,19);b.lamp('east_lamp',[7.6,3.1,-1],13,4.8);b.lamp('study_lamp',[7.6,3.1,3.6],12,4.8)
  b.fan('hall_fan',[-3.2,2.88,-6.6],[-3.8,1.5,-4.14])
  for(const x of [-2.2,2.2])b.lamp('pond_lamp_'+x,[x,.65,.8],4,3.5)
  return b.finish()
}

function mediterranean() {
  const b=new Blueprint('栖坡陶院 · 地中海坡顶别墅'),F=.3,U=3.5
  b.data.materials.wall.baseColor=[.88,.83,.71];b.data.materials.stone.baseColor=[.65,.57,.44];b.data.materials.metal.baseColor=[.14,.17,.16]
  b.slab('site',[-16,16,-14,14],-.12,.24,'grass')
  b.slab('upper_terrace',[-12.2,12.2,-9,9],.12,.3,'paving')
  b.slab('lower_court',[-11.5,11.5,9,12.6],-.02,.2,'paving')
  b.stair('garden_steps',[0,-.02,10.1],[0,.12,9.3],4.4,1)
  b.slab('med_ground',[-6.14,6.14,-7.14,1.14],F,.22,'paving')
  b.slab('med_upper',[-6.14,6.14,-7.14,3.1],U,.2,'oak',[[-3.6,2.4,-6.15,-4.85]])
  b.slab('west_floor',[-10.14,-5.86,-3.14,7.14],F,.22,'paving');b.slab('east_floor',[5.86,10.14,-3.14,7.14],F,.22,'paving')
  const main=b.room('main',[-6,6,-7,1],F,3.3),upper=b.room('upper',[-6,6,-7,1],U,6.52)
  const wings={}
  for(const s of [-1,1]) {
    const a=s===-1?-10:6,c=s===-1?-6:10
    wings[s]={n:b.wall('wing_n_'+s,[a,-3],[c,-3],F,3.18),s:b.wall('wing_s_'+s,[c,7],[a,7],F,3.18),outer:b.wall('wing_outer_'+s,[s*10,-3],[s*10,7],F,3.18),inner:b.wall('wing_inner_'+s,[s*6,1],[s*6,7],F,3.18)}
    b.opening('wing_court_door_'+s,wings[s].inner,[s*6,4.6],F,1.4,2.45,{door:true,arched:true,leaf:'oak',frame:'stone'})
    b.opening('wing_front_window_'+s,wings[s].s,[(a+c)/2,7],F+.8,1.9,1.65,{trim:true,frame:'oak'})
    for(const z of [-.4,3.4])b.opening('wing_outer_window_'+s+'_'+z,wings[s].outer,[s*10,z],F+.8,1.7,1.65,{trim:true,frame:'oak'})
    b.roof('wing_roof_'+s,[a-.65,c+.65,-3.65,7.65],3.36,1.18,'clay')
  }
  b.opening('west_connection',main.w,[-6,-.9],F,1.05,2.3,{door:true,leaf:'oak',frame:'stone'})
  b.opening('east_connection',main.e,[6,-.9],F,1.05,2.3,{door:true,leaf:'oak',frame:'stone'})
  b.opening('entry_arch',main.s,[1.35,1],F,1.7,2.55,{door:true,arched:true,leaf:'oak',frame:'stone'})
  for(const x of [-4,-1.4,4.2])b.opening('front_window_'+x,main.s,[x,1],F+.75,1.8,1.75,{trim:true,frame:'oak'})
  b.opening('upper_terrace_arch',upper.s,[1.35,1],U,1.7,2.55,{door:true,arched:true,frame:'stone'})
  for(const x of [-3.7,4.2])b.opening('upper_window_'+x,upper.s,[x,1],U+.7,1.9,1.75,{trim:true,frame:'oak'})
  for(const [wall,x]of [[upper.w,-6],[upper.e,6]])b.opening('upper_side_'+x,wall,[x,-2.6],U+.8,2.3,1.6,{trim:true,frame:'oak'})
  for(const x of [-4,0,4])b.opening('back_window_'+x,main.n,[x,-7],F+1.3,1.8,1.1,{frame:'oak'})
  for(const x of [-3.9,3.9])b.opening('upper_back_'+x,upper.n,[x,-7],U+1.1,1.9,1.3,{frame:'oak'})
  b.roof('main_gable',[-6.65,6.65,-7.65,1.65],6.7,2.15,'clay','gable')
  b.box('ridge_cap',[0,8.9,-3],[13.2,.12,.22],'clay')
  // 坡面细脊按真实双坡高程推导，避免把水平线条当贴坡瓦垄。
  for(const x of [-5.7,-3.8,-1.9,0,1.9,3.8,5.7]) for(const side of [-1,1]) {
    const path=[]
    for(let i=0;i<=6;i++){const z=-3+side*(4.65*i/6),y=6.7+2.15*(1-Math.abs(z+3)/4.65)+.045;path.push([x,y,z])}
    b.add({type:'primitive',id:'roof_rib_'+x+'_'+side,shape:'profile_sweep',position:[0,0,0],path,profile:[[-.035,-.02],[.035,-.02],[.035,.02],[-.035,.02]],closedProfile:true,caps:true,material:'clay'})
  }
  b.stair('main_stair',[-3.4,F,-5.5],[2.4,U,-5.5],1.1,20,'stone')
  b.rail('stair_upper_guard',[[-3.6,U,-4.85],[-3.6,U,-6.15],[2.4,U,-6.15]],'metal',false)
  b.rail('stair_inner_guard',[[-3.6,U,-4.85],[2.4,U,-4.85]],'metal',false)
  const upperDivider=b.wall('upper_divider',[0,-4.4],[0,1],U,6.52)
  b.opening('upper_connect',upperDivider,[0,-2.7],U,.9,2.25,{door:true,leaf:'oak',frame:'stone'})
  b.bed('upper_west',-3,U,-1.7);b.bed('upper_east',3.3,U,-1.7,1.6)
  b.bed('west_guest',-8,F,3.9,1.6)
  const westPartition=b.wall('guest_divider',[-10,1.2],[-6,1.2],F,3.18)
  b.opening('guest_internal',westPartition,[-8,1.2],F,.9,2.2,{door:true,leaf:'oak'})
  b.box('guest_storage',[-9.5,F+1.05,-.8],[.6,2.1,2.5],'oak')
  b.box('kitchen',[9.5,F+.45,.3],[.72,.9,5.5],'oak');b.box('kitchen_counter',[9.5,F+.94,.3],[.8,.08,5.6],'quartz')
  b.table('east_dining',7.5,F,4.4,1.6,.9);b.chair('dining_1',7.5,F,3.3);b.chair('dining_2',7.5,F,5.5,Math.PI)
  b.sofa('main_sofa',-2,F,-1.3,2.8);b.table('main_coffee',-2,F,.25,1.5,.7)
  b.wall('bath_north',[-6,-4.5],[-3.7,-4.5],F,3.3);b.wall('bath_south',[-3.7,-1.9],[-6,-1.9],F,3.3)
  const bathWall=b.wall('bath_east',[-3.7,-4.5],[-3.7,-1.9],F,3.3)
  b.opening('bath_door',bathWall,[-3.7,-3.15],F,.85,2.2,{door:true,leaf:'oak'})
  b.bathroom('bath',[-5.8,-3.9,-4.3,-2.1],F)
  b.box('bookcase',[5.5,F+1.1,-3.9],[.55,2.2,2.2],'walnut')
  b.table('study',3.4,F,-3.6,1.7,.8);b.chair('study_seat',3.4,F,-2.65,Math.PI)
  // 石柱、压顶和四跨弧拱是独立构造，中央跨对准入户门，柱不挡门。
  const posts=[-5.4,-2.7,0,2.7,5.4]
  for(let i=0;i<posts.length;i++) {
    const x=posts[i];b.box('arcade_base_'+i,[x,F+.14,2.65],[.47,.28,.47],'stone')
    b.cylinder('arcade_column_'+i,[x,F+.95,2.65],.16,1.62,'stone',.145)
    b.box('arcade_capital_'+i,[x,1.98,2.65],[.48,.2,.45],'stone')
  }
  for(let i=0;i<4;i++) {
    const cx=(posts[i]+posts[i+1])/2,path=[]
    for(let j=0;j<=20;j++){const a=Math.PI*j/20;path.push([cx+1.35*Math.cos(a),1.96+1.15*Math.sin(a),2.65])}
    b.add({type:'primitive',id:'arcade_arch_'+i,shape:'profile_sweep',position:[0,0,0],path,profile:[[-.13,-.13],[.13,-.13],[.13,.13],[-.13,.13]],closedProfile:true,caps:true,material:'stone'})
  }
  b.box('arcade_lintel',[0,3.25,2.65],[11.4,.1,.38],'stone')
  b.rail('front_terrace_guard',[[-5.85,U,1.2],[-5.85,U,2.95],[5.85,U,2.95],[5.85,U,1.2]],'metal',false)
  b.stair('porch_steps',[1.35,.12,4.1],[1.35,F,3.1],1.9,1)
  b.slab('porch',[-5.85,5.85,1.15,3.1],F,.16,'paving')
  b.sign('name_board','栖坡陶院',[3.8,2.85,1.18],1.8,'stone')
  b.planter('courtyard_bed',[-4.8,-1.5,4.5,6.6],.52);b.tree('olive',-3.2,5.6,3.25)
  b.planter('east_garden',[1.8,4.8,6.7,7.7],.45)
  b.box('garden_bench',[2.7,.48,5.4],[2.4,.32,.7],'oak')
  for(const [x,z,h]of [[-13,3,3.5],[13,5,3.7],[-12,-9,4],[12,-9,3.8]])b.tree('olive_'+x+'_'+z,x,z,h)
  b.pendant('living_lamp',[-2,2.65,-1],3.3,18);b.lamp('kitchen_lamp',[8,3.05,1],17,6);b.lamp('upper_lamp',[1.7,6.4,-3.7],16,5)
  for(const x of [-3.8,1.35,4.1])b.lamp('arcade_lamp_'+x,[x,3.18,1.8],10,5,true)
  b.fan('dining_fan',[7.8,2.75,4.4],[6.15,1.4,2.5])
  return b.finish()
}

const cases=[['01-澄屿叠院-现代悬挑',modern],['02-松雨回廊-新中式合院',chinese],['03-栖坡陶院-地中海坡顶',mediterranean]]
const records=[]
for(const [directory,design]of cases) {
  const bp=design(),text=JSON.stringify(bp)+'\n',target=join(here,directory)
  await mkdir(target,{recursive:true});const filename=bp.meta.name.split(' · ')[0]+'.wild'
  await writeFile(join(target,filename),text)
  records.push({directory,file:filename,name:bp.meta.name,bytes:Buffer.byteLength(text),sha256:createHash('sha256').update(text).digest('hex'),elements:bp.geometry.elements.length,components:bp.geometry.components.length,materials:Object.keys(bp.materials).length})
}
await writeFile(join(here,'生成清单.json'),JSON.stringify({method:'原创设计 + 确定性展开；无模型API、外部图片和GLB',records},null,2)+'\n')
console.log(JSON.stringify(records,null,2))
