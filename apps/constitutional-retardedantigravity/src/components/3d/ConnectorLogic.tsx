import { useMemo, useRef } from "react";
import { useAppStore, type Source } from "../../stores/useAppStore";
import { useThree, useFrame } from "@react-three/fiber";
import * as THREE from "three";

// This component runs inside the Canvas to project 3D card positions to 2D screen coords.
// It updates the Zustand store, which the 2D ConnectorOverlay reads.

const EMPTY_SOURCES: Source[] = [];

export function ConnectorLogic() {
  const activeSourceId = useAppStore((s) => s.activeSourceId);
  const hoveredSourceId = useAppStore((s) => s.hoveredSourceId);
  const citationTarget = useAppStore((s) => s.citationTarget);
  const setConnectorCoords = useAppStore((s) => s.setConnectorCoords);
  const queries = useAppStore((s) => s.queries);
  const focusedQueryId = useAppStore((s) => s.focusedQueryId);
  const sources = useMemo(() => {
    const q = queries.find((x) => x.id === focusedQueryId);
    return q?.sources ?? EMPTY_SOURCES;
  }, [queries, focusedQueryId]);
  const { camera, size } = useThree();
  const lastCoords = useRef<{ x: number; y: number } | null>(null);

  useFrame(() => {
    const focusSourceId =
      citationTarget && hoveredSourceId ? hoveredSourceId : activeSourceId;

    if (!focusSourceId) {
      if (lastCoords.current !== null) {
        setConnectorCoords(null);
        lastCoords.current = null;
      }
      return;
    }

    const sourceIndex = sources.findIndex(
      (s: { id: string }) => s.id === focusSourceId,
    );
    if (sourceIndex === -1) {
      if (lastCoords.current !== null) {
        setConnectorCoords(null);
        lastCoords.current = null;
      }
      return;
    }

    // Match SourceViewer3D.tsx positioning:
    // Group Position: [-5.5, 1.5, 2]
    // Card Local Y: -index * 0.85
    // Card Local Z: isActive ? 0.8 : 0

    // World coordinates of active card center:
    const x = -5.5;
    const y = 1.5 - sourceIndex * 0.85;
    const z = 2 + 0.8; // Group Z + Active Z Offset

    const vec = new THREE.Vector3(x, y, z);
    vec.project(camera);

    // Convert NDC to screen pixels
    const x2 = (vec.x * 0.5 + 0.5) * size.width;
    const y2 = (-(vec.y * 0.5) + 0.5) * size.height;

    // Optimization: Only update if coordinates changed significantly (> 1px)
    if (
      !lastCoords.current ||
      Math.abs(lastCoords.current.x - x2) > 1 ||
      Math.abs(lastCoords.current.y - y2) > 1
    ) {
      setConnectorCoords({ x: x2, y: y2 });
      lastCoords.current = { x: x2, y: y2 };
    }
  });

  return null;
}
