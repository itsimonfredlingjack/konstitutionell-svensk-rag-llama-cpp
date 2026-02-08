import { useMemo, useRef } from "react";
import { useAppStore, type Source } from "../../stores/useAppStore";
import { Text } from "@react-three/drei";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";

/**
 * SourceViewer3D - Clean 3D source visualization on the LEFT side.
 */

const EMPTY_SOURCES: Source[] = [];

export function SourceViewer3D() {
  const queries = useAppStore((state) => state.queries);
  const focusedQueryId = useAppStore((state) => state.focusedQueryId);
  const sources = useMemo(() => {
    const q = queries.find((x) => x.id === focusedQueryId);
    return q?.sources ?? EMPTY_SOURCES;
  }, [queries, focusedQueryId]);
  const activeSourceId = useAppStore((state) => state.activeSourceId);
  const hoveredSourceId = useAppStore((state) => state.hoveredSourceId);
  const citationTarget = useAppStore((state) => state.citationTarget);

  const focusSourceId =
    citationTarget && hoveredSourceId ? hoveredSourceId : activeSourceId;

  if (sources.length === 0) return null;

  return (
    <group position={[-5.5, 1.5, 2]}>
      {sources.slice(0, 5).map((source: Source, index: number) => (
        <SourceCard3D
          key={source.id}
          source={source}
          index={index}
          isActive={focusSourceId === source.id}
        />
      ))}
    </group>
  );
}

interface SourceCard3DProps {
  source: {
    id: string;
    title: string;
    doc_type: string;
    score: number;
  };
  index: number;
  isActive: boolean;
}

function SourceCard3D({ source, index, isActive }: SourceCard3DProps) {
  const meshRef = useRef<THREE.Group>(null);
  // Larger vertical spacing
  const yOffset = -index * 0.85;

  useFrame((state) => {
    if (!meshRef.current) return;

    // Gentle floating
    const t = state.clock.getElapsedTime();
    meshRef.current.position.y = THREE.MathUtils.lerp(
      meshRef.current.position.y,
      yOffset + Math.sin(t * 0.4 + index * 0.5) * 0.03,
      0.1,
    );

    // Move forward and scale up when active
    const targetZ = isActive ? 0.8 : 0;
    const targetScale = isActive ? 1.05 : 1.0;

    meshRef.current.position.z = THREE.MathUtils.lerp(
      meshRef.current.position.z,
      targetZ,
      0.1,
    );
    meshRef.current.scale.setScalar(
      THREE.MathUtils.lerp(meshRef.current.scale.x, targetScale, 0.1),
    );
  });

  return (
    <group ref={meshRef} position={[0, yOffset, 0]}>
      {/* Glass Card Body */}
      <mesh>
        <boxGeometry args={[2.8, 0.7, 0.1]} />
        <meshPhysicalMaterial
          color={isActive ? "#f8fafc" : "#e2e8f0"} // Light paper/slate
          transparent
          opacity={isActive ? 0.9 : 0.7}
          roughness={0.4} // Matte paper feel
          metalness={0.1}
          clearcoat={0.5}
          clearcoatRoughness={0.1}
          emissive={isActive ? "#0e7490" : "#000000"} // Cyan-700
          emissiveIntensity={isActive ? 0.05 : 0}
        />
      </mesh>

      {/* Glowing Edge/Outline */}
      <mesh position={[0, 0, 0.06]}>
        <boxGeometry args={[2.82, 0.72, 0.02]} />
        <meshBasicMaterial
          color={isActive ? "#0891b2" : "#cbd5e1"} // Cyan-600 or Slate-300
          transparent
          opacity={isActive ? 0.8 : 0.5}
          wireframe
        />
      </mesh>

      {/* Active Accent Bar */}
      {isActive && (
        <mesh position={[-1.35, 0, 0.08]}>
          <boxGeometry args={[0.08, 0.6, 0.02]} />
          <meshBasicMaterial color="#0891b2" toneMapped={false} />
        </mesh>
      )}

      {/* Title Text */}
      <Text
        position={[-1.2, 0.12, 0.08]}
        anchorX="left"
        anchorY="middle"
        fontSize={0.11}
        maxWidth={2.4}
        font="/fonts/JetBrainsMono-Regular.woff2"
        color={isActive ? "#0f172a" : "#475569"} // Slate-900 or Slate-600
      >
        {source.title.length > 45
          ? source.title.substring(0, 45) + "..."
          : source.title}
      </Text>

      {/* Metadata (Type + Score) */}
      <group position={[-1.2, -0.15, 0.08]}>
        {/* Doc Type Badge */}
        <Text
          position={[0, 0, 0]}
          anchorX="left"
          anchorY="middle"
          fontSize={0.07}
          font="/fonts/JetBrainsMono-Regular.woff2"
          color="#0891b2" // Cyan-600
        >
          {source.doc_type.toUpperCase()}
        </Text>

        {/* Score */}
        <Text
          position={[0.5, 0, 0]}
          anchorX="left"
          anchorY="middle"
          fontSize={0.07}
          color={source.score > 0.7 ? "#059669" : "#d97706"} // Emerald-600 or Amber-600
        >
          {Math.round(source.score * 100)}% MATCH
        </Text>
      </group>
    </group>
  );
}
