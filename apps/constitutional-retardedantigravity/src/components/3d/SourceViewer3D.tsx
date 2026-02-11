import { useMemo, useRef } from "react";
import { useAppStore, type Source } from "../../stores/useAppStore";
import { Text } from "@react-three/drei";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { EVIDENCE_COLORS, DEFAULT_STAGE_COLORS } from "../../theme/colors";

/**
 * SourceViewer3D - Clean 3D source visualization on the LEFT side.
 * Now confidence-aware: card materials shift to amber/emerald/red
 * based on the current query's evidenceLevel.
 */

const EMPTY_SOURCES: Source[] = [];

// Reusable THREE.Color instances for lerping (avoids GC pressure)
const _colorA = new THREE.Color();
const _colorB = new THREE.Color();

export function SourceViewer3D() {
  const queries = useAppStore((state) => state.queries);
  const focusedQueryId = useAppStore((state) => state.focusedQueryId);

  const { sources, evidenceLevel } = useMemo(() => {
    const q = queries.find((x) => x.id === focusedQueryId);
    return {
      sources: q?.sources ?? EMPTY_SOURCES,
      evidenceLevel: (q?.evidenceLevel as keyof typeof EVIDENCE_COLORS) ?? null,
    };
  }, [queries, focusedQueryId]);

  const activeSourceId = useAppStore((state) => state.activeSourceId);
  const hoveredSourceId = useAppStore((state) => state.hoveredSourceId);
  const citationTarget = useAppStore((state) => state.citationTarget);

  const focusSourceId =
    citationTarget && hoveredSourceId ? hoveredSourceId : activeSourceId;

  // Resolve 3D material colors from evidence level
  const palette = useMemo(() => {
    if (evidenceLevel && EVIDENCE_COLORS[evidenceLevel]) {
      return EVIDENCE_COLORS[evidenceLevel];
    }
    return DEFAULT_STAGE_COLORS;
  }, [evidenceLevel]);

  if (sources.length === 0) return null;

  return (
    <group position={[-5.5, 1.5, 2]}>
      {sources.slice(0, 5).map((source: Source, index: number) => (
        <SourceCard3D
          key={source.id}
          source={source}
          index={index}
          isActive={focusSourceId === source.id}
          palette={palette}
        />
      ))}
    </group>
  );
}

interface PaletteColors {
  readonly emissive: string;
  readonly wireframe: string;
  readonly accentBar: string;
  readonly label: string;
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
  palette: PaletteColors;
}

function SourceCard3D({ source, index, isActive, palette }: SourceCard3DProps) {
  const meshRef = useRef<THREE.Group>(null);
  const emissiveRef = useRef<THREE.MeshPhysicalMaterial>(null);
  const wireframeRef = useRef<THREE.MeshBasicMaterial>(null);
  const accentBarRef = useRef<THREE.MeshBasicMaterial>(null);

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

    // Smooth color transitions for materials
    if (emissiveRef.current && isActive) {
      _colorA.set(palette.emissive);
      emissiveRef.current.emissive.lerp(_colorA, 0.08);
    }
    if (wireframeRef.current) {
      const targetWireColor = isActive ? palette.wireframe : "#cbd5e1";
      _colorB.set(targetWireColor);
      wireframeRef.current.color.lerp(_colorB, 0.08);
    }
    if (accentBarRef.current) {
      _colorA.set(palette.accentBar);
      accentBarRef.current.color.lerp(_colorA, 0.08);
    }
  });

  // 3-tier score coloring: emerald (≥0.7), amber (≥0.4), red (<0.4)
  const scoreColor =
    source.score >= 0.7
      ? "#059669"
      : source.score >= 0.4
        ? "#d97706"
        : "#dc2626";

  return (
    <group ref={meshRef} position={[0, yOffset, 0]}>
      {/* Glass Card Body */}
      <mesh>
        <boxGeometry args={[2.8, 0.7, 0.1]} />
        <meshPhysicalMaterial
          ref={emissiveRef}
          color={isActive ? "#f8fafc" : "#e2e8f0"}
          transparent
          opacity={isActive ? 0.9 : 0.7}
          roughness={0.4}
          metalness={0.1}
          clearcoat={0.5}
          clearcoatRoughness={0.1}
          emissive={isActive ? palette.emissive : "#000000"}
          emissiveIntensity={isActive ? 0.05 : 0}
        />
      </mesh>

      {/* Glowing Edge/Outline */}
      <mesh position={[0, 0, 0.06]}>
        <boxGeometry args={[2.82, 0.72, 0.02]} />
        <meshBasicMaterial
          ref={wireframeRef}
          color={isActive ? palette.wireframe : "#cbd5e1"}
          transparent
          opacity={isActive ? 0.8 : 0.5}
          wireframe
        />
      </mesh>

      {/* Active Accent Bar */}
      {isActive && (
        <mesh position={[-1.35, 0, 0.08]}>
          <boxGeometry args={[0.08, 0.6, 0.02]} />
          <meshBasicMaterial
            ref={accentBarRef}
            color={palette.accentBar}
            toneMapped={false}
          />
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
        color={isActive ? "#0f172a" : "#475569"}
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
          color={palette.label}
        >
          {source.doc_type.toUpperCase()}
        </Text>

        {/* Score - 3-tier coloring */}
        <Text
          position={[0.5, 0, 0]}
          anchorX="left"
          anchorY="middle"
          fontSize={0.07}
          color={scoreColor}
        >
          {Math.round(source.score * 100)}% MATCH
        </Text>
      </group>
    </group>
  );
}
