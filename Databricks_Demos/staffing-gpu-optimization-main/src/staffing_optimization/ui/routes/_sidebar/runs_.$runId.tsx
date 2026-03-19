import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getRun,
  getConfig,
  cancelRun,
  exportRunResults,
  saveResultsToTable,
  getWorkspaceInfo,
  refreshRunStatus,
  getRunResultsSummary,
  getPagedAssignments,
  getShiftAggregates,
  getShiftAssignments,
  getWorkerAggregates,
  getWorkerAssignments,
} from "@/lib/api-client";
import type {
  RunResultsSummary,
  PagedAssignments,
  PagedShiftAggregates,
  PagedWorkerAggregates,
} from "@/lib/api-client";
import {
  ArrowLeft,
  Download,
  Save,
  XCircle,
  CheckCircle2,
  Clock,
  Loader2,
  RefreshCw,
  Users,
  DollarSign,
  Timer,
  Network,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  ArrowUpDown,
} from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useState, Suspense } from "react";
import { toast } from "sonner";
import { GraphExplorer } from "@/components/graph";

export const Route = createFileRoute("/_sidebar/runs_/$runId")({
  component: RunDetail,
});

const PAGE_SIZE = 50;

function RunDetail() {
  const { runId } = Route.useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [saveCatalog, setSaveCatalog] = useState("demos");
  const [saveSchema, setSaveSchema] = useState("staffing_optimization");
  const [saveTable, setSaveTable] = useState(`results_${runId.slice(0, 8)}`);

  const { data: run, isLoading: runLoading, isFetching } = useQuery({
    queryKey: ["run", runId],
    queryFn: () => getRun(runId),
    refetchInterval: (query) => {
      if (query.state.data?.status === "RUNNING" || query.state.data?.status === "PENDING") {
        return 3000;
      }
      return false;
    },
  });

  const { data: summary } = useQuery({
    queryKey: ["runResultsSummary", runId],
    queryFn: () => getRunResultsSummary(runId),
    enabled: run?.status === "COMPLETED",
  });

  const { data: config } = useQuery({
    queryKey: ["config", run?.config_id],
    queryFn: () => getConfig(run!.config_id),
    enabled: !!run?.config_id,
  });

  const { data: wsInfo } = useQuery({
    queryKey: ["workspaceInfo"],
    queryFn: getWorkspaceInfo,
    staleTime: Infinity,
  });

  const databricksRunUrl = (() => {
    if (!run?.databricks_run_id) return null;
    const jobId = wsInfo?.databricks_job_id ?? config?.databricks_job_id;
    let host = wsInfo?.host?.replace(/\/$/, "");
    if (!jobId || !host) return null;
    if (!/^https?:\/\//.test(host)) host = `https://${host}`;
    return `${host}/#job/${jobId}/run/${run.databricks_run_id}`;
  })();

  const cancelMutation = useMutation({
    mutationFn: () => cancelRun(runId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["run", runId] });
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      toast.success("Run cancelled");
    },
    onError: (error) => {
      toast.error(`Failed to cancel: ${error.message}`);
    },
  });

  const refreshMutation = useMutation({
    mutationFn: () => refreshRunStatus(runId),
    onSuccess: (latestRun) => {
      queryClient.setQueryData(["run", runId], latestRun);
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      if (latestRun.status === "COMPLETED") {
        queryClient.invalidateQueries({ queryKey: ["runResultsSummary", runId] });
      }
      toast.success(`Run status: ${latestRun.status}`);
    },
    onError: (error) => {
      toast.error(`Failed to refresh run status: ${error.message}`);
    },
  });

  const saveMutation = useMutation({
    mutationFn: () => saveResultsToTable(runId, saveCatalog, saveSchema, saveTable),
    onSuccess: (data) => {
      toast.success(`Results saved to ${data.table}`);
      setSaveDialogOpen(false);
    },
    onError: (error) => {
      toast.error(`Failed to save: ${error.message}`);
    },
  });

  const handleExport = async (format: "csv" | "json") => {
    try {
      const blob = await exportRunResults(runId, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `optimization_results_${runId}.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success(`Results exported as ${format.toUpperCase()}`);
    } catch (error) {
      toast.error(`Export failed: ${error}`);
    }
  };

  if (runLoading) {
    return (
      <div className="p-6 space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!run) {
    return (
      <div className="p-6">
        <p>Run not found</p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate({ to: "/runs" })}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-3">
              {run.run_name || `Run ${run.id.slice(0, 8)}`}
              <StatusBadge status={run.status} />
            </h1>
            <p className="text-muted-foreground">
              Configuration: {config?.name || run.config_id.slice(0, 8)}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => refreshMutation.mutate()}
            disabled={isFetching || refreshMutation.isPending}
          >
            <RefreshCw
              className={`h-4 w-4 mr-2 ${(isFetching || refreshMutation.isPending) ? "animate-spin" : ""}`}
            />
            Refresh
          </Button>
          {run.status === "RUNNING" && (
            <Button
              variant="destructive"
              onClick={() => cancelMutation.mutate()}
              disabled={cancelMutation.isPending}
            >
              <XCircle className="h-4 w-4 mr-2" />
              Cancel
            </Button>
          )}
          {run.status === "COMPLETED" && (
            <>
              <Button variant="outline" onClick={() => handleExport("csv")}>
                <Download className="h-4 w-4 mr-2" />
                Export CSV
              </Button>
              <Dialog open={saveDialogOpen} onOpenChange={setSaveDialogOpen}>
                <DialogTrigger asChild>
                  <Button>
                    <Save className="h-4 w-4 mr-2" />
                    Save to Table
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Save Results to Table</DialogTitle>
                    <DialogDescription>
                      Save the optimization results to a Delta table
                    </DialogDescription>
                  </DialogHeader>
                  <div className="space-y-4 py-4">
                    <div className="space-y-2">
                      <Label>Catalog</Label>
                      <Input value={saveCatalog} onChange={e => setSaveCatalog(e.target.value)} />
                    </div>
                    <div className="space-y-2">
                      <Label>Schema</Label>
                      <Input value={saveSchema} onChange={e => setSaveSchema(e.target.value)} />
                    </div>
                    <div className="space-y-2">
                      <Label>Table Name</Label>
                      <Input value={saveTable} onChange={e => setSaveTable(e.target.value)} />
                    </div>
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setSaveDialogOpen(false)}>Cancel</Button>
                    <Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
                      {saveMutation.isPending ? "Saving..." : "Save"}
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </>
          )}
        </div>
      </div>

      {/* Status Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Status</CardTitle>
            <StatusIcon status={run.status} />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{run.status}</div>
            {run.error_message && (
              <p className="text-xs text-destructive mt-1">{run.error_message}</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Labor Cost</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {(summary?.total_cost ?? run.total_cost) ? `$${(summary?.total_cost ?? run.total_cost)?.toFixed(2)}` : "-"}
            </div>
            {summary?.avg_cost_per_assignment != null && (
              <p className="text-xs text-muted-foreground">
                Avg ${summary.avg_cost_per_assignment.toFixed(2)} per assignment
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Solve Time</CardTitle>
            <Timer className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {(summary?.solve_time_seconds ?? run.solve_time_seconds) ? `${(summary?.solve_time_seconds ?? run.solve_time_seconds)?.toFixed(2)}s` : "-"}
            </div>
            <p className="text-xs text-muted-foreground">GPU-accelerated</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Assignments</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {summary?.num_workers_assigned ?? run.num_workers_assigned ?? 0} / {summary?.num_shifts_covered ?? run.num_shifts_covered ?? 0}
            </div>
            <p className="text-xs text-muted-foreground">
              Workers / Shifts{summary?.total_assignments ? ` (${summary.total_assignments} total)` : ""}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Running Run Animation */}
      {(run.status === "RUNNING" || run.status === "PENDING") && (
        <Card className="border-blue-200 bg-blue-50/50 dark:border-blue-900 dark:bg-blue-950/20">
          <CardContent className="py-8 text-center">
            <Loader2 className="h-12 w-12 mx-auto mb-4 animate-spin text-blue-500" />
            <h3 className="text-lg font-semibold mb-2">
              {run.status === "PENDING" ? "Run Queued" : "Optimization Running"}
            </h3>
            <p className="text-muted-foreground">
              {run.status === "PENDING"
                ? "Waiting for GPU compute resources..."
                : "Solving workforce optimization with NVIDIA cuOpt..."}
            </p>
            {run.databricks_run_id && (
              <p className="text-sm text-muted-foreground mt-2">
                Databricks Run ID: {run.databricks_run_id}
                {databricksRunUrl && (
                  <>
                    {" · "}
                    <a
                      href={databricksRunUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 underline underline-offset-2"
                    >
                      Open in Databricks <ExternalLink className="h-3 w-3" />
                    </a>
                  </>
                )}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Results */}
      {run.status === "COMPLETED" && summary && (
        <Tabs defaultValue="summary" className="space-y-4">
          <TabsList>
            <TabsTrigger value="summary">Summary</TabsTrigger>
            <TabsTrigger value="graph" className="gap-2">
              <Network className="h-4 w-4" />
              Assignment Graph
            </TabsTrigger>
          </TabsList>

          <TabsContent value="summary">
            <Tabs defaultValue="assignments" className="space-y-4">
              <TabsList>
                <TabsTrigger value="assignments">All Assignments</TabsTrigger>
                <TabsTrigger value="by-shift">By Shift</TabsTrigger>
                <TabsTrigger value="by-worker">By Worker</TabsTrigger>
              </TabsList>

              <TabsContent value="assignments">
                <PagedAssignmentsTable runId={runId} />
              </TabsContent>

              <TabsContent value="by-shift">
                <ShiftAggregatesView runId={runId} />
              </TabsContent>

              <TabsContent value="by-worker">
                <WorkerAggregatesView runId={runId} />
              </TabsContent>
            </Tabs>
          </TabsContent>

          <TabsContent value="graph">
            <Suspense fallback={<Skeleton className="h-[600px]" />}>
              <GraphExplorer runId={runId} />
            </Suspense>
          </TabsContent>
        </Tabs>
      )}

      {/* Failed Run */}
      {run.status === "FAILED" && (
        <Card className="border-destructive">
          <CardHeader>
            <CardTitle className="text-destructive flex items-center gap-2">
              <XCircle className="h-5 w-5" />
              {run.error_message?.includes("INFEASIBLE") ? "Infeasible Problem" : "Run Failed"}
            </CardTitle>
            <CardDescription>
              {run.error_message?.includes("INFEASIBLE")
                ? "No feasible solution exists for the current configuration"
                : "The optimization run encountered an error"}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4">
              <pre className="text-sm whitespace-pre-wrap font-mono text-foreground">
                {run.error_message || "An unknown error occurred during optimization."}
              </pre>
            </div>

            {run.error_message?.includes("INFEASIBLE") && (
              <div className="bg-yellow-50 dark:bg-yellow-950/20 border border-yellow-200 dark:border-yellow-900 rounded-lg p-4">
                <h4 className="font-semibold text-yellow-800 dark:text-yellow-400 mb-2">
                  How to Fix This
                </h4>
                <ul className="text-sm space-y-1 text-yellow-900 dark:text-yellow-300 list-disc list-inside">
                  <li>Edit the configuration to adjust constraints (e.g., max shifts per worker)</li>
                  <li>Add more workers or increase worker availability in your data</li>
                  <li>Reduce required workers for some shifts</li>
                </ul>
              </div>
            )}

            <div className="flex gap-2">
              <Button asChild variant="default">
                <Link to="/configs">
                  View Configurations
                </Link>
              </Button>
              <Button asChild variant="outline">
                <Link to="/runs/new" search={{ configId: run.config_id }}>
                  Retry Run
                </Link>
              </Button>
              <Button asChild variant="outline">
                <Link to="/data">
                  Manage Data
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Run Metadata */}
      <Card>
        <CardHeader>
          <CardTitle>Run Details</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <p className="text-muted-foreground">Run ID</p>
              <p className="font-mono">{run.id}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Created</p>
              <p>{new Date(run.created_at).toLocaleString()}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Updated</p>
              <p>{new Date(run.updated_at).toLocaleString()}</p>
            </div>
            {run.completed_at && (
              <div>
                <p className="text-muted-foreground">Completed</p>
                <p>{new Date(run.completed_at).toLocaleString()}</p>
              </div>
            )}
            {run.databricks_run_id && (
              <div>
                <p className="text-muted-foreground">Databricks Run ID</p>
                <p className="font-mono flex items-center gap-2">
                  {run.databricks_run_id}
                  {databricksRunUrl && (
                    <a
                      href={databricksRunUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-sm font-normal underline underline-offset-2"
                    >
                      Open run <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  )}
                </p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ============== Paginated Assignments Table ==============

function PagedAssignmentsTable({ runId }: { runId: string }) {
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<{ field: string; dir: "asc" | "desc" }>({ field: "worker_name", dir: "asc" });

  const { data, isLoading } = useQuery({
    queryKey: ["pagedAssignments", runId, page, sort],
    queryFn: () => getPagedAssignments(runId, {
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
      sort: sort.field,
      sort_dir: sort.dir,
    }),
  });

  const toggleSort = (field: string) => {
    setSort(prev => ({
      field,
      dir: prev.field === field && prev.dir === "asc" ? "desc" : "asc",
    }));
    setPage(0);
  };

  if (isLoading) return <Skeleton className="h-64 w-full" />;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Worker-Shift Assignments</CardTitle>
        <CardDescription>
          {data?.pagination.total ?? 0} total assignments
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>
                <button className="flex items-center gap-1" onClick={() => toggleSort("worker_name")}>
                  Worker <ArrowUpDown className="h-3 w-3" />
                </button>
              </TableHead>
              <TableHead>
                <button className="flex items-center gap-1" onClick={() => toggleSort("shift_name")}>
                  Shift <ArrowUpDown className="h-3 w-3" />
                </button>
              </TableHead>
              <TableHead className="text-right">
                <button className="flex items-center gap-1 ml-auto" onClick={() => toggleSort("cost")}>
                  Labor Cost <ArrowUpDown className="h-3 w-3" />
                </button>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.assignments.map((a, i) => (
              <TableRow key={i}>
                <TableCell className="font-medium">{a.worker_name}</TableCell>
                <TableCell>{a.shift_name}</TableCell>
                <TableCell className="text-right">${a.cost.toFixed(2)}</TableCell>
              </TableRow>
            ))}
            {data?.assignments.length === 0 && (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-muted-foreground py-8">
                  No assignments
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        {data && data.pagination.total > PAGE_SIZE && (
          <PaginationControls
            pagination={data.pagination}
            page={page}
            pageSize={PAGE_SIZE}
            onPageChange={setPage}
          />
        )}
      </CardContent>
    </Card>
  );
}

// ============== Shift Aggregates with Drill-down ==============

function ShiftAggregatesView({ runId }: { runId: string }) {
  const [page, setPage] = useState(0);
  const [expandedShift, setExpandedShift] = useState<string | null>(null);
  const [detailPage, setDetailPage] = useState(0);

  const { data, isLoading } = useQuery({
    queryKey: ["shiftAggregates", runId, page],
    queryFn: () => getShiftAggregates(runId, {
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    }),
  });

  const { data: shiftDetail, isLoading: detailLoading } = useQuery({
    queryKey: ["shiftAssignments", runId, expandedShift, detailPage],
    queryFn: () => getShiftAssignments(runId, expandedShift!, {
      limit: PAGE_SIZE,
      offset: detailPage * PAGE_SIZE,
    }),
    enabled: !!expandedShift,
  });

  if (isLoading) return <Skeleton className="h-64 w-full" />;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Assignments by Shift</CardTitle>
        <CardDescription>
          {data?.pagination.total ?? 0} shifts covered.
          Click a shift to see its assigned workers.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Shift</TableHead>
              <TableHead className="text-right">Workers Assigned</TableHead>
              <TableHead className="text-right">Optimized Cost</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.shifts.map((s) => (
              <>
                <TableRow
                  key={s.shift_name}
                  className="cursor-pointer hover:bg-muted/50"
                  onClick={() => {
                    setExpandedShift(prev => prev === s.shift_name ? null : s.shift_name);
                    setDetailPage(0);
                  }}
                >
                  <TableCell className="font-medium">
                    <span className="flex items-center gap-2">
                      {expandedShift === s.shift_name ? "▼" : "▶"}
                      {s.shift_name}
                    </span>
                  </TableCell>
                  <TableCell className="text-right">
                    <Badge variant="outline">{s.assigned_count}</Badge>
                  </TableCell>
                  <TableCell className="text-right">${s.total_cost.toFixed(2)}</TableCell>
                </TableRow>
                {expandedShift === s.shift_name && (
                  <TableRow key={`${s.shift_name}-detail`}>
                    <TableCell colSpan={3} className="bg-muted/30 p-4">
                      {detailLoading ? (
                        <Skeleton className="h-24 w-full" />
                      ) : shiftDetail && shiftDetail.assignments.length > 0 ? (
                        <div className="space-y-2">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead>Worker</TableHead>
                                <TableHead className="text-right">Cost</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {shiftDetail.assignments.map((a, i) => (
                                <TableRow key={i}>
                                  <TableCell>{a.worker_name}</TableCell>
                                  <TableCell className="text-right">${a.cost.toFixed(2)}</TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                          {shiftDetail.pagination.total > PAGE_SIZE && (
                            <PaginationControls
                              pagination={shiftDetail.pagination}
                              page={detailPage}
                              pageSize={PAGE_SIZE}
                              onPageChange={setDetailPage}
                            />
                          )}
                        </div>
                      ) : (
                        <p className="text-muted-foreground text-sm">No assignments for this shift</p>
                      )}
                    </TableCell>
                  </TableRow>
                )}
              </>
            ))}
            {data?.shifts.length === 0 && (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-muted-foreground py-8">
                  No shifts
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        {data && data.pagination.total > PAGE_SIZE && (
          <PaginationControls
            pagination={data.pagination}
            page={page}
            pageSize={PAGE_SIZE}
            onPageChange={setPage}
          />
        )}
      </CardContent>
    </Card>
  );
}

// ============== Worker Aggregates with Drill-down ==============

function WorkerAggregatesView({ runId }: { runId: string }) {
  const [page, setPage] = useState(0);
  const [expandedWorker, setExpandedWorker] = useState<string | null>(null);
  const [detailPage, setDetailPage] = useState(0);

  const { data, isLoading } = useQuery({
    queryKey: ["workerAggregates", runId, page],
    queryFn: () => getWorkerAggregates(runId, {
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    }),
  });

  const { data: workerDetail, isLoading: detailLoading } = useQuery({
    queryKey: ["workerAssignments", runId, expandedWorker, detailPage],
    queryFn: () => getWorkerAssignments(runId, expandedWorker!, {
      limit: PAGE_SIZE,
      offset: detailPage * PAGE_SIZE,
    }),
    enabled: !!expandedWorker,
  });

  if (isLoading) return <Skeleton className="h-64 w-full" />;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Assignments by Worker</CardTitle>
        <CardDescription>
          {data?.pagination.total ?? 0} workers assigned.
          Click a worker to see their shifts.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Worker</TableHead>
              <TableHead className="text-right">Shifts</TableHead>
              <TableHead className="text-right">Total Labor Cost</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.workers.map((w) => (
              <>
                <TableRow
                  key={w.worker_name}
                  className="cursor-pointer hover:bg-muted/50"
                  onClick={() => {
                    setExpandedWorker(prev => prev === w.worker_name ? null : w.worker_name);
                    setDetailPage(0);
                  }}
                >
                  <TableCell className="font-medium">
                    <span className="flex items-center gap-2">
                      {expandedWorker === w.worker_name ? "▼" : "▶"}
                      {w.worker_name}
                    </span>
                  </TableCell>
                  <TableCell className="text-right">
                    <Badge variant="outline">{w.shift_count}</Badge>
                  </TableCell>
                  <TableCell className="text-right">${w.total_cost.toFixed(2)}</TableCell>
                </TableRow>
                {expandedWorker === w.worker_name && (
                  <TableRow key={`${w.worker_name}-detail`}>
                    <TableCell colSpan={3} className="bg-muted/30 p-4">
                      {detailLoading ? (
                        <Skeleton className="h-24 w-full" />
                      ) : workerDetail && workerDetail.assignments.length > 0 ? (
                        <div className="space-y-2">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead>Shift</TableHead>
                                <TableHead className="text-right">Cost</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {workerDetail.assignments.map((a, i) => (
                                <TableRow key={i}>
                                  <TableCell>{a.shift_name}</TableCell>
                                  <TableCell className="text-right">${a.cost.toFixed(2)}</TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                          {workerDetail.pagination.total > PAGE_SIZE && (
                            <PaginationControls
                              pagination={workerDetail.pagination}
                              page={detailPage}
                              pageSize={PAGE_SIZE}
                              onPageChange={setDetailPage}
                            />
                          )}
                        </div>
                      ) : (
                        <p className="text-muted-foreground text-sm">No assignments for this worker</p>
                      )}
                    </TableCell>
                  </TableRow>
                )}
              </>
            ))}
            {data?.workers.length === 0 && (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-muted-foreground py-8">
                  No workers
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        {data && data.pagination.total > PAGE_SIZE && (
          <PaginationControls
            pagination={data.pagination}
            page={page}
            pageSize={PAGE_SIZE}
            onPageChange={setPage}
          />
        )}
      </CardContent>
    </Card>
  );
}

// ============== Pagination Controls ==============

function PaginationControls({
  pagination,
  page,
  pageSize,
  onPageChange,
}: {
  pagination: { total: number; has_more: boolean };
  page: number;
  pageSize: number;
  onPageChange: (p: number) => void;
}) {
  const totalPages = Math.ceil(pagination.total / pageSize);
  return (
    <div className="flex items-center justify-between pt-4">
      <p className="text-sm text-muted-foreground">
        Showing {page * pageSize + 1}–{Math.min((page + 1) * pageSize, pagination.total)} of {pagination.total}
      </p>
      <div className="flex gap-1">
        <Button
          variant="outline"
          size="sm"
          disabled={page === 0}
          onClick={() => onPageChange(page - 1)}
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="flex items-center px-2 text-sm">
          {page + 1} / {totalPages}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={!pagination.has_more}
          onClick={() => onPageChange(page + 1)}
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

// ============== Status Helpers ==============

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "COMPLETED":
      return <CheckCircle2 className="h-4 w-4 text-green-500" />;
    case "RUNNING":
      return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
    case "FAILED":
      return <XCircle className="h-4 w-4 text-red-500" />;
    case "PENDING":
      return <Clock className="h-4 w-4 text-yellow-500" />;
    default:
      return <Clock className="h-4 w-4 text-muted-foreground" />;
  }
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
    COMPLETED: "default",
    RUNNING: "secondary",
    FAILED: "destructive",
    PENDING: "outline",
    CANCELLED: "outline",
  };

  return <Badge variant={config[status] || "outline"}>{status}</Badge>;
}
