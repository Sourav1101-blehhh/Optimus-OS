export class WebGLCore {
    constructor(containerId, canvasId) {
        this.container = document.getElementById(containerId);
        this.canvas = document.getElementById(canvasId);

        if (typeof THREE === 'undefined') {
            console.warn('[WebGLCore] THREE.js is not loaded. 3D rendering disabled.');
            return;
        }
        if (!this.container || !this.canvas) {
            console.warn('[WebGLCore] Container or Canvas not found. 3D rendering disabled.');
            return;
        }

        // Scene Setup
        this.scene = new THREE.Scene();
        this.camera = new THREE.PerspectiveCamera(60, this.container.clientWidth / this.container.clientHeight, 0.1, 100);
        this.camera.position.z = 8;

        this.renderer = new THREE.WebGLRenderer({ canvas: this.canvas, alpha: true, antialias: true });
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);

        this.coreGroup = new THREE.Group();
        this.scene.add(this.coreGroup);

        // AI State lerp targets
        this.stateColors = {
            IDLE: { c1: new THREE.Color(0x00f3ff), c2: new THREE.Color(0x0088ff), c3: new THREE.Color(0x002244) },
            THINKING: { c1: new THREE.Color(0xff00ff), c2: new THREE.Color(0x8a2be2), c3: new THREE.Color(0x4a0082) },
            STREAMING: { c1: new THREE.Color(0x00ffff), c2: new THREE.Color(0x00f3ff), c3: new THREE.Color(0xff0055) }
        };
        
        this.currentColor1 = this.stateColors.IDLE.c1.clone();
        this.currentColor2 = this.stateColors.IDLE.c2.clone();
        this.currentColor3 = this.stateColors.IDLE.c3.clone();
        this.targetColor1 = this.stateColors.IDLE.c1.clone();
        this.targetColor2 = this.stateColors.IDLE.c2.clone();
        this.targetColor3 = this.stateColors.IDLE.c3.clone();
        
        this.currentState = 'IDLE';

        this.setupOrb();
        this.setupParticles();

        this.targetAmplitude = 0;
        this.currentAmplitude = 0;

        this._resizeHandler = this.onWindowResize.bind(this);
        window.addEventListener('resize', this._resizeHandler);
    }

    setAIState(state, tps = 0) {
        if (this.stateColors[state]) {
            this.currentState = state;
            this.targetColor1.copy(this.stateColors[state].c1);
            this.targetColor2.copy(this.stateColors[state].c2);
            this.targetColor3.copy(this.stateColors[state].c3);
        }
        // Normalize TPS to an amplitude
        this.targetAmplitude = Math.min(tps / 30.0, 1.0);
    }

    setTelemetry(amplitude) {
        this.targetAmplitude = amplitude;
    }

    setupOrb() {
        const vertexShaderCode = `
            uniform float uTime;
            uniform float uNoiseIntensity;
            uniform float uNoiseSpeed;
            varying vec3 vNormal;
            varying vec3 vPosition;
            varying vec3 vEyeVector;

            // Ashima Arts 3D Simplex Noise
            vec4 permute(vec4 x){return mod(((x*34.0)+1.0)*x, 289.0);}
            vec4 taylorInvSqrt(vec4 r){return 1.79284291400159 - 0.85373472095314 * r;}

            float snoise(vec3 v){
                const vec2 C = vec2(1.0/6.0, 1.0/3.0);
                const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
                vec3 i  = floor(v + dot(v, C.yyy) );
                vec3 x0 =   v - i + dot(i, C.xxx) ;
                vec3 g = step(x0.yzx, x0.xyz);
                vec3 l = 1.0 - g;
                vec3 i1 = min( g.xyz, l.zxy );
                vec3 i2 = max( g.xyz, l.zxy );
                vec3 x1 = x0 - i1 + 1.0 * C.xxx;
                vec3 x2 = x0 - i2 + 2.0 * C.xxx;
                vec3 x3 = x0 - D.yyy;
                i = mod(i, 289.0 );
                vec4 p = permute( permute( permute(
                             i.z + vec4(0.0, i1.z, i2.z, 1.0 ))
                           + i.y + vec4(0.0, i1.y, i2.y, 1.0 ))
                           + i.x + vec4(0.0, i1.x, i2.x, 1.0 ));
                float n_ = 0.142857142857;
                vec3 ns = n_ * D.wyz - D.xzx;
                vec4 j = p - 49.0 * floor(p * ns.z *ns.z);
                vec4 x_ = floor(j * ns.z);
                vec4 y_ = floor(j - 7.0 * x_ );
                vec4 x = x_ *ns.x + ns.yyyy;
                vec4 y = y_ *ns.x + ns.yyyy;
                vec4 h = 1.0 - abs(x) - abs(y);
                vec4 b0 = vec4( x.xy, y.xy );
                vec4 b1 = vec4( x.zw, y.zw );
                vec4 s0 = floor(b0)*2.0 + 1.0;
                vec4 s1 = floor(b1)*2.0 + 1.0;
                vec4 sh = -step(h, vec4(0.0));
                vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy ;
                vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww ;
                vec3 p0 = vec3(a0.xy,h.x);
                vec3 p1 = vec3(a0.zw,h.y);
                vec3 p2 = vec3(a1.xy,h.z);
                vec3 p3 = vec3(a1.zw,h.w);
                vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2, p2), dot(p3,p3)));
                p0 *= norm.x;
                p1 *= norm.y;
                p2 *= norm.z;
                p3 *= norm.w;
                vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
                m = m * m;
                return 42.0 * dot( m*m, vec4( dot(p0,x0), dot(p1,x1),
                                                dot(p2,x2), dot(p3,x3) ) );
            }

            void main() {
                vNormal = normalize(normalMatrix * normal);
                float noise = snoise(position * uNoiseSpeed + uTime);
                vec3 newPosition = position + normal * noise * uNoiseIntensity;
                vPosition = newPosition;
                
                vec4 worldPosition = modelMatrix * vec4(newPosition, 1.0);
                vEyeVector = normalize(worldPosition.xyz - cameraPosition);
                
                gl_Position = projectionMatrix * viewMatrix * worldPosition;
            }
        `;

        const fragmentShaderCode = `
            uniform float uTime;
            uniform float uAmplitude;
            uniform vec3 uColorCyan;
            uniform vec3 uColorMagenta;
            uniform vec3 uColorPurple;
            varying vec3 vNormal;
            varying vec3 vPosition;
            varying vec3 vEyeVector;

            void main() {
                float ior = 1.15;
                vec3 refracted = refract(vEyeVector, vNormal, 1.0 / ior);
                
                float mixVal1 = sin(vPosition.x * 0.4 + uTime * 0.6) * 0.5 + 0.5;
                float mixVal2 = cos(vPosition.y * 0.4 - uTime * 0.4) * 0.5 + 0.5;

                vec3 colorBlend = mix(uColorCyan, uColorMagenta, mixVal1 + uAmplitude * 0.5);
                vec3 finalColor = mix(colorBlend, uColorPurple, mixVal2);

                float fresnel = pow(1.0 + dot(vEyeVector, vNormal), 3.0);
                float glow = pow(1.0 - max(dot(vNormal, vec3(0.0, 0.0, 1.0)), 0.0), 2.0);
                
                finalColor += vec3(fresnel * 0.9) * uColorCyan;
                finalColor += vec3(glow * 0.5) * uColorMagenta;
                
                float alpha = 0.5 + fresnel * 0.5 + uAmplitude * 0.2;

                gl_FragColor = vec4(finalColor, min(alpha, 1.0));
            }
        `;

        this.orbUniforms = {
            uTime: { value: 0.0 },
            uAmplitude: { value: 0.0 },
            uNoiseIntensity: { value: 0.18 },
            uNoiseSpeed: { value: 0.6 },
            uColorCyan: { value: this.currentColor1 },
            uColorMagenta: { value: this.currentColor2 },
            uColorPurple: { value: this.currentColor3 }
        };

        const geometry = new THREE.IcosahedronGeometry(2.5, 128);
        const material = new THREE.ShaderMaterial({
            vertexShader: vertexShaderCode,
            fragmentShader: fragmentShaderCode,
            uniforms: this.orbUniforms,
            wireframe: false,
            transparent: true,
            side: THREE.DoubleSide,
            blending: THREE.AdditiveBlending,
            depthWrite: false
        });

        this.orb = new THREE.Mesh(geometry, material);
        this.coreGroup.add(this.orb);
    }

    setupParticles() {
        const particleCount = 200;
        const geometry = new THREE.BufferGeometry();
        const positions = new Float32Array(particleCount * 3);
        const velocities = [];

        for (let i = 0; i < particleCount; i++) {
            positions[i * 3] = (Math.random() - 0.5) * 10;
            positions[i * 3 + 1] = (Math.random() - 0.5) * 10;
            positions[i * 3 + 2] = (Math.random() - 0.5) * 10;
            velocities.push({
                x: (Math.random() - 0.5) * 0.02,
                y: (Math.random() - 0.5) * 0.02,
                z: (Math.random() - 0.5) * 0.02
            });
        }

        geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

        const material = new THREE.PointsMaterial({
            color: 0x00f3ff,
            size: 0.05,
            transparent: true,
            opacity: 0.6,
            blending: THREE.AdditiveBlending
        });

        this.particles = new THREE.Points(geometry, material);
        this.particleVelocities = velocities;
        this.scene.add(this.particles);
    }

    onWindowResize() {
        if (!this.container) return;
        const w = this.container.clientWidth;
        const h = this.container.clientHeight;
        if (w === 0 || h === 0) return;

        this.camera.aspect = w / h;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(w, h);
    }

    destroy() {
        window.removeEventListener('resize', this._resizeHandler);
        if (this.orb) {
            this.orb.geometry.dispose();
            this.orb.material.dispose();
        }
        if (this.particles) {
            this.particles.geometry.dispose();
            this.particles.material.dispose();
        }
        if (this.renderer) {
            this.renderer.dispose();
            this.renderer.forceContextLoss();
            this.renderer.domElement.remove();
        }
    }

    render(time) {
        this.currentAmplitude += (this.targetAmplitude - this.currentAmplitude) * 0.1;
        
        // Lerp colors
        this.currentColor1.lerp(this.targetColor1, 0.05);
        this.currentColor2.lerp(this.targetColor2, 0.05);
        this.currentColor3.lerp(this.targetColor3, 0.05);
        
        this.orbUniforms.uTime.value = time * 0.001;
        this.orbUniforms.uAmplitude.value = this.currentAmplitude;
        
        let targetIntensity = 0.18;
        let targetSpeed = 0.4;
        
        if (this.currentState === 'THINKING') {
            targetIntensity = 0.3;
            targetSpeed = 1.5;
        } else if (this.currentState === 'STREAMING') {
            targetIntensity = 0.2 + this.currentAmplitude * 0.8;
            targetSpeed = 1.0 + this.currentAmplitude * 5.5;
        }
        
        this.orbUniforms.uNoiseIntensity.value += (targetIntensity - this.orbUniforms.uNoiseIntensity.value) * 0.05;
        this.orbUniforms.uNoiseSpeed.value += (targetSpeed - this.orbUniforms.uNoiseSpeed.value) * 0.05;

        this.orb.rotation.y += 0.003 + this.currentAmplitude * 0.02;
        this.orb.rotation.x += 0.002 + this.currentAmplitude * 0.01;

        if (this.particles) {
            const positions = this.particles.geometry.attributes.position.array;
            const speedMultiplier = 1.0 + (this.currentAmplitude * 5.0);
            for (let i = 0; i < positions.length / 3; i++) {
                positions[i * 3] += this.particleVelocities[i].x * speedMultiplier;
                positions[i * 3 + 1] += this.particleVelocities[i].y * speedMultiplier;
                positions[i * 3 + 2] += this.particleVelocities[i].z * speedMultiplier;

                if (Math.abs(positions[i * 3]) > 5) positions[i * 3] *= -0.9;
                if (Math.abs(positions[i * 3 + 1]) > 5) positions[i * 3 + 1] *= -0.9;
                if (Math.abs(positions[i * 3 + 2]) > 5) positions[i * 3 + 2] *= -0.9;
            }
            this.particles.geometry.attributes.position.needsUpdate = true;
            this.particles.rotation.y += 0.001 * speedMultiplier;
        }

        this.renderer.render(this.scene, this.camera);
    }
}
