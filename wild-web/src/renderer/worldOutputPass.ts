import * as THREE from 'three'
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js'

/** 借鉴参考项目的高光过渡、轻微冷暖分离与边缘保护锐化，合入现有输出遍。 */
export function createWorldOutputPass(): OutputPass {
  const pass = new OutputPass()
  pass.material.uniforms.worldTexel = {value: new THREE.Vector2(1,1)}
  pass.material.uniforms.worldSharpen = {value: .1}
  pass.setSize = (width,height) => pass.material.uniforms.worldTexel.value.set(1 / Math.max(width,1),1 / Math.max(height,1))
  pass.material.fragmentShader = pass.material.fragmentShader
    .replace('varying vec2 vUv;', `varying vec2 vUv;
      uniform vec2 worldTexel;
      uniform float worldSharpen;`)
    .replace('gl_FragColor = texture2D( tDiffuse, vUv );', `gl_FragColor = texture2D( tDiffuse, vUv );
      if (worldSharpen > 0.0) {
        vec3 a = texture2D(tDiffuse, vUv + worldTexel * vec2(-1.0,-1.0)).rgb;
        vec3 b = texture2D(tDiffuse, vUv + worldTexel * vec2( 1.0,-1.0)).rgb;
        vec3 c = texture2D(tDiffuse, vUv + worldTexel * vec2(-1.0, 1.0)).rgb;
        vec3 d = texture2D(tDiffuse, vUv + worldTexel * vec2( 1.0, 1.0)).rgb;
        vec3 lo = min(gl_FragColor.rgb,min(min(a,b),min(c,d)));
        vec3 hi = max(gl_FragColor.rgb,max(max(a,b),max(c,d)));
        float contrast = dot(hi-lo, vec3(.2126,.7152,.0722)) / max(.1,dot(hi,vec3(.2126,.7152,.0722)));
        float strength = worldSharpen * (1.0-smoothstep(.08,.35,contrast));
        gl_FragColor.rgb = clamp(gl_FragColor.rgb + (gl_FragColor.rgb-(a+b+c+d)*.25)*strength, lo, hi);
      }`)
    .replace('gl_FragColor.rgb = ACESFilmicToneMapping( gl_FragColor.rgb );', `
      gl_FragColor.rgb = mix(ACESFilmicToneMapping(gl_FragColor.rgb), AgXToneMapping(gl_FragColor.rgb), .18);`)
    .replace('// color space', `// 轻微 S 曲线与冷暖分离，保留建筑材质本色；不加入颗粒、色差或动态模糊。
      float luma = dot(gl_FragColor.rgb,vec3(.2126,.7152,.0722));
      gl_FragColor.rgb *= mix(vec3(.98,1.0,1.025),vec3(1.01,1.0,.99),smoothstep(.04,.65,luma));
      gl_FragColor.rgb = mix(gl_FragColor.rgb,gl_FragColor.rgb*gl_FragColor.rgb*(3.0-2.0*gl_FragColor.rgb),.08);
      gl_FragColor.rgb = clamp(gl_FragColor.rgb*.997 + vec3(.001,.0015,.002),0.0,1.0);
      // color space`)
  return pass
}
