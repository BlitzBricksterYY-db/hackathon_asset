import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listRuns, listConfigs, cancelRun } from "@/lib/api-client";
import { Plus, XCircle, CheckCircle2, Clock, Loader2, RefreshCw } from "lucide-react";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useState } from "react";
import { toast } from "sonner";

export const Route = createFileRoute("/_sidebar/runs")({
  component: RunsList,
});

function RunsList() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [configFilter, setConfigFilter] = useState<string>("all");

  const { data: runs, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["runs", configFilter === "all" ? undefined : configFilter],
    queryFn: () => listRuns(configFilter === "all" ? undefined : configFilter),
    refetchInterval: (query) => {
      const runList = query.state.data ?? [];
      const hasActiveRuns = runList.some(
        (run) => run.status === "RUNNING" || run.status === "PENDING"
      );
      return hasActiveRuns ? 5000 : false;
    },
  });

  const { data: configs } = useQuery({
    queryKey: ["configs"],
    queryFn: listConfigs,
  });

  const cancelMutation = useMutation({
    mutationFn: cancelRun,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      toast.success("Run cancelled");
    },
    onError: (error) => {
      toast.error(`Failed to cancel run: ${error.message}`);
    },
  });

  const configsMap = new Map(configs?.map(c => [c.id, c.name]) || []);

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold">Optimization Runs</h1>
          <p className="text-muted-foreground">
            View and manage your optimization runs
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isFetching ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <Button asChild>
            <Link to="/runs/new">
              <Plus className="h-4 w-4 mr-2" />
              New Run
            </Link>
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <div className="flex justify-between items-center">
            <div>
              <CardTitle>Run History</CardTitle>
              <CardDescription>All optimization runs</CardDescription>
            </div>
            <Select value={configFilter} onValueChange={setConfigFilter}>
              <SelectTrigger className="w-64">
                <SelectValue placeholder="Filter by configuration" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Configurations</SelectItem>
                {configs?.map(c => (
                  <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">
              {[1, 2, 3, 4, 5].map(i => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : runs?.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Clock className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p className="mb-4">No runs yet</p>
              <Button asChild>
                <Link to="/runs/new">Run Your First Optimization</Link>
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Status</TableHead>
                  <TableHead>Run Name</TableHead>
                  <TableHead>Configuration</TableHead>
                  <TableHead>Optimized Cost</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs?.map(run => (
                  <TableRow
                    key={run.id}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => navigate({ to: "/runs/$runId", params: { runId: run.id } })}
                  >
                    <TableCell>
                      <StatusBadge status={run.status} />
                    </TableCell>
                    <TableCell>
                      <div className="font-medium">
                        {run.run_name || `Run ${run.id.slice(0, 8)}`}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        ID: {run.id.slice(0, 8)}...
                      </div>
                    </TableCell>
                    <TableCell>
                      {configsMap.get(run.config_id) || run.config_id.slice(0, 8)}
                    </TableCell>
                    <TableCell>
                      {run.total_cost ? `$${run.total_cost.toFixed(2)}` : '-'}
                    </TableCell>
                    <TableCell>
                      {run.solve_time_seconds 
                        ? `${run.solve_time_seconds.toFixed(2)}s` 
                        : run.status === 'RUNNING' 
                          ? <Loader2 className="h-4 w-4 animate-spin" />
                          : '-'
                      }
                    </TableCell>
                    <TableCell>
                      {new Date(run.created_at).toLocaleString()}
                    </TableCell>
                    <TableCell className="text-right">
                      {run.status === 'RUNNING' && (
                        <Button 
                          variant="outline" 
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            cancelMutation.mutate(run.id);
                          }}
                          disabled={cancelMutation.isPending}
                        >
                          <XCircle className="h-4 w-4 text-destructive" />
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { variant: "default" | "secondary" | "destructive" | "outline", icon: React.ReactNode }> = {
    COMPLETED: { variant: "default", icon: <CheckCircle2 className="h-3 w-3 mr-1" /> },
    RUNNING: { variant: "secondary", icon: <Loader2 className="h-3 w-3 mr-1 animate-spin" /> },
    FAILED: { variant: "destructive", icon: <XCircle className="h-3 w-3 mr-1" /> },
    PENDING: { variant: "outline", icon: <Clock className="h-3 w-3 mr-1" /> },
    CANCELLED: { variant: "outline", icon: <XCircle className="h-3 w-3 mr-1" /> },
  };

  const { variant, icon } = config[status] || { variant: "outline" as const, icon: null };

  return (
    <Badge variant={variant} className="flex items-center w-fit">
      {icon}
      {status}
    </Badge>
  );
}
