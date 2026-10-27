import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFile, writeFile, mkdir, readdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { resolve, relative, join } from 'node:path'
import { launchEditorBrowser } from '../../../wild-web/scripts/editor-browser.mjs'

const root = fileURLToPath(new URL('../../../', import.meta.url))
const output = fileURLToPath(new URL('./', import.meta.url))
const threeRoot = 'docs/10月27日/渲染性能光影与三种别墅'
const projects = [
  { id:'lanshi', name:'岚石光庭', type:'交互材质别墅', file:'docs/10月27日/岚石光庭-交互材质别墅.wild', story:'L 形体量与水庭组织居住空间，木格栅、洞石、玻璃与室内陈设共同参与表达。', views:[{name:'主视日景',time:'day',direction:[1.15,.8,1.3]},{name:'侧向全景',time:'day',direction:[-1.25,.72,1.3]},{name:'水庭夜景',time:'night',direction:[1.15,.72,1.3]}], inside:{camera:[-.8,1.95,-.8],target:[5.2,1.3,-3.8]} },
  { id:'chengyu', name:'澄屿叠院', type:'现代悬挑', file:threeRoot+'/01-澄屿叠院-现代悬挑/澄屿叠院.wild', story:'现代悬挑体量、连续玻璃界面与水面，展示构件组合、材质和光影的协同。', views:[{name:'日景全貌',time:'day',direction:[1.15,.72,1.3]},{name:'黄昏全景',time:'sunset',direction:[-1.2,.75,1.25]},{name:'夜景全貌',time:'night',direction:[1.15,.68,1.3]}], inside:{camera:[6.3,1.95,2.7],target:[2.5,1.2,-1.5]} },
  { id:'songyu', name:'松雨回廊', type:'新中式合院', file:threeRoot+'/02-松雨回廊-新中式合院/松雨回廊.wild', story:'围合院落、屋面层次和回廊关系，体现蓝图对不同空间组织与建筑语言的承载。', views:[{name:'合院全貌',time:'day',direction:[-1.2,.9,1.3]},{name:'庭院俯视',time:'day',direction:[.12,1.55,1.0]},{name:'回廊夜景',time:'night',direction:[1.2,.8,1.3]}], inside:{camera:[2.7,1.9,-4.9],target:[-.5,1.1,-7.2]} },
  { id:'qipo', name:'栖坡陶院', type:'地中海坡顶', file:threeRoot+'/03-栖坡陶院-地中海坡顶/栖坡陶院.wild', story:'陶土坡顶、拱廊、阳台与庭院，展示同一引擎下的风格变化与参数化复用。', views:[{name:'拱廊全貌',time:'day',direction:[-1.1,.78,1.3]},{name:'院落全景',time:'sunset',direction:[1.2,.9,1.3]},{name:'陶院夜景',time:'night',direction:[-1.1,.75,1.3]}], inside:{camera:[2.8,1.9,-.2],target:[-2,1.05,-2.7]} },
  { id:'qingyu', name:'青屿咖啡', type:'商业空间', file:'docs/10月22日/09-咖啡厅/青屿咖啡.wild', story:'以咖啡空间检验建筑创作向商业展示场景的延展，关注入口、露台与界面表达。', views:[{name:'商业主视',time:'day',direction:[1.15,.7,1.3]},{name:'入口侧景',time:'day',direction:[-1.1,.72,1.3]},{name:'商业夜景',time:'night',direction:[1.15,.7,1.3]}] },
  { id:'yunxu', name:'云序中心', type:'写字楼', file:'docs/10月22日/05-写字楼/云序中心-写字楼.wild', story:'多层体量、立面分格和露台层次，展示蓝图在办公建筑外观表达中的应用。', views:[{name:'办公主视',time:'day',direction:[1.1,.55,1.3]},{name:'侧向立面',time:'day',direction:[-1.1,.55,1.3]},{name:'体量俯视',time:'sunset',direction:[1.05,1.0,1.3]}] },
  { id:'zhixu', name:'知序图书馆', type:'公共文化建筑', file:'docs/10月22日/07-图书馆/知序图书馆.wild', story:'公共文化建筑的体量和入口组织，补充住宅之外的建筑类型与展示任务。', views:[{name:'公共建筑主视',time:'day',direction:[1.1,.8,1.3]},{name:'侧向体量',time:'day',direction:[-1.1,.8,1.3]},{name:'文化空间夜景',time:'night',direction:[1.1,.7,1.3]}] },
  { id:'tingyu', name:'听雨水榭', type:'园林亭榭', file:'docs/10月22日/04-凉亭/听雨水榭-凉亭.wild', story:'开放亭榭、屋顶与木构细节，呈现小型景观构件和院落配景的创作可能。', views:[{name:'亭榭主视',time:'day',direction:[1.1,.7,1.3]},{name:'木构侧景',time:'day',direction:[-1.1,.65,1.3]},{name:'亭榭黄昏',time:'sunset',direction:[1.1,.7,1.3]}] },
]
const curated = process.argv.includes('--curated')
if (curated) {
  const selections = [
    ['curated-linting', '林庭石光馆.wild', '庭院展馆', '庭院、连廊与石材界面共同组织建筑空间，展示较复杂的公共空间和构件细节。'],
    ['curated-meiting', '玫庭庄园 · 欧式别墅.wild', '欧式住宅', '通过坡屋顶、门窗、柱廊与装饰层次，表达具有细节的欧式住宅。'],
    ['curated-qiguang', '栖光别墅 · 叠院露台住宅.wild', '叠院露台住宅', '退台、露台与多层空间组合，展示住宅体量与院落关系的参数化表达。'],
    ['curated-tinglan', '听澜合院 · 新中式别墅.wild', '新中式合院', '以合院、坡顶和木作细节表达新中式居住空间。'],
    ['curated-tingguang', '庭光别墅 · 双层庭院住宅.wild', '双层庭院住宅', '围绕庭院组织双层居住体量，展示建筑形态与开口、材质的组合。'],
    ['curated-yanlu', '砚麓别墅.wild', '别墅与景观', '以真实蓝图中的建筑体量和细部表达，展示持续迭代的建筑创作成果。'],
    ['curated-forest', 'Forest Cafe.wild', '商业建筑', '以丰富的商业空间、界面和构件细节，展示 WILD 在住宅之外的应用。'],
  ]
  projects.splice(0, projects.length, ...selections.map(([id,name,type,story]) => ({ id, name:name.replace('.wild',''), type, story, file:'docs-dev/wild/'+name, views:[{name:'建筑全貌',time:'day',direction:[-1.15,.78,1.3]},{name:'另一侧完整视角',time:'day',direction:[1.15,.8,-1.3]}] })))
}
const manifestFile = curated ? 'curated-manifest.json' : 'render-manifest.json'

await mkdir(output, { recursive:true })
const sourceHash = createHash('sha256')
async function digest(dir) {
  for (const entry of (await readdir(dir,{withFileTypes:true})).sort((a,b)=>a.name.localeCompare(b.name))) {
    const file=join(dir,entry.name)
    if(entry.isDirectory()) await digest(file)
    else if(/\.(ts|json)$/.test(file)) { sourceHash.update(relative(root,file).replaceAll('\\','/'));sourceHash.update(await readFile(file)) }
  }
}
await digest(resolve(root,'wild-core/src'))
await digest(resolve(root,'wild-web/src/renderer'))
sourceHash.update(await readFile(resolve(root,'wild-core/schema.json')))
sourceHash.update(await readFile(resolve(root,'wild-web/scripts/material-mechanism-preview.html')))
const rendererSha256=sourceHash.digest('hex')
const browser=await launchEditorBrowser((process.env.BUSINESS_PREVIEW_URL || 'http://127.0.0.1:5178')+'/scripts/material-mechanism-preview.html')
const records=[]
try {
  const p=browser.page
  await p.resize(1600,1000)
  await p.wait('window.ready===true',60000)
  await p.evaluate(`renderer.setSize(1600,1000);camera.aspect=1.6;camera.updateProjectionMatrix();window.renderHarness.post.setSize(1600,1000);document.body.style.overflow='hidden';true`)
  for(const project of projects) {
    const text=await readFile(resolve(root,project.file),'utf8'), bp=JSON.parse(text)
    const inputSha256=createHash('sha256').update(text).digest('hex')
    const results=[]
    for(const [index,view] of project.views.entries()) {
      const result=await p.evaluate('window.viewBlueprint('+JSON.stringify(bp)+','+JSON.stringify({time:view.time,quality:'high',fov:43})+')')
      assert.deepEqual(result.diagnostics.filter(d=>d.level==='error'),[],project.name+' 编译错误')
      const frame=await p.evaluate(`(() => {
        const T=window.THREE,b=new T.Box3().setFromObject(window.group),center=b.getCenter(new T.Vector3()),size=b.getSize(new T.Vector3());
        const direction=new T.Vector3(...${JSON.stringify(view.direction)}).normalize();
        camera.position.copy(center).add(direction);camera.lookAt(center);camera.updateMatrixWorld();
        const right=new T.Vector3(1,0,0).applyQuaternion(camera.quaternion),up=new T.Vector3(0,1,0).applyQuaternion(camera.quaternion);
        const tanV=Math.tan(T.MathUtils.degToRad(camera.fov/2)),tanH=tanV*camera.aspect;
        let distance=0;const corners=[];
        window.group.updateMatrixWorld(true);
        window.group.traverse(object=>{
          if(!object.isMesh||!object.visible)return;
          if(!object.geometry.boundingBox)object.geometry.computeBoundingBox();
          const box=object.geometry.boundingBox;if(!box)return;
          for(const x of [box.min.x,box.max.x])for(const y of [box.min.y,box.max.y])for(const z of [box.min.z,box.max.z]){
            const point=new T.Vector3(x,y,z).applyMatrix4(object.matrixWorld),d=point.clone().sub(center),depth=d.dot(direction);
            distance=Math.max(distance,Math.abs(d.dot(right))/(tanH*.88)+depth,Math.abs(d.dot(up))/(tanV*.88)+depth);corners.push(point);
          }
        });
        camera.position.copy(center).addScaledVector(direction,distance);camera.lookAt(center);camera.updateMatrixWorld();
        for(let i=0;i<4;i++){
          const projected=corners.map(c=>c.clone().project(camera));
          const minX=Math.min(...projected.map(v=>v.x)),maxX=Math.max(...projected.map(v=>v.x)),minY=Math.min(...projected.map(v=>v.y)),maxY=Math.max(...projected.map(v=>v.y));
          center.addScaledVector(right,(minX+maxX)*.5*distance*tanH).addScaledVector(up,(minY+maxY)*.5*distance*tanV);
          distance*=Math.max((maxX-minX)/1.76,(maxY-minY)/1.76);
          camera.position.copy(center).addScaledVector(direction,distance);camera.lookAt(center);camera.updateMatrixWorld();
        }
        camera.position.copy(center).addScaledVector(direction,distance);camera.lookAt(center);camera.updateMatrixWorld();window.draw();
        const ndc=corners.map(c=>c.clone().project(camera).toArray());
        return {camera:camera.position.toArray(),target:center.toArray(),bounds:{min:b.min.toArray(),max:b.max.toArray()},maxProjectedExtent:Math.max(...ndc.flatMap(v=>[Math.abs(v[0]),Math.abs(v[1])])),fov:camera.fov};
      })()`)
      assert.ok(frame.maxProjectedExtent<=.9,project.name+' 全景必须完整入镜')
      await p.evaluate('document.fonts.ready.then(()=>{window.draw();return true})')
      const file=project.id+'-'+String(index+1).padStart(2,'0')+'.jpg'
      const capture=await p.send('Page.captureScreenshot',{format:'jpeg',quality:94,fromSurface:true})
      await writeFile(join(output,file),Buffer.from(capture.data,'base64'))
      results.push({file,name:view.name,time:view.time,...frame,...result})
    }
    if(project.inside) {
      const settings={...project.inside,time:'day',quality:'high',fov:58}
      const result=await p.evaluate('window.viewBlueprint('+JSON.stringify(bp)+','+JSON.stringify(settings)+')')
      assert.deepEqual(result.diagnostics.filter(d=>d.level==='error'),[])
      const file=project.id+'-04-interior.jpg'
      const capture=await p.send('Page.captureScreenshot',{format:'jpeg',quality:94,fromSurface:true})
      await writeFile(join(output,file),Buffer.from(capture.data,'base64'))
      results.push({file,name:'室内材质',...settings,...result,scope:'室内取景，保留全部建筑几何'})
    }
    records.push({...project,bytes:Buffer.byteLength(text),inputSha256,views:results})
    await writeFile(join(output,manifestFile),JSON.stringify({status:'in_progress',resolution:[1600,1000],rendererSha256,records},null,2))
    console.log(JSON.stringify({name:project.name,views:results.length,bytes:Buffer.byteLength(text)}))
  }
  assert.deepEqual(p.errors,[])
  await writeFile(join(output,manifestFile),JSON.stringify({status:'rendered',createdAt:new Date().toISOString(),resolution:[1600,1000],format:'jpeg',quality:94,rendererSha256,hiddenObjects:[],records,shaderErrors:p.errors,visualReview:{assistant:'pending',user:'pending'},scope:'本轮读取既有真实 WILD，使用项目正式前端 Core/Three.js/材质/光照/后期模块重建截图；不是本轮 Agent 自动生成或客户验收证明。'},null,2))
} finally { await browser.close() }
