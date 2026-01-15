import { useRef, useMemo } from 'react';
import { useFrame } from '@react-three/fiber';
import { Points, PointMaterial } from '@react-three/drei';
import * as THREE from 'three';
import { COLORS } from '../../theme/colors';

// Generate random points in a sphere (replacement for maath.random.inSphere)
function generateSpherePoints(count: number, radius: number): Float32Array {
    const points = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
        // Generate random point in sphere using rejection sampling
        let x, y, z, len;
        do {
            x = (Math.random() - 0.5) * 2;
            y = (Math.random() - 0.5) * 2;
            z = (Math.random() - 0.5) * 2;
            len = Math.sqrt(x * x + y * y + z * z);
        } while (len > 1 || len === 0);

        // Scale by radius (distribute inside volume)
        const scale = radius;
        points[i * 3] = x * scale;
        points[i * 3 + 1] = y * scale;
        points[i * 3 + 2] = z * scale;
    }
    return points;
}

export function Substrate() {
    const ref = useRef<THREE.Points>(null);

    // Generate subtle tech particles (not snow!)
    const sphere = useMemo(() => {
        return generateSpherePoints(800, 25); // Much fewer particles
    }, []);

    useFrame((state, delta) => {
        if (ref.current) {
            ref.current.rotation.x -= delta / 30;
            ref.current.rotation.y -= delta / 40;

            // Gentle wave scale pulsation
            const t = state.clock.getElapsedTime();
            ref.current.position.y = -2 + Math.sin(t / 4) * 0.2;
        }
    });

    return (
        <group rotation={[0, 0, Math.PI / 4]} position={[0, -2, 0]}>
            {/* 1. Underlying Horizon Grid (Subtle) */}
            <gridHelper args={[100, 50, '#cbd5e1', '#f1f5f9']} position={[0, -5, 0]} />

            {/* 2. Subtle Tech Particles - NOT SNOW */}
            <Points ref={ref} positions={sphere} stride={3} frustumCulled={false}>
                <PointMaterial
                    transparent
                    color={COLORS.accentPrimary}
                    size={0.02}
                    sizeAttenuation={true}
                    depthWrite={false}
                    opacity={0.15}
                />
            </Points>

            {/* 3. Ambient Glow Mesh */}
            <mesh position={[0, -8, 0]} rotation={[-Math.PI / 2, 0, 0]}>
                <planeGeometry args={[100, 100]} />
                <meshBasicMaterial color="#ffffff" transparent opacity={0.1} />
            </mesh>
        </group>
    );
}
