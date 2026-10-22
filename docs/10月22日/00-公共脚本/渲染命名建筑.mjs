// 独立 Chromium：复用生产材质、水面与环境贴图运行时，补日景/夜景和文字近景。
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { resolve, dirname } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../..')
const {createServer}=await import(pathToFileURL(resolve(root,'wild-web/node_modules/vite/dist/node/index.js')))
const {launchEditorBrowser}=await import(pathToFileURL(resolve(root,'wild-web/scripts/editor-browser.mjs')))
const target=resolve(process.argv[2]), out=resolve(process.argv[3])
const raw=await readFile(target,'utf8'), bp=JSON.parse(raw)
const server=await createServer({root:resolve(root,'wild-web'),logLevel:'silent',server:{host:'127.0.0.1',port:0,fs:{allow:[root]}},plugins:[{
  name:'named-building-preview',configureServer(s){s.middlewares.use('/__named',(_req,res)=>{res.setHeader('Content-Type','text/html');res.end('<!doctype html><html><meta charset="utf-8"><style>body{margin:0}canvas{display:block}</style><body></body></html>')})}
}]})
await server.listen()
let browser
try {
  browser=await launchEditorBrowser(server.resolvedUrls.local[0]+'__named')
  const p=browser.page
  await p.resize(1440,1080)
  const result=await p.evaluate(`(async()=>{
    const THREE=await import('/node_modules/.vite/deps/three.js');
    const {parseWildBlueprint,reconstructWildEntity}=await import('/src/renderer/wildCoreAdapter.ts');
    const {createSceneGroupFromEntity}=await import('/src/renderer/renderEntity.ts');
    const {WorldEnvironmentMapRuntime}=await import('/src/renderer/environmentRuntime.ts');
    const {TIME_PRESETS}=await import('/src/renderer/defaultWorldLook.ts');
    const {setWaterSurfaceTime,setWaterSurfaceAppearance}=await import('/src/renderer/waterSurfaceMaterial.ts');
    const {configureMaterialRendering}=await import('/src/renderer/materialAdapter.ts');
    const blueprint=parseWildBlueprint(${JSON.stringify(raw)});
    const entity=await reconstructWildEntity(blueprint);
    if(entity.diagnostics.some(d=>d.level==='error'))throw Error(JSON.stringify(entity.diagnostics));
    const renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});
    renderer.setSize(1440,1080);renderer.setPixelRatio(1);renderer.shadowMap.enabled=true;
    renderer.shadowMap.type=THREE.PCFSoftShadowMap;renderer.toneMapping=THREE.ACESFilmicToneMapping;
    configureMaterialRendering(renderer.capabilities.getMaxAnisotropy());document.body.appendChild(renderer.domElement);
    const scene=new THREE.Scene(),group=createSceneGroupFromEntity(entity);scene.add(group);
    const bounds=new THREE.Box3(new THREE.Vector3(...entity.boundingBox.min),new THREE.Vector3(...entity.boundingBox.max));
    const size=bounds.getSize(new THREE.Vector3()),center=bounds.getCenter(new THREE.Vector3());
    const camera=new THREE.PerspectiveCamera(43,4/3,.1,1000);
    const ground=new THREE.Mesh(new THREE.PlaneGeometry(1000,1000),new THREE.MeshStandardMaterial({color:0x8c927f,roughness:1}));
    ground.rotation.x=-Math.PI/2;ground.position.y=Math.min(-.24,bounds.min.y-.04);ground.receiveShadow=true;scene.add(ground);
    const sun=new THREE.DirectionalLight();scene.add(sun);sun.castShadow=true;sun.shadow.mapSize.set(2048,2048);
    sun.shadow.camera.left=-35;sun.shadow.camera.right=35;sun.shadow.camera.top=35;sun.shadow.camera.bottom=-35;
    sun.shadow.camera.far=150;sun.shadow.normalBias=.03;sun.shadow.bias=-.00015;
    const hemi=new THREE.HemisphereLight();scene.add(hemi);
    const env=new WorldEnvironmentMapRuntime(renderer,scene);
    const atmosphere={cloud:0,rain:0,snow:0,dust:0,fog:0,tintStrength:0,backgroundTint:0xb9c9d8};
    const labels=[];group.traverse(o=>{if(o.name==='TextLabel')labels.push(o)});
    const deadline=Date.now()+20000;
    while(labels.some(o=>!o.material.map?.image?.complete)&&Date.now()<deadline)await new Promise(r=>setTimeout(r,50));
    if(labels.some(o=>!o.material.map?.image?.complete))throw Error('文字纹理未就绪');
    const setTime=(time)=>{const preset=TIME_PRESETS[time];const phi=THREE.MathUtils.degToRad(preset.sunPhi),theta=THREE.MathUtils.degToRad(preset.sunTheta);
      const direction=new THREE.Vector3().setFromSphericalCoords(1,phi,theta);sun.position.copy(direction).multiplyScalar(60);
      sun.color.setHex(preset.directionalColor);sun.intensity=preset.directionalIntensity;
      hemi.color.setHex(preset.hemisphereSkyColor);hemi.groundColor.setHex(preset.hemisphereGroundColor);hemi.intensity=preset.hemisphereIntensity;
      renderer.toneMappingExposure=preset.exposure;scene.background=new THREE.Color(preset.background);
      env.rebuild(preset,atmosphere,direction,time==='night');setWaterSurfaceAppearance(1,.65);setWaterSurfaceTime(2.4);
    };
    const shot=(time,name,position,look)=>{setTime(time);camera.position.set(...position);camera.lookAt(...look);renderer.render(scene,camera);return {name,data:renderer.domElement.toDataURL('image/png')}};
    const span=Math.max(size.x,size.z),target=[center.x,Math.max(1.5,size.y*.36),center.z];
    const corner=[center.x+span*1.05,size.y+span*.54,center.z-span*1.45];
    const shots=[shot('day','day',corner,target),shot('night','night',corner,target)];
    const water=blueprint.geometry.elements.find(e=>e.material==='water'&&e.type==='floor');
    if(water){const x=(water.from[0]+water.to[0])/2,z=(water.from[2]+water.to[2])/2;
      shots.push(shot('day','water',[x+7,4.6,z-8],[x,.15,z]));}
    let main;group.traverse(o=>{if(o.userData.elementId==='building_name'&&o.name==='TextLabel')main=o});
    if(!main)throw Error('缺少主招牌');
    const signCenter=main.getWorldPosition(new THREE.Vector3());
    shots.push(shot('day','sign',[signCenter.x+span*.16,signCenter.y+1.25,signCenter.z-span*.48],signCenter.toArray()));
    return {shots,boundingBox:entity.boundingBox,meshCount:entity.meshes.length,labels:labels.length,
      lightSources:blueprint.geometry.elements.filter(e=>e.lightSource).length,diagnostics:entity.diagnostics};
  })()`)
  if(p.errors.length)throw Error(p.errors.join('\n'))
  await mkdir(out,{recursive:true})
  for(const s of result.shots)await writeFile(resolve(out,s.name+'.png'),Buffer.from(s.data.split(',')[1],'base64'))
  const manifest={input:target,inputSha256:createHash('sha256').update(raw).digest('hex'),renderer:'production renderEntity + materialAdapter + WorldEnvironmentMapRuntime + waterSurfaceMaterial',
    settings:{width:1440,height:1080,shadows:'PCFSoft 2048',timePresets:['day','night'],water:{transparency:1,waveStrength:.65,time:2.4}},
    ...result,shots:result.shots.map(s=>s.name+'.png'),runtimeErrors:p.errors}
  await writeFile(resolve(out,'world-render-manifest.json'),JSON.stringify(manifest,null,2))
  console.log(JSON.stringify(manifest,null,2))
} finally {await browser?.close();await server.close()}
