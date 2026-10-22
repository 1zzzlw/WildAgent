// 图片对应视角与暖光实图；生产几何、材质、天空、IBL，零后期修图。
import {readFile,writeFile,mkdir} from 'node:fs/promises'
import {createHash} from 'node:crypto'
import {resolve,dirname} from 'node:path'
import {fileURLToPath,pathToFileURL} from 'node:url'
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../..')
const {createServer}=await import(pathToFileURL(resolve(root,'wild-web/node_modules/vite/dist/node/index.js')))
const {launchEditorBrowser}=await import(pathToFileURL(resolve(root,'wild-web/scripts/editor-browser.mjs')))
const target=resolve(process.argv[2]),out=resolve(process.argv[3]),raw=await readFile(target,'utf8')
const design=JSON.parse(await readFile(resolve(dirname(target),'01-需求与设计/DesignDocument.json'),'utf8'))
const params=design.decisions.authoring
const width=params.recipe==='stone'?1600:1100,height=params.recipe==='stone'?1120:1320
const server=await createServer({root:resolve(root,'wild-web'),logLevel:'silent',server:{host:'127.0.0.1',port:0,fs:{allow:[root]}},
 plugins:[{name:'photo-preview',configureServer(s){s.middlewares.use('/__photo',(_req,res)=>{res.setHeader('Content-Type','text/html');res.end('<!doctype html><html><meta charset="utf-8"><style>body{margin:0}canvas{display:block}</style><body></body></html>')})}}]})
await server.listen();let browser
try {
 browser=await launchEditorBrowser(server.resolvedUrls.local[0]+'__photo');const page=browser.page
 await page.resize(width,height)
 const result=await page.evaluate(`(async()=>{
  const THREE=await import('/node_modules/.vite/deps/three.js');
  const {Sky}=await import('/node_modules/three/examples/jsm/objects/Sky.js');
  const {parseWildBlueprint,reconstructWildEntity}=await import('/src/renderer/wildCoreAdapter.ts');
  const {createSceneGroupFromEntity}=await import('/src/renderer/renderEntity.ts');
  const {configureMaterialRendering}=await import('/src/renderer/materialAdapter.ts');
  const {WorldEnvironmentMapRuntime,syncSkyPreset}=await import('/src/renderer/environmentRuntime.ts');
  const {TIME_PRESETS}=await import('/src/renderer/defaultWorldLook.ts');
  const source=parseWildBlueprint(${JSON.stringify(raw)}),entity=await reconstructWildEntity(source),p=${JSON.stringify(params)};
  if(entity.diagnostics.some(d=>d.level==='error'))throw Error(JSON.stringify(entity.diagnostics));
  const scene=new THREE.Scene(),group=createSceneGroupFromEntity(entity);scene.add(group);
  const renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});
  renderer.setSize(${width},${height});renderer.setPixelRatio(1);renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
  renderer.toneMapping=THREE.ACESFilmicToneMapping;configureMaterialRendering(renderer.capabilities.getMaxAnisotropy());document.body.appendChild(renderer.domElement);
  const camera=new THREE.PerspectiveCamera(p.camera.fov,${width}/${height},.1,1000);camera.position.set(...p.camera.position);camera.lookAt(...p.camera.target);
  const sun=new THREE.DirectionalLight();scene.add(sun);sun.castShadow=true;sun.shadow.mapSize.set(4096,4096);
  Object.assign(sun.shadow.camera,{left:-32,right:32,top:32,bottom:-32,far:180});sun.shadow.normalBias=.025;sun.shadow.bias=-.0001;
  const hemi=new THREE.HemisphereLight();scene.add(hemi);
  const ground=new THREE.Mesh(new THREE.PlaneGeometry(1000,1000),new THREE.MeshStandardMaterial({color:p.recipe==='stone'?0x69734c:0x616559,roughness:1}));
  ground.rotation.x=-Math.PI/2;ground.position.y=entity.boundingBox.min[1]-.04;ground.receiveShadow=true;scene.add(ground);
  const sky=new Sky();sky.scale.setScalar(450);scene.add(sky);
  const atmosphere={cloud:0,rain:0,snow:0,dust:0,fog:0,tintStrength:0,backgroundTint:0xb9c9d8};
  const env=new WorldEnvironmentMapRuntime(renderer,scene);
  const labels=[];group.traverse(o=>{if(o.name==='TextLabel')labels.push(o)});
  const deadline=Date.now()+20000;while(labels.some(o=>!o.material.map?.image?.complete)&&Date.now()<deadline)await new Promise(r=>setTimeout(r,40));
  if(labels.some(o=>!o.material.map?.image?.complete))throw Error('招牌纹理未加载');
  const shots=[];
  const lighting=time=>{const preset=TIME_PRESETS[time];
    const direction=new THREE.Vector3().setFromSphericalCoords(1,THREE.MathUtils.degToRad(preset.sunPhi),THREE.MathUtils.degToRad(preset.sunTheta));
    sun.position.copy(direction).multiplyScalar(70);sun.color.setHex(preset.directionalColor);sun.intensity=preset.directionalIntensity;
    hemi.color.setHex(preset.hemisphereSkyColor);hemi.groundColor.setHex(preset.hemisphereGroundColor);hemi.intensity=preset.hemisphereIntensity;
    renderer.toneMappingExposure=preset.exposure;scene.background=new THREE.Color(preset.background);sky.visible=time!=='night';syncSkyPreset(sky,preset,atmosphere,direction);env.rebuild(preset,atmosphere,direction,time==='night');
  };
  const capture=(name,time,position=p.camera.position,look=p.camera.target)=>{lighting(time);camera.position.set(...position);camera.lookAt(...look);renderer.render(scene,camera);shots.push({name,data:renderer.domElement.toDataURL('image/png')});};
  capture('reference-day','day');capture('reference-night','night');
  if(p.recipe==='stone')capture('facade-detail','day',[-18,10,-20],[-3.2,4.1,0]);
  else capture('warm-evening','sunset');
  return {shots,boundingBox:entity.boundingBox,meshCount:entity.meshes.length,diagnostics:entity.diagnostics,
    labels:labels.length,lightSources:source.geometry.elements.filter(e=>e.lightSource).length};
 })()`)
 if(page.errors.length)throw Error(page.errors.join('\n'))
 await mkdir(out,{recursive:true})
 for(const s of result.shots)await writeFile(resolve(out,s.name+'.png'),Buffer.from(s.data.split(',')[1],'base64'))
 const manifest={input:target,inputSha256:createHash('sha256').update(raw).digest('hex'),
  designSha256:createHash('sha256').update(await readFile(resolve(dirname(target),'01-需求与设计/DesignDocument.json'))).digest('hex'),
  renderer:'production Core + renderEntity + materialAdapter + Sky + WorldEnvironmentMapRuntime',
  settings:{width,height,camera:params.camera,shadows:'4096 PCFSoft',lighting:'repository TIME_PRESETS',postprocessed:false},
  ...result,shots:result.shots.map(s=>s.name+'.png'),runtimeErrors:page.errors}
 await writeFile(resolve(out,'photo-render-manifest.json'),JSON.stringify(manifest,null,2))
 console.log(JSON.stringify(manifest,null,2))
}finally{await browser?.close();await server.close()}
