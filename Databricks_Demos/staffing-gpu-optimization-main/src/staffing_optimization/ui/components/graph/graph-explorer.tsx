import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getFocusedGraph,
  getShiftAggregates,
  getWorkerAggregates,
} from "@/lib/api-client";
import { CytoscapeCanvas } from "./cytoscape-canvas";
import { InspectorPanel } from "./inspector-panel";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DollarSign, Users, Calendar, Link2, Search, X, AlertTriangle } from "lucide-react";
import type { GraphElements, FilterState } from "@/lib/graph-utils";
import { applyFilters, calculateGraphStats, defaultFilterState } from "@/lib/graph-utils";
import { FiltersPanel } from "./filters-panel";

export interface GraphExplorerProps {
  runId: string;
}

export function GraphExplorer({ runId }: GraphExplorerProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedType, setSelectedType] = useState<"node" | "edge" | null>(null);
  const [filters, setFilters] = useState<FilterState>(defaultFilterState);

  const [focusType, setFocusType] = useState<"shift" | "worker" | null>(null);
  const [focusEntity, setFocusEntity] = useState<string | null>(null);

  const { data: graphData, isLoading } = useQuery({
    queryKey: ["focusedGraph", runId, focusType, focusEntity],
    queryFn: () =>
      getFocusedGraph(runId, {
        shift_name: focusType === "shift" ? focusEntity! : undefined,
        worker_name: focusType === "worker" ? focusEntity! : undefined,
        limit: 500,
      }),
  });

  const graphElements = useMemo((): GraphElements => {
    if (!graphData || (!graphData.nodes.length && !graphData.edges.length)) {
      return { nodes: [], edges: [] };
    }
    return {
      nodes: graphData.nodes.map((n) => ({
        data: {
          id: n.id,
          kind: n.kind as "worker" | "shift",
          label: n.label,
          totalCost: n.totalCost,
          assignedCount: n.assignedCount,
        },
      })),
      edges: graphData.edges.map((e) => ({
        data: {
          id: e.id,
          source: e.source,
          target: e.target,
          cost: e.cost,
          workerName: e.workerName,
          shiftName: e.shiftName,
        },
      })),
    };
  }, [graphData]);

  const stats = useMemo(() => calculateGraphStats(graphElements), [graphElements]);
  const filteredElements = useMemo(
    () => applyFilters(graphElements, filters),
    [graphElements, filters],
  );
  const filteredStats = useMemo(
    () => calculateGraphStats(filteredElements),
    [filteredElements],
  );

  const handleSelect = (id: string | null, type: "node" | "edge" | null) => {
    setSelectedId(id);
    setSelectedType(type);
  };

  const clearFocus = () => {
    setFocusType(null);
    setFocusEntity(null);
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-4 gap-4">
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
        </div>
        <Skeleton className="h-[500px]" />
      </div>
    );
  }

  // Large graph that needs focus selection
  if (graphData && !graphData.is_complete && !focusEntity) {
    return (
      <LargeGraphFallback
        runId={runId}
        totalNodes={graphData.total_nodes}
        totalEdges={graphData.total_edges}
        onSelectFocus={(type, name) => {
          setFocusType(type);
          setFocusEntity(name);
        }}
      />
    );
  }

  if (!graphData) {
    return (
      <Card>
        <CardContent className="py-8 text-center">
          <p className="text-muted-foreground">No graph data available</p>
        </CardContent>
      </Card>
    );
  }

  const isFiltered =
    filters.search !== "" ||
    filters.costRange[0] !== 0 ||
    filters.costRange[1] !== Infinity ||
    !filters.showWorkers ||
    !filters.showShifts;

  return (
    <div className="space-y-4">
      {/* Focus indicator */}
      {focusEntity && (
        <div className="flex items-center gap-2">
          <Badge variant="secondary">
            Focused: {focusType === "shift" ? "Shift" : "Worker"} &quot;{focusEntity}&quot;
          </Badge>
          <Button variant="ghost" size="sm" onClick={clearFocus}>
            <X className="h-3 w-3 mr-1" /> Clear focus
          </Button>
          {!graphData.is_complete && (
            <span className="text-xs text-muted-foreground">
              Showing neighbourhood ({graphData.edges.length} of {graphData.total_edges} edges)
            </span>
          )}
        </div>
      )}

      {/* KPI Header */}
      <div className="grid grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Optimized Cost</p>
                <p className="text-2xl font-bold">
                  ${stats.totalCost.toFixed(2)}
                </p>
              </div>
              <DollarSign className="h-8 w-8 text-muted-foreground/50" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Workers</p>
                <p className="text-2xl font-bold">
                  {isFiltered ? (
                    <>
                      {filteredStats.workerCount}
                      <span className="text-sm text-muted-foreground font-normal">
                        {" "} / {stats.workerCount}
                      </span>
                    </>
                  ) : (
                    stats.workerCount
                  )}
                </p>
              </div>
              <Users className="h-8 w-8 text-blue-500/50" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Shifts</p>
                <p className="text-2xl font-bold">
                  {isFiltered ? (
                    <>
                      {filteredStats.shiftCount}
                      <span className="text-sm text-muted-foreground font-normal">
                        {" "} / {stats.shiftCount}
                      </span>
                    </>
                  ) : (
                    stats.shiftCount
                  )}
                </p>
              </div>
              <Calendar className="h-8 w-8 text-green-500/50" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Assignments</p>
                <p className="text-2xl font-bold">
                  {isFiltered ? (
                    <>
                      {filteredStats.assignmentCount}
                      <span className="text-sm text-muted-foreground font-normal">
                        {" "} / {stats.assignmentCount}
                      </span>
                    </>
                  ) : (
                    stats.assignmentCount
                  )}
                </p>
              </div>
              <Link2 className="h-8 w-8 text-muted-foreground/50" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filter indicator */}
      {isFiltered && (
        <div className="flex items-center gap-2">
          <Badge variant="secondary">Filtered View</Badge>
          <span className="text-sm text-muted-foreground">
            Showing {filteredStats.assignmentCount} of {stats.assignmentCount}{" "}
            assignments
          </span>
        </div>
      )}

      {/* Main content: Filters | Graph | Inspector */}
      <div className="grid grid-cols-[240px_1fr_280px] gap-4 h-[500px]">
        <FiltersPanel
          filters={filters}
          onFiltersChange={setFilters}
          stats={stats}
          className="h-full overflow-auto"
        />

        <CytoscapeCanvas
          elements={filteredElements}
          onSelect={handleSelect}
          selectedId={selectedId}
          className="h-full"
        />

        <InspectorPanel
          runId={runId}
          elements={filteredElements}
          selectedId={selectedId}
          selectedType={selectedType}
          className="h-full overflow-auto"
        />
      </div>
    </div>
  );
}

// ============== Large Graph Fallback ==============

function LargeGraphFallback({
  runId,
  totalNodes,
  totalEdges,
  onSelectFocus,
}: {
  runId: string;
  totalNodes: number;
  totalEdges: number;
  onSelectFocus: (type: "shift" | "worker", name: string) => void;
}) {
  const [tab, setTab] = useState<"shift" | "worker">("shift");
  const [search, setSearch] = useState("");

  const { data: shifts } = useQuery({
    queryKey: ["shiftAggregatesForGraph", runId],
    queryFn: () => getShiftAggregates(runId, { limit: 500 }),
  });

  const { data: workers } = useQuery({
    queryKey: ["workerAggregatesForGraph", runId],
    queryFn: () => getWorkerAggregates(runId, { limit: 500 }),
  });

  const filteredShifts = shifts?.shifts.filter(
    (s) => s.shift_name.toLowerCase().includes(search.toLowerCase()),
  ) ?? [];

  const filteredWorkers = workers?.workers.filter(
    (w) => w.worker_name.toLowerCase().includes(search.toLowerCase()),
  ) ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-yellow-500" />
          Large Graph - Select a Focus
        </CardTitle>
        <CardDescription>
          This result has {totalNodes.toLocaleString()} nodes and{" "}
          {totalEdges.toLocaleString()} edges, which is too large to render at once.
          Select a shift or worker below to explore its neighbourhood.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2">
          <Button
            variant={tab === "shift" ? "default" : "outline"}
            size="sm"
            onClick={() => setTab("shift")}
          >
            <Calendar className="h-4 w-4 mr-1" />
            Browse Shifts
          </Button>
          <Button
            variant={tab === "worker" ? "default" : "outline"}
            size="sm"
            onClick={() => setTab("worker")}
          >
            <Users className="h-4 w-4 mr-1" />
            Browse Workers
          </Button>
        </div>

        <div className="relative">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder={`Search ${tab === "shift" ? "shifts" : "workers"}...`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8"
          />
        </div>

        <div className="max-h-[300px] overflow-auto border rounded-lg">
          {tab === "shift" ? (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-background border-b">
                <tr>
                  <th className="text-left px-3 py-2 font-medium">Shift</th>
                  <th className="text-right px-3 py-2 font-medium">Workers</th>
                  <th className="text-right px-3 py-2 font-medium">Cost</th>
                </tr>
              </thead>
              <tbody>
                {filteredShifts.map((s) => (
                  <tr
                    key={s.shift_name}
                    className="border-b cursor-pointer hover:bg-muted/50"
                    onClick={() => onSelectFocus("shift", s.shift_name)}
                  >
                    <td className="px-3 py-2 font-medium">{s.shift_name}</td>
                    <td className="px-3 py-2 text-right">{s.assigned_count}</td>
                    <td className="px-3 py-2 text-right">${s.total_cost.toFixed(2)}</td>
                  </tr>
                ))}
                {filteredShifts.length === 0 && (
                  <tr>
                    <td colSpan={3} className="text-center text-muted-foreground py-4">
                      {shifts ? "No matching shifts" : "Loading..."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-background border-b">
                <tr>
                  <th className="text-left px-3 py-2 font-medium">Worker</th>
                  <th className="text-right px-3 py-2 font-medium">Shifts</th>
                  <th className="text-right px-3 py-2 font-medium">Cost</th>
                </tr>
              </thead>
              <tbody>
                {filteredWorkers.map((w) => (
                  <tr
                    key={w.worker_name}
                    className="border-b cursor-pointer hover:bg-muted/50"
                    onClick={() => onSelectFocus("worker", w.worker_name)}
                  >
                    <td className="px-3 py-2 font-medium">{w.worker_name}</td>
                    <td className="px-3 py-2 text-right">{w.shift_count}</td>
                    <td className="px-3 py-2 text-right">${w.total_cost.toFixed(2)}</td>
                  </tr>
                ))}
                {filteredWorkers.length === 0 && (
                  <tr>
                    <td colSpan={3} className="text-center text-muted-foreground py-4">
                      {workers ? "No matching workers" : "Loading..."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
