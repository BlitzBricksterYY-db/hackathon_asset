import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { User, Calendar, DollarSign, Link2 } from "lucide-react";
import { getWorkerAssignments, getShiftAssignments } from "@/lib/api-client";
import type { GraphElements, GraphNodeData, GraphEdgeData } from "@/lib/graph-utils";

export interface InspectorPanelProps {
  runId: string;
  elements: GraphElements;
  selectedId: string | null;
  selectedType: "node" | "edge" | null;
  className?: string;
}

export function InspectorPanel({
  runId,
  elements,
  selectedId,
  selectedType,
  className,
}: InspectorPanelProps) {
  if (!selectedId || !selectedType) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle className="text-sm">Inspector</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Click on a node or edge to see details
          </p>
        </CardContent>
      </Card>
    );
  }

  if (selectedType === "node") {
    const node = elements.nodes.find((n) => n.data.id === selectedId);
    if (!node) {
      return (
        <Card className={className}>
          <CardHeader>
            <CardTitle className="text-sm">Inspector</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">Node not found</p>
          </CardContent>
        </Card>
      );
    }

    return <NodeInspector runId={runId} node={node.data} className={className} />;
  }

  if (selectedType === "edge") {
    const edge = elements.edges.find((e) => e.data.id === selectedId);
    if (!edge) {
      return (
        <Card className={className}>
          <CardHeader>
            <CardTitle className="text-sm">Inspector</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">Edge not found</p>
          </CardContent>
        </Card>
      );
    }

    return <EdgeInspector edge={edge.data} className={className} />;
  }

  return null;
}

function NodeInspector({
  runId,
  node,
  className,
}: {
  runId: string;
  node: GraphNodeData;
  className?: string;
}) {
  const isWorker = node.kind === "worker";

  const { data: assignments, isLoading } = useQuery({
    queryKey: [
      "inspectorAssignments",
      runId,
      isWorker ? "worker" : "shift",
      node.label,
    ],
    queryFn: () =>
      isWorker
        ? getWorkerAssignments(runId, node.label, { limit: 100 })
        : getShiftAssignments(runId, node.label, { limit: 100 }),
  });

  const rows = assignments?.assignments ?? [];
  const total = assignments?.pagination.total ?? 0;

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          {isWorker ? (
            <User className="h-4 w-4 text-blue-500" />
          ) : (
            <Calendar className="h-4 w-4 text-green-500" />
          )}
          <CardTitle className="text-sm">{node.label}</CardTitle>
        </div>
        <Badge variant={isWorker ? "default" : "secondary"} className="w-fit">
          {isWorker ? "Worker" : "Shift"}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Stats */}
        <div className="grid grid-cols-2 gap-2 text-sm">
          {isWorker ? (
            <>
              <div>
                <p className="text-muted-foreground text-xs">Shifts</p>
                <p className="font-semibold">{node.shiftCount}</p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs">Optimized Cost</p>
                <p className="font-semibold">
                  ${node.totalCost?.toFixed(2) ?? "0.00"}
                </p>
              </div>
            </>
          ) : (
            <div>
              <p className="text-muted-foreground text-xs">Workers Assigned</p>
              <p className="font-semibold">{node.assignedCount}</p>
            </div>
          )}
        </div>

        <Separator />

        {/* All assignments fetched from backend */}
        <div>
          <p className="text-xs text-muted-foreground mb-2">
            {isWorker ? "Assigned Shifts" : "Assigned Workers"}
            {!isLoading && total > 0 && (
              <span className="ml-1 text-muted-foreground">({total})</span>
            )}
          </p>

          {isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ) : rows.length === 0 ? (
            <span className="text-sm text-muted-foreground">None</span>
          ) : (
            <div className="space-y-1 max-h-[260px] overflow-auto">
              {rows.map((a, i) => (
                <div
                  key={i}
                  className="flex justify-between text-sm"
                >
                  <span>{isWorker ? a.shift_name : a.worker_name}</span>
                  <span className="font-mono text-muted-foreground">
                    ${a.cost.toFixed(2)}
                  </span>
                </div>
              ))}
              {total > rows.length && (
                <p className="text-xs text-muted-foreground pt-1">
                  Showing {rows.length} of {total}
                </p>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function EdgeInspector({
  edge,
  className,
}: {
  edge: GraphEdgeData;
  className?: string;
}) {
  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <Link2 className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm">Assignment</CardTitle>
        </div>
        <Badge variant="outline" className="w-fit">
          Edge
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Connection info */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm">
            <User className="h-3 w-3 text-blue-500" />
            <span className="text-muted-foreground">Worker:</span>
            <span className="font-semibold">{edge.workerName}</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <Calendar className="h-3 w-3 text-green-500" />
            <span className="text-muted-foreground">Shift:</span>
            <span className="font-semibold">{edge.shiftName}</span>
          </div>
        </div>

        <Separator />

        {/* Cost */}
        <div>
          <p className="text-xs text-muted-foreground mb-1">Labor Cost</p>
          <div className="flex items-center gap-2">
            <DollarSign className="h-4 w-4 text-muted-foreground" />
            <span className="text-2xl font-bold">{edge.cost.toFixed(2)}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
