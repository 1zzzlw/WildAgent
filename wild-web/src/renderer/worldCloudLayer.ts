import * as THREE from 'three'
import { getWorldEffectUniforms } from './worldEffectRuntime'
import { getWorldEnvironmentUniforms } from './worldEnvironmentRuntime'

/**
 * 程序化动态云层。以小噪声纹理生成多层云形，补充朝光面、云底与亮边，
 * ``cloudCoverage`` 控制覆盖度、``wind`` 控制漂移、``effectTime`` 推进动画。
 * 默认由 ``clouds`` 开关关闭；关闭时整层不绘制，零 GPU 成本。
 */
export class WorldCloudLayer {
  private readonly mesh: THREE.Mesh
  private readonly material: THREE.ShaderMaterial
  private readonly environment = getWorldEnvironmentUniforms()
  private readonly effects = getWorldEffectUniforms()
  private readonly noise: THREE.DataTexture

  constructor(scene: THREE.Scene) {
    // 参考项目用小噪声纹理代替每像素哈希，支持多层云形和朝光面的自遮蔽。
    const noise = new Uint8Array(256 * 256)
    let seed = 2654435769
    for (let index=0; index<noise.length; index++) {
      seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5
      noise[index] = (seed >>> 0) & 255
    }
    this.noise = new THREE.DataTexture(noise,256,256,THREE.RedFormat)
    this.noise.wrapS = this.noise.wrapT = THREE.RepeatWrapping
    this.noise.minFilter = this.noise.magFilter = THREE.LinearFilter
    this.noise.needsUpdate = true
    this.material = new THREE.ShaderMaterial({
      name: 'WorldCloudLayer',
      side: THREE.BackSide,
      transparent: true,
      depthWrite: false,
      depthTest: true,
      fog: false,
      uniforms: {
        uCloudCoverage: this.environment.cloudCoverage,
        uWind: this.environment.wind,
        uTime: this.effects.effectTime,
        uClouds: this.effects.clouds,
        uNoise: {value: this.noise},
        uSunDirection: {value: new THREE.Vector3(1,1,1).normalize()},
        uSunColor: {value: new THREE.Color(0xfff1d6)},
        uBrightness: {value: 3},
      },
      vertexShader: /* glsl */ `
        varying vec3 vWorldDirection;
        void main() {
          vWorldDirection = position;
          gl_Position = projectionMatrix * vec4(mat3(viewMatrix) * position, 1.0);
          gl_Position.z = gl_Position.w;
        }
      `,
      fragmentShader: /* glsl */ `
        uniform float uCloudCoverage;
        uniform float uWind;
        uniform float uTime;
        uniform float uClouds;
        uniform sampler2D uNoise;
        uniform vec3 uSunDirection;
        uniform vec3 uSunColor;
        uniform float uBrightness;
        varying vec3 vWorldDirection;
        float cloudNoise(vec2 p) {
          vec2 cell=floor(p), f=fract(p);f=f*f*(3.0-2.0*f);
          return texture2D(uNoise,(cell+f+.5)/256.0).r;
        }
        float cloudFbm(vec2 p) {
          float value=0.0, amplitude=.5;
          for(int i=0;i<5;i++) {
            value+=cloudNoise(p)*amplitude;
            p=mat2(1.6,1.2,-1.2,1.6)*p+17.3;amplitude*=.5;
          }
          return value/.96875;
        }

        void main() {
          if (uClouds < 0.5) { discard; return; }
          vec3 direction=normalize(vWorldDirection);
          float height=max(direction.y,0.0);
          if(height<.005) {discard;return;}
          vec2 uv=direction.xz/(height+.10)*vec2(.62,.95)*2.2;
          uv+=vec2(-.012,.004)*uTime*(.4+uWind);
          float warp=cloudFbm(uv*.45+7.1);
          vec2 warped=uv+(warp-.5)*1.3;
          float body=cloudFbm(warped);
          float broad=cloudNoise(uv*.19+3.7);
          float densityField=body*.74+broad*.36;
          float threshold=mix(.72,.28,uCloudCoverage);
          float coverage=smoothstep(threshold-.08,threshold+.09,densityField);
          float density=coverage*smoothstep(.005,.10,height)*smoothstep(0.0,.1,uCloudCoverage);
          if (density <= 0.001) { discard; return; }
          vec2 towardSun=normalize(uSunDirection.xz+vec2(.0001));
          float relief=clamp((body-cloudFbm(warped+towardSun*.22))*4.5+.5,0.0,1.0);
          float facing=pow(max(dot(direction,uSunDirection),0.0),7.0);
          float rim=coverage*(1.0-coverage)*4.0;
          float thickness=smoothstep(.42,.72,densityField);
          vec3 cloudColor=mix(vec3(.18,.24,.34),vec3(.98,.99,1.0),relief*relief);
          cloudColor*=1.0-thickness*.35;
          cloudColor+=uSunColor*rim*(.12+facing*.65);
          gl_FragColor = vec4(cloudColor*uBrightness, density*.95);
        }
      `,
    })

    this.mesh = new THREE.Mesh(new THREE.BoxGeometry(2,2,2), this.material)
    this.mesh.name = 'WorldCloudLayer'
    this.mesh.renderOrder = 1
    this.mesh.frustumCulled = false
    scene.add(this.mesh)
  }

  setVisible(visible: boolean): void {
    this.mesh.visible = visible
  }

  setLighting(direction: THREE.Vector3, color: number, exposure: number, isNight: boolean): void {
    this.material.uniforms.uSunDirection.value.copy(direction)
    this.material.uniforms.uSunColor.value.setHex(color)
    this.material.uniforms.uBrightness.value = (isNight ? .18 : .9) / exposure
  }

  dispose(): void {
    this.mesh.removeFromParent()
    this.mesh.geometry.dispose()
    this.material.dispose()
    this.noise.dispose()
  }
}
