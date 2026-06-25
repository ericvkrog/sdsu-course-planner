import { useMemo } from "react";

const NODE_W = 100;
const NODE_H = 44;
const H_GAP = 12;
const V_GAP = 52;
const PAD_X = 10;
const PAD_Y = 14;

/**
 * Prerequisite chain as a top-down pyramid tree.
 *
 * Root course is at the top (SDSU red). Each level below shows direct prereqs,
 * then their prereqs, etc. Shared prereqs (diamond pattern) appear once at
 * their deepest level so the tree stays clean.
 *
 * Props:
 *   graph        — { nodes: [{id, label, units}], edges: [{source, target}] }
 *   highlightCode — course code at the root
 */
export default function PrereqGraph({ graph, highlightCode }) {
  const layout = useMemo(
    () => computeLayout(graph, highlightCode),
    [graph, highlightCode]
  );

  if (!layout) {
    return (
      <p className="text-sm text-gray-400 text-center py-6">
        No prerequisites
      </p>
    );
  }

  const { positions, svgWidth, svgHeight, edgeList, courseInfo } = layout;

  return (
    <div className="overflow-x-auto">
      <svg
        width={svgWidth}
        height={svgHeight}
        style={{ display: "block", minWidth: svgWidth }}
      >
        {/* Connector lines — drawn first so nodes sit on top */}
        {edgeList.map(({ source, target }, i) => {
          const from = positions[target]; // target is the parent (higher up)
          const to = positions[source];   // source is the prereq (lower)
          if (!from || !to) return null;

          const x1 = from.x + NODE_W / 2;
          const y1 = from.y + NODE_H;
          const x2 = to.x + NODE_W / 2;
          const y2 = to.y;
          const midY = (y1 + y2) / 2;

          return (
            <path
              key={i}
              d={`M${x1},${y1} C${x1},${midY} ${x2},${midY} ${x2},${y2}`}
              fill="none"
              stroke="#E5E7EB"
              strokeWidth="1.5"
            />
          );
        })}

        {/* Nodes */}
        {Object.entries(positions).map(([code, pos]) => {
          const isRoot = code === highlightCode;
          const info = courseInfo[code] ?? {};

          return (
            <g key={code} transform={`translate(${pos.x},${pos.y})`}>
              <rect
                width={NODE_W}
                height={NODE_H}
                rx={7}
                fill={isRoot ? "#A6192E" : "#FFFFFF"}
                stroke={isRoot ? "#A6192E" : "#E5E7EB"}
                strokeWidth="1.5"
              />
              {/* Course code */}
              <text
                x={NODE_W / 2}
                y={17}
                textAnchor="middle"
                fontSize="11"
                fontWeight="700"
                fontFamily="ui-monospace, 'Cascadia Code', monospace"
                fill={isRoot ? "#FFFFFF" : "#111827"}
              >
                {code}
              </text>
              {/* Units */}
              <text
                x={NODE_W / 2}
                y={31}
                textAnchor="middle"
                fontSize="9"
                fill={isRoot ? "rgba(255,255,255,0.7)" : "#9CA3AF"}
              >
                {info.units > 0 ? `${info.units} units` : ""}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ── Layout engine ──────────────────────────────────────────────────────────────

function computeLayout(graph, highlightCode) {
  if (!graph?.nodes?.length) return null;

  const courseInfo = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));

  // prereqsOf[code] = direct prerequisites of code
  const prereqsOf = {};
  for (const edge of graph.edges) {
    if (!prereqsOf[edge.target]) prereqsOf[edge.target] = [];
    prereqsOf[edge.target].push(edge.source);
  }

  // Assign depth = longest path distance from root.
  // Shared prereqs (diamond patterns) sink to their deepest level.
  const nodeDepth = {};
  function assignDepth(code, d) {
    if (d > 20) return; // cycle safety
    if ((nodeDepth[code] ?? -1) >= d) return; // already found a longer path
    nodeDepth[code] = d;
    for (const prereq of prereqsOf[code] ?? []) {
      assignDepth(prereq, d + 1);
    }
  }
  assignDepth(highlightCode, 0);

  if (Object.keys(nodeDepth).length <= 1) {
    // Only the root — no prereqs to draw
    return null;
  }

  // Group nodes by depth level
  const levels = {}; // depth → [code, ...]
  for (const [code, d] of Object.entries(nodeDepth)) {
    if (!levels[d]) levels[d] = [];
    levels[d].push(code);
  }

  const maxDepth = Math.max(...Object.keys(levels).map(Number));

  // SVG width is driven by the widest level
  const widestCount = Math.max(...Object.values(levels).map((l) => l.length));
  const contentWidth = widestCount * NODE_W + (widestCount - 1) * H_GAP;
  const svgWidth = contentWidth + 2 * PAD_X;

  // Position each level: evenly spaced, centered in SVG.
  // Sort each level by the average x-position of its children (next level down)
  // to reduce edge crossings.
  const positions = {};

  for (let d = 0; d <= maxDepth; d++) {
    const nodes = levels[d];
    const y = PAD_Y + d * (NODE_H + V_GAP);

    // Sort by average child x (children are one level deeper).
    // Nodes at the deepest level or with no positioned children stay in place.
    const scored = nodes.map((code) => {
      const prereqs = prereqsOf[code] ?? [];
      const childXs = prereqs
        .filter((p) => positions[p] !== undefined)
        .map((p) => positions[p].x + NODE_W / 2);
      const avgChildX =
        childXs.length > 0
          ? childXs.reduce((a, b) => a + b, 0) / childXs.length
          : null;
      return { code, avgChildX };
    });

    // Nodes with children: sort by their avg child x.
    // Nodes without: keep their relative order from the levels array.
    scored.sort((a, b) => {
      if (a.avgChildX !== null && b.avgChildX !== null)
        return a.avgChildX - b.avgChildX;
      if (a.avgChildX !== null) return -1;
      if (b.avgChildX !== null) return 1;
      return 0;
    });

    // Evenly space the sorted nodes, centered in SVG
    const levelWidth = nodes.length * NODE_W + (nodes.length - 1) * H_GAP;
    const startX = (svgWidth - levelWidth) / 2;

    scored.forEach(({ code }, i) => {
      positions[code] = {
        x: startX + i * (NODE_W + H_GAP),
        y,
      };
    });
  }

  // Only keep edges where both endpoints are in our node set
  const placed = new Set(Object.keys(positions));
  const edgeList = graph.edges.filter(
    (e) => placed.has(e.source) && placed.has(e.target)
  );

  const svgHeight = PAD_Y + maxDepth * (NODE_H + V_GAP) + NODE_H + PAD_Y;

  return { positions, svgWidth, svgHeight, edgeList, courseInfo };
}
