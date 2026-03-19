import { createFileRoute, Link } from "@tanstack/react-router";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useQuery } from "@tanstack/react-query";
import { listConfigs, listRuns } from "@/lib/api-client";
import { 
  Plus, 
  PlayCircle, 
  Settings, 
  Clock, 
  CheckCircle2, 
  XCircle, 
  Loader2,
  TrendingUp,
  Users,
  Calendar
} from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

export const Route = createFileRoute("/_sidebar/dashboard")({
  component: Dashboard,
});

function Dashboard() {
  const { data: configs, isLoading: configsLoading } = useQuery({
    queryKey: ["configs"],
    queryFn: listConfigs,
  });

  const { data: runs, isLoading: runsLoading } = useQuery({
    queryKey: ["runs"],
    queryFn: () => listRuns(),
  });

  const recentRuns = runs?.slice(0, 5) || [];
  const runningRuns = runs?.filter(r => r.status === "RUNNING").length || 0;
  const completedRuns = runs?.filter(r => r.status === "COMPLETED").length || 0;
  const totalCostSaved = runs
    ?.filter(r => r.status === "COMPLETED" && r.total_cost)
    .reduce((acc, r) => acc + (r.total_cost || 0), 0) || 0;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold">Dashboard</h1>
          <p className="text-muted-foreground">
            Workforce optimization powered by NVIDIA cuOpt
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline">
            <Link to="/configs/new">
              <Plus className="h-4 w-4 mr-2" />
              New Configuration
            </Link>
          </Button>
          <Button asChild>
            <Link to="/runs/new">
              <PlayCircle className="h-4 w-4 mr-2" />
              Run Optimization
            </Link>
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Configurations</CardTitle>
            <Settings className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {configsLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-2xl font-bold">{configs?.length || 0}</div>
            )}
            <p className="text-xs text-muted-foreground">
              Saved optimization configs
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Running</CardTitle>
            <Loader2 className={`h-4 w-4 text-muted-foreground ${runningRuns > 0 ? "animate-spin" : ""}`} />
          </CardHeader>
          <CardContent>
            {runsLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-2xl font-bold">{runningRuns}</div>
            )}
            <p className="text-xs text-muted-foreground">
              Currently processing
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Completed</CardTitle>
            <CheckCircle2 className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            {runsLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-2xl font-bold">{completedRuns}</div>
            )}
            <p className="text-xs text-muted-foreground">
              Successful optimizations
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Optimized Cost</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {runsLoading ? (
              <Skeleton className="h-8 w-24" />
            ) : (
              <div className="text-2xl font-bold">${totalCostSaved.toFixed(2)}</div>
            )}
            <p className="text-xs text-muted-foreground">
              Total optimized labor cost
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Recent Runs */}
      <Card>
        <CardHeader>
          <div className="flex justify-between items-center">
            <div>
              <CardTitle>Recent Runs</CardTitle>
              <CardDescription>Latest optimization runs</CardDescription>
            </div>
            <Button variant="outline" size="sm" asChild>
              <Link to="/runs">View All</Link>
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {runsLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map(i => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : recentRuns.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <PlayCircle className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>No optimization runs yet</p>
              <Button className="mt-4" asChild>
                <Link to="/runs/new">Run Your First Optimization</Link>
              </Button>
            </div>
          ) : (
            <div className="space-y-2">
              {recentRuns.map(run => (
                <Link
                  key={run.id}
                  to="/runs/$runId"
                  params={{ runId: run.id }}
                  className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <StatusIcon status={run.status} />
                    <div>
                      <p className="font-medium">{run.run_name || `Run ${run.id.slice(0, 8)}`}</p>
                      <p className="text-sm text-muted-foreground">
                        {new Date(run.created_at).toLocaleString()}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    {run.total_cost && (
                      <span className="text-sm font-medium">${run.total_cost.toFixed(2)}</span>
                    )}
                    <StatusBadge status={run.status} />
                  </div>
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Quick Actions */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="hover:border-primary transition-colors cursor-pointer" onClick={() => {}}>
          <Link to="/configs/new">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Settings className="h-5 w-5" />
                Create Configuration
              </CardTitle>
              <CardDescription>
                Set up a new optimization configuration with your data sources
              </CardDescription>
            </CardHeader>
          </Link>
        </Card>

        <Card className="hover:border-primary transition-colors cursor-pointer">
          <Link to="/data">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5" />
                Generate Sample Data
              </CardTitle>
              <CardDescription>
                Create sample workforce data to test the optimization
              </CardDescription>
            </CardHeader>
          </Link>
        </Card>

        <Card className="hover:border-primary transition-colors cursor-pointer">
          <Link to="/runs">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Calendar className="h-5 w-5" />
                View All Runs
              </CardTitle>
              <CardDescription>
                Monitor and manage your optimization runs
              </CardDescription>
            </CardHeader>
          </Link>
        </Card>
      </div>
    </div>
  );
}

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "COMPLETED":
      return <CheckCircle2 className="h-5 w-5 text-green-500" />;
    case "RUNNING":
      return <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />;
    case "FAILED":
      return <XCircle className="h-5 w-5 text-red-500" />;
    case "PENDING":
      return <Clock className="h-5 w-5 text-yellow-500" />;
    default:
      return <Clock className="h-5 w-5 text-muted-foreground" />;
  }
}

function StatusBadge({ status }: { status: string }) {
  const variants: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
    COMPLETED: "default",
    RUNNING: "secondary",
    FAILED: "destructive",
    PENDING: "outline",
    CANCELLED: "outline",
  };

  return (
    <Badge variant={variants[status] || "outline"}>
      {status}
    </Badge>
  );
}
