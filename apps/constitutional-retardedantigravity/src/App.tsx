import React, { Suspense, useState, useRef, useMemo } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { TrustHull } from "./components/ui/TrustHull";
import {
  EffectComposer,
  Noise,
  Vignette,
  Bloom,
  TiltShift2,
} from "@react-three/postprocessing";
import { COLORS, EVIDENCE_COLORS } from "./theme/colors";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { useAppStore } from "./stores/useAppStore";
import * as THREE from "three";

// Lazy-load heavy 3D components for faster initial paint
const Substrate = React.lazy(() =>
  import("./components/3d/Substrate").then((m) => ({ default: m.Substrate })),
);
const SourceViewer3D = React.lazy(() =>
  import("./components/3d/SourceViewer3D").then((m) => ({
    default: m.SourceViewer3D,
  })),
);
const ConnectorLogic = React.lazy(() =>
  import("./components/3d/ConnectorLogic").then((m) => ({
    default: m.ConnectorLogic,
  })),
);

/** Dynamic amber point light — intensity reacts to the current evidence level. */
function AmberLight() {
  const lightRef = useRef<THREE.PointLight>(null);
  const queries = useAppStore((s) => s.queries);
  const focusedQueryId = useAppStore((s) => s.focusedQueryId);

  const evidenceLevel = useMemo(() => {
    const q = queries.find((x) => x.id === focusedQueryId);
    return (q?.evidenceLevel as keyof typeof EVIDENCE_COLORS) ?? null;
  }, [queries, focusedQueryId]);

  useFrame(() => {
    if (!lightRef.current) return;
    // MEDIUM → warmer glow (0.8), LOW → subdued (0.3), HIGH/null → default (0.4)
    const targetIntensity =
      evidenceLevel === "MEDIUM" ? 0.8 : evidenceLevel === "LOW" ? 0.3 : 0.4;
    lightRef.current.intensity = THREE.MathUtils.lerp(
      lightRef.current.intensity,
      targetIntensity,
      0.05,
    );
  });

  return (
    <pointLight
      ref={lightRef}
      position={[-10, 5, -10]}
      intensity={0.4}
      color={COLORS.accentSecondary}
    />
  );
}

function App() {
  const [isHighPerformance] = useState(() => {
    if (typeof window === "undefined") return true;
    // Check pixel ratio. If > 2 (Retina/HighDPI) or mobile agent, assume restricted performance budget.
    const pixelRatio = window.devicePixelRatio;
    const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
    return !(pixelRatio > 2 || isMobile);
  });

  return (
    <div
      className="w-screen h-screen overflow-hidden relative"
      style={{ backgroundColor: COLORS.background }}
    >
      {/* ===== LAYER 0: 3D Background (Fixed, Z-0) ===== */}
      <div className="fixed inset-0 z-0 pointer-events-none">
        <ErrorBoundary>
          <Canvas
            dpr={isHighPerformance ? [1, 2] : [1, 1.5]} // Cap DPR on lower end
            camera={{ position: [0, 2, 8], fov: 50 }}
            gl={{ antialias: true, powerPreference: "high-performance" }}
          >
            <color attach="background" args={[COLORS.background]} />
            <fog attach="fog" args={[COLORS.background, 5, 25]} />

            <ambientLight intensity={0.8} />
            <pointLight
              position={[10, 10, 10]}
              intensity={0.6}
              color={COLORS.accentPrimary}
            />
            <AmberLight />

            <Suspense fallback={null}>
              <Substrate />

              {/* 3D Source Visualization (Left side) */}
              <SourceViewer3D />
              <ConnectorLogic />
            </Suspense>

            <EffectComposer
              multisampling={isHighPerformance ? 4 : 0}
              enableNormalPass={isHighPerformance}
            >
              <Bloom
                luminanceThreshold={0.8}
                mipmapBlur
                intensity={0.2}
                radius={0.2}
              />
              <Vignette eskil={false} offset={0.1} darkness={0.4} />
              {isHighPerformance ? <Noise opacity={0.01} /> : <></>}
              <TiltShift2 blur={0.05} />
            </EffectComposer>
          </Canvas>
        </ErrorBoundary>
      </div>

      {/* ===== LAYER 1: UI Overlay (Relative, Z-10) ===== */}
      <div className="relative z-10 w-full h-full">
        <TrustHull />
      </div>
    </div>
  );
}

export default App;
