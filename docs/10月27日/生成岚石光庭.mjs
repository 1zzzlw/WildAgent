import { readFile, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
const here = new URL('./', import.meta.url)
const presets = JSON.parse(await readFile(new URL('../../wild-core/material-presets.json', here), 'utf8'))
const materials = Object.fromEntries(presets.map(p => [p.id, p.material]))
const plain = (baseColor, roughness = .85) => ({ baseColor, roughness, metallic: 0, albedo: 1, lightingCondition: 'D65_noon' })
materials.dark_metal = { ...materials.metal_brushed, baseColor: [.085, .105, .11], roughness: .36 }
materials.leaf = { ...plain([.13,.23,.12]), surfaceFamily: 'neutral' }
materials.soil = plain([.22,.19,.13])
materials.ground_grass = { ...plain([.24,.30,.18],.96), surfaceFamily:'neutral' }
materials.water = { ...materials.glass_clear, baseColor: [.16,.42,.39], ior: 1.333, roughness: .055, thickness: .85, attenuationColor: [.3,.68,.6], attenuationDistance: 3 }
materials.emitter = { ...plain([1,.81,.52], .25), emissive: [1,.67,.32], emissiveIntensity: 2 }
const elements = [], components = []
const box = (id, position, dimensions, material, extra = {}) => elements.push({ type:'primitive', id, shape:'box', position, dimensions, material, ...extra })
const slab = (id,x1,z1,x2,z2,bottom,thickness,material) => elements.push({type:'floor',id,from:[x1,bottom,z1],to:[x2,bottom,z2],thickness,material})
const wall = (id,x1,z1,x2,z2,y,height,material='plaster_lime',thickness=.24) => elements.push({type:'wall',id,from:[x1,y,z1],to:[x2,y+height,z2],thickness,material})
const beam = (id,from,to,width,height,material) => elements.push({type:'beam',id,from,to,crossSection:'rect',width,height,material})
const furnish = (id,subtype,position,width,depth,height,material,rotation=0) => elements.push({type:'furniture',id,subtype,position,dimensions:{width,depth,height},material,rotation:[0,rotation,0]})
const window = (id,parentWall,along,y,width,height,glass='glass_clear',mullions=1,interaction=false) => components.push({type:'window',id,parentWall,from:[along,y,0],width,height,frameWidth:.045,frameDepth:.26,glassDepth:.012,verticalMullions:mullions,horizontalMullions:0,frameMaterial:'dark_metal',glassMaterial:glass,interaction})
const door = (id,parentWall,along,y,width=1.05,height=2.5,material='planks_walnut') => components.push({type:'door',id,parentWall,from:[along,y,0],width,height,frameWidth:.05,frameDepth:.26,leafMaterial:material,frameMaterial:'dark_metal',interaction:{mode:'swing',openAngle:100}})
const lamp = (id,position,intensity=18,distance=6,type='point',direction=[0,-1,0]) => {
 box(id,position,[.1,.04,.1],'emitter',{lightSource:{lightType:type,color:[1,.77,.51],intensity,distance,direction,angle:55}})
 if(type==='spot')for(const [side,axis] of [[-1,0],[1,0],[-1,2],[1,2]]){
  const p=[...position];p[axis]+=side*.065;p[1]+=.08
  box(id+'_trim_'+axis+'_'+side,p,axis===0?[.025,.16,.15]:[.15,.16,.025],'dark_metal')
 }
}
const y0=.32,y1=3.72,fh=3.4
// 土地、台地与水庭。地坪留真洞，水面下有池底与四周池壁。
slab('site',-15,-13,15,14,-.23,.2,'ground_grass')
slab('plinth_north',-8.75,-7.25,8.75,.25,-.08,.1,'concrete_fair')
slab('plinth_west',-8.75,.25,-2.25,7.25,-.08,.1,'concrete_fair')
slab('court_deck',-2.25,.25,9,9,.02,.3,'planks_oak')
// 泳池占地在木平台之外，边缘压顶独立，避免实心地坪盖住水体。
slab('pool_bed',.7,9.15,8.5,12.6,-1.02,.15,'tiles_limestone')
for (const [id,p,d] of [['pool_w',[.7,-.38,10.875],[.15,1.15,3.6]],['pool_e',[8.5,-.38,10.875],[.15,1.15,3.6]],['pool_n',[4.6,-.38,9.15],[7.8,1.15,.15]],['pool_s',[4.6,-.38,12.6],[7.8,1.15,.15]]]) box(id,p,d,'tiles_limestone')
slab('pool_water',.8,9.25,8.4,12.5,.07,.035,'water')
for (const z of [9.07,12.68]) box('pool_coping_'+z,[4.6,.24,z],[8.2,.16,.22],'stone_travertine')
for (const x of [.59,8.61]) box('pool_coping_'+x,[x,.24,10.875],[.22,.16,3.8],'stone_travertine')
for(let i=0;i<8;i++)slab('entry_paver_'+i,-8.4+i*.74,7.75,-7.82+i*.74,8.85,.03,.12,'tiles_terracotta')
// L形楼板：二层同时留出电梯和楼梯的贯通井洞。
const footprint=[[0,0],[17,0],[17,7],[6,7],[6,14],[0,14]]
for(const [level,y] of [[0,y0],[1,y1]]){
 elements.push({type:'floor',id:'floor_'+level,shape:'polygon',from:[-8.5,y-.3,-7],thickness:.3,polygon:footprint,...(level?{holes:[[[1.05,1.35],[3.55,1.35],[3.55,3.65],[1.05,3.65]],[[5,.57],[10.6,.57],[10.6,1.83],[5,1.83]]]}:{}),material:level?'planks_oak':'tiles_limestone'})
 wall('north_'+level,-8.5,-7,8.5,-7,y,3.1)
 wall('east_'+level,8.5,-7,8.5,0,y,3.1)
 wall('south_main_'+level,-2.5,0,8.5,0,y,3.1)
 wall('west_'+level,-8.5,-7,-8.5,7,y,3.1)
 wall('court_west_'+level,-2.5,0,-2.5,7,y,3.1,'stone_travertine')
 wall('south_west_'+level,-8.5,7,-2.5,7,y,3.1)
 // 各层完整井壁；编译器在前墙切层门洞。
 wall('shaft_back_'+level,-7.42,-5.67,-4.98,-5.67,y,3.1,'concrete_fair',.18)
 wall('shaft_left_'+level,-7.42,-5.67,-7.42,-3.47,y,3.1,'concrete_fair',.18)
 wall('shaft_right_'+level,-4.98,-5.67,-4.98,-3.47,y,3.1,'concrete_fair',.18)
 wall('shaft_front_'+level,-7.42,-3.47,-4.98,-3.47,y,3.1,'stone_travertine',.24)
 window('north_ribbon_'+level,'north_'+level,10.7,y+.8,5.3,1.8,'glass_clear',3)
 window('east_glazing_'+level,'east_'+level,.55,y+.1,5.9,2.75,'glass_clear',3)
 window('living_glazing_'+level,'south_main_'+level,1.4,y+.08,8.9,2.82,'glass_clear',4)
 window('court_glazing_'+level,'court_west_'+level,.65,y+.25,5.7,2.6,'glass_clear',3)
 window('west_ribbon_'+level,'west_'+level,8.7,y+.75,3.9,1.8,'glass_clear',2)
 window('south_suite_'+level,'south_west_'+level,.6,y+.25,4.8,2.6,'glass_clear',2)
 // 室内西翼卧室隔墙和入口。
 wall('suite_partition_'+level,-8.5,.1,-2.5,.1,y,3.1)
 door('suite_door_'+level,'suite_partition_'+level,4.55,y,.95)
 // 分层压顶、窗前挑檐与天花。
 for(const [name,pos,dim] of [['front',[3,y+3.1,.25],[11.5,.16,.24]],['back',[0,y+3.1,-7.25],[17.6,.16,.24]],['east',[8.75,y+3.1,-3.5],[.24,.16,7.5]],['west',[-8.75,y+3.1,0],[.24,.16,14.6]],['wing_s',[-5.5,y+3.1,7.25],[6.5,.16,.24]]])box('fascia_'+level+'_'+name,pos,dim,'stone_travertine')
}
// 独立薄天花饰面避免上层木地板材质同时变成首层木顶；保留交通井洞。
elements.push({type:'floor',id:'ceiling_main_0',shape:'polygon',from:[-8.5,3.405,-7],thickness:.014,polygon:footprint,holes:[[[1.05,1.35],[3.55,1.35],[3.55,3.65],[1.05,3.65]],[[5,.57],[10.6,.57],[10.6,1.83],[5,1.83]]],material:'plaster_lime'})
slab('ceiling_main_1',-8.5,-7,8.5,0,6.8,.015,'plaster_lime')
slab('ceiling_west_1',-8.5,0,-2.5,7,6.8,.015,'plaster_lime')
// 首层入口在南立面左端，门洞独立于落地玻璃。
door('entry','south_main_0',.15,y0,1.05,2.65)
door('terrace_door','south_main_1',.15,y1,1.05,2.65,'glass_clear')
// 二层临水露台、栏杆。顶部平屋面与首层楼板均真实覆盖空间。
slab('terrace',-2.5,.15,8.65,2.4,3.42,.3,'tiles_limestone')
components.push({type:'railing',id:'terrace_rail',path:[[-2.5,y1,2.4],[8.65,y1,2.4],[8.65,y1,.15]],height:1.05,postSpacing:1.4,postRadius:.018,railRadius:.018,material:'dark_metal',infillType:'glass',infillMaterial:'glass_clear'})
elements.push({type:'roof',id:'roof_main',roofType:'flat',span:17.8,depth:7.6,height:.16,thickness:.18,position:[0,6.82,-3.5],material:'concrete_fair'})
elements.push({type:'roof',id:'roof_west',roofType:'flat',span:6.6,depth:7,height:.16,thickness:.18,position:[-5.5,6.82,3.8],material:'concrete_fair'})
// 钢木薄片遮阳，不盖住庭院。竖向石柱支撑上方平台和木格栅。
for(const x of [-2.5,2.7,8.5])box('court_column_'+x,[x,1.87,2.35],[.22,3.1,.22],'stone_travertine')
beam('pergola_front',[-2.5,3.4,6.7],[8.5,3.4,6.7],.16,.24,'dark_metal')
for(const x of [-2.5,8.5])box('pergola_post_'+x,[x,1.87,6.7],[.14,3.1,.14],'dark_metal')
for(let i=0;i<27;i++)box('pergola_slat_'+i,[-2.5+i*11/26,3.55,4.55],[.055,.16,4.5],'planks_walnut')
for(let i=0;i<15;i++)box('west_screen_'+i,[-2.25,5.29,.65+i*.38],[.13,2.8,.045],'planks_walnut')
// 主交通：楼梯上沿与二层完成面严格相同；踏步与扶手各自有实体。
elements.push({type:'stair',id:'main_stair',from:[-3.5,y0,-5.8],to:[2.1,y1,-5.8],width:1.1,stepCount:20,stepHeight:.17,stepDepth:.28,material:'planks_oak'})
for(const z of [-6.4,-5.2]){
 beam('stair_rail_'+z,[-3.5,y0+1,-5.8+(z+5.8)],[2.1,y1+1,z],.035,.045,'dark_metal')
 for(let i=0;i<=10;i++)box('stair_post_'+z+'_'+i,[-3.5+i*.56,y0+i*.34+.5,z],[.022,1,.022],'dark_metal')
}
components.push({type:'elevator',id:'courtyard_lift',position:[-6.2,y0,-4.45],dimensions:{width:1.8,depth:1.8,height:2.55},floorHeight:fh,floorCount:2,initialFloor:0,material:'planks_walnut',frameMaterial:'dark_metal',doorMaterial:'metal_brushed',floorMaterial:'tiles_limestone',landingWalls:['shaft_front_0','shaft_front_1']})
components.push({type:'fan',id:'living_fan',position:[3.1,2.91,-2.25],radius:.7,bladeCount:3,drop:.49,rpm:170,initiallyOn:false,controlPosition:[7.7,1.45,-6.85],material:'planks_walnut',frameMaterial:'dark_metal'})
// 起居与餐厨：织物、木作、石英石和金属分别落在实际部件。
furnish('living_sofa','sofa',[4.1,y0,-3.7],3.1,1.03,.83,'fabric_linen')
furnish('lounge_chair','chair',[7.1,y0,-2.2],.8,.82,.86,'fabric_linen',-.4)
furnish('coffee_table','table',[4.2,y0,-1.75],1.45,.72,.38,'planks_walnut')
box('coffee_stone',[4.2,.73,-1.75],[1.52,.045,.76],'quartz_ivory')
box('living_rug',[4.1,.327,-2.3],[4.2,.014,2.6],'fabric_linen')
furnish('dining_table','table',[.25,y0,-2.4],2.1,.95,.76,'planks_oak')
for(const z of [-3.18,-1.62])for(const x of [-.35,.85])furnish('dining_chair_'+x+'_'+z,'chair',[x,y0,z],.48,.48,.82,'fabric_linen',z<-2?0:Math.PI)
box('island_base',[5.4,.77,-5.8],[3.1,.9,.8],'planks_walnut')
box('island_worktop',[5.4,1.25,-5.8],[3.25,.055,.92],'quartz_ivory')
box('sink',[4.75,1.28,-5.8],[.48,.02,.36],'metal_brushed')
box('hob',[6.25,1.283,-5.8],[.52,.018,.4],'dark_metal')
for(let i=0;i<5;i++)box('cabinet_handle_'+i,[4.15+i*.6,.92,-5.37],[.3,.018,.018],'metal_brushed')
// 西翼客卧、二层主卧、工作区与磨砂浴室隔屏。
for(const [level,y] of [[0,y0],[1,y1]]){
 furnish('bed_'+level,'bed',[-5.4,y,3.8],2.1,2.2,.7,'fabric_linen')
 box('headboard_'+level,[-5.4,y+.8,2.6],[2.6,1.25,.12],'planks_walnut')
 for(const x of [-7,-3.8])furnish('nightstand_'+level+'_'+x,'nightstand',[x,y,2.9],.55,.5,.5,'planks_oak')
 furnish('wardrobe_'+level,'wardrobe',[-7.8,y,5.1],2.3,.55,2.65,'planks_walnut',Math.PI/2)
}
furnish('study_table','table',[5.2,y1,-2.3],2.2,.75,.77,'planks_oak')
furnish('study_chair','chair',[5.2,y1,-1.45],.62,.6,.9,'fabric_linen',Math.PI)
furnish('study_shelf','bookshelf',[7.8,y1,-4.1],2.3,.5,2.4,'planks_walnut',Math.PI/2)
box('bath_screen',[1.1,4.9,-3.3],[.02,2.35,2.9],'glass_frosted')
box('bath_vanity',[2.2,4.17,-5.8],[1.6,.9,.65],'planks_oak')
box('bath_counter',[2.2,4.65,-5.8],[1.7,.06,.72],'quartz_grey')
furnish('terrace_seat','sofa',[5.4,y1,1.5],2.5,.8,.72,'fabric_linen',Math.PI)
furnish('deck_sofa','sofa',[4.9,y0,5.8],2.6,.95,.78,'fabric_linen',Math.PI)
furnish('deck_table','table',[4.9,y0,4.4],1.2,.65,.4,'stone_travertine')
// 夜间局部灯：全部通过正式光源与遮挡预算，发光片不代替照明。
lamp('living_downlight',[4.3,3.25,-2.4],28,6,'spot')
lamp('dining_downlight',[.1,3.25,-2.5],22,5,'spot')
lamp('bedroom_lamp',[-5.5,3.25,4],20,5,'spot')
lamp('upper_lamp',[5.1,6.65,-2.4],22,5,'spot')
lamp('upper_suite_lamp',[-5.5,6.65,4],18,5,'spot')
lamp('entry_wall_light',[-1.1,2.7,.2],14,4)
lamp('pergola_light',[2.8,3.36,4.5],22,5,'spot')
lamp('pergola_light2',[6.8,3.36,4.5],18,4,'spot')
for(const [x,z] of [[-10,4],[-10,-5],[10.4,-4],[10.4,6]]){
 box('bollard_'+x+'_'+z,[x,.38,z],[.12,.76,.12],'dark_metal');lamp('bollard_emitter_'+x+'_'+z,[x,.78,z],5,2.6)
}
// 花池与克制的景观体量，全部为参数几何。
for(const [k,x,z] of [['a',-10,4],['b',10.5,-4],['c',-10,-6],['d',10.6,6]]){
 box('planter_'+k,[x,.25,z],[1.5,.5,1.5],'stone_travertine')
 box('planter_soil_'+k,[x,.51,z],[1.32,.04,1.32],'soil')
 elements.push({type:'primitive',id:'tree_trunk_'+k,shape:'cylinder',position:[x,1.6,z],radius:.075,height:2.2,material:'planks_walnut'})
 for(let i=0;i<7;i++){const a=i*2.399;elements.push({type:'primitive',id:'canopy_'+k+'_'+i,shape:'sphere',position:[x+Math.cos(a)*.45,2.3+(i%3)*.3,z+Math.sin(a)*.45],radius:.62,scale:[1,.75,1],material:'leaf'})}
}
const blueprint={meta:{version:'1.1',type:'building',name:'岚石光庭·交互材质别墅',author:'Codex',description:'原创两层L形庭院别墅；石灰抹面、洞石、木作、物理玻璃、织物、动态吊扇、可乘电梯和夜景照明。'},geometry:{elements,components},materials,renderProfile:'default-world'}
const path=fileURLToPath(new URL('岚石光庭-交互材质别墅.wild',here))
await writeFile(path,JSON.stringify(blueprint))
console.log(JSON.stringify({path,elements:elements.length,components:components.length,materials:Object.keys(materials).length,bytes:Buffer.byteLength(JSON.stringify(blueprint))},null,2))
