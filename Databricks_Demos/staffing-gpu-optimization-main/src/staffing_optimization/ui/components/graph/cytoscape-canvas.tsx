import { useEffect, useRef, useCallback } from "react";
import cytoscape, { type Core, type EventObject, type StylesheetStyle } from "cytoscape";
import dagre from "cytoscape-dagre";
import type { GraphElements } from "@/lib/graph-utils";
import { toCytoscapeElements } from "@/lib/graph-utils";

// Register the dagre layout
cytoscape.use(dagre);

export interface CytoscapeCanvasProps {
  elements: GraphElements;
  onSelect: (id: string | null, type: "node" | "edge" | null) => void;
  selectedId: string | null;
  className?: string;
}

// Cytoscape doesn't support CSS variables, so we define colors directly
const COLORS = {
  // Edge colors (neutral gray that works on dark/light backgrounds)
  edgeDefault: "#6b7280", // gray-500
  // Selection ring color (amber for visibility)
  ring: "#f59e0b", // amber-500
  // Node colors
  workerBg: "#3b82f6", // blue-500
  workerBorder: "#2563eb", // blue-600
  workerTextOutline: "#1d4ed8", // blue-700
  shiftBg: "#22c55e", // green-500
  shiftBorder: "#16a34a", // green-600
  shiftTextOutline: "#15803d", // green-700
};

/**
 * Get Cytoscape stylesheet for the graph
 */
function getStylesheet(): StylesheetStyle[] {
  return [
    // Base node styles
    {
      selector: "node",
      style: {
        label: "data(label)",
        "text-valign": "center",
        "text-halign": "center",
        "font-size": "11px",
        "font-weight": 500,
        "text-wrap": "ellipsis",
        "text-max-width": "80px",
        color: "#ffffff",
        "text-outline-width": "1px",
      },
    },
    // Worker nodes (blue circles)
    {
      selector: 'node[kind = "worker"]',
      style: {
        shape: "ellipse",
        "background-color": COLORS.workerBg,
        width: "50px",
        height: "50px",
        "border-width": "2px",
        "border-color": COLORS.workerBorder,
        "text-outline-color": COLORS.workerTextOutline,
      },
    },
    // Shift nodes (green rectangles)
    {
      selector: 'node[kind = "shift"]',
      style: {
        shape: "round-rectangle",
        "background-color": COLORS.shiftBg,
        width: "70px",
        height: "40px",
        "border-width": "2px",
        "border-color": COLORS.shiftBorder,
        "text-outline-color": COLORS.shiftTextOutline,
      },
    },
    // Base edge styles
    {
      selector: "edge",
      style: {
        width: 2,
        "line-color": COLORS.edgeDefault,
        "target-arrow-color": COLORS.edgeDefault,
        "target-arrow-shape": "triangle",
        "curve-style": "bezier",
        opacity: 0.6,
      },
    },
    // Selected node
    {
      selector: "node:selected",
      style: {
        "border-width": "4px",
        "border-color": COLORS.ring,
        "background-opacity": 1,
      },
    },
    // Selected edge
    {
      selector: "edge:selected",
      style: {
        width: 4,
        "line-color": COLORS.ring,
        "target-arrow-color": COLORS.ring,
        opacity: 1,
      },
    },
    // Highlighted (connected to selected)
    {
      selector: ".highlighted",
      style: {
        opacity: 1,
      },
    },
    // Dimmed (not connected to selected)
    {
      selector: ".dimmed",
      style: {
        opacity: 0.2,
      },
    },
  ];
}

/**
 * Get layout configuration for bipartite graph
 */
function getLayoutConfig(): cytoscape.LayoutOptions {
  return {
    name: "dagre",
    rankDir: "LR", // Left to right
    nodeSep: 30,
    rankSep: 150,
    padding: 30,
    animate: true,
    animationDuration: 300,
    fit: true,
  } as cytoscape.LayoutOptions;
}

export function CytoscapeCanvas({
  elements,
  onSelect,
  selectedId,
  className,
}: CytoscapeCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);

  // Initialize Cytoscape
  useEffect(() => {
    if (!containerRef.current) return;

    const cy = cytoscape({
      container: containerRef.current,
      elements: toCytoscapeElements(elements),
      style: getStylesheet(),
      layout: getLayoutConfig(),
      minZoom: 0.2,
      maxZoom: 3,
    });

    cyRef.current = cy;

    // Handle tap on canvas (deselect)
    cy.on("tap", (event: EventObject) => {
      if (event.target === cy) {
        onSelect(null, null);
      }
    });

    // Handle node selection
    cy.on("tap", "node", (event: EventObject) => {
      const node = event.target;
      onSelect(node.id(), "node");
    });

    // Handle edge selection
    cy.on("tap", "edge", (event: EventObject) => {
      const edge = event.target;
      onSelect(edge.id(), "edge");
    });

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, []); // Only run once on mount

  // Update elements when they change
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    // Batch the update
    cy.batch(() => {
      // Remove all existing elements
      cy.elements().remove();

      // Add new elements
      cy.add(toCytoscapeElements(elements));
    });

    // Run layout
    cy.layout(getLayoutConfig()).run();
  }, [elements]);

  // Handle selection highlighting
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    // Clear all classes
    cy.elements().removeClass("highlighted dimmed");

    if (!selectedId) return;

    const selected = cy.getElementById(selectedId);
    if (!selected || selected.empty()) return;

    // Get connected elements based on whether it's a node or edge
    let connected;
    if (selected.isNode()) {
      // For nodes: get connected edges and neighboring nodes
      connected = selected.connectedEdges().union(selected.neighborhood("node"));
    } else {
      // For edges: get the source and target nodes
      const edge = selected as cytoscape.EdgeSingular;
      connected = edge.source().union(edge.target()).union(selected);
    }

    // Dim non-connected elements
    cy.elements().not(connected).not(selected).addClass("dimmed");
    connected.addClass("highlighted");
  }, [selectedId]);

  // Fit graph to viewport
  const handleFit = useCallback(() => {
    cyRef.current?.fit(undefined, 30);
  }, []);

  // Reset layout
  const handleResetLayout = useCallback(() => {
    cyRef.current?.layout(getLayoutConfig()).run();
  }, []);

  return (
    <div className={`relative ${className || ""}`}>
      <div
        ref={containerRef}
        className="w-full h-full bg-muted/30 rounded-lg border"
      />
      <div className="absolute top-2 right-2 flex gap-1">
        <button
          onClick={handleFit}
          className="p-2 bg-background/80 hover:bg-background rounded-md border text-xs"
          title="Fit to view"
        >
          Fit
        </button>
        <button
          onClick={handleResetLayout}
          className="p-2 bg-background/80 hover:bg-background rounded-md border text-xs"
          title="Reset layout"
        >
          Reset
        </button>
      </div>
    </div>
  );
}
