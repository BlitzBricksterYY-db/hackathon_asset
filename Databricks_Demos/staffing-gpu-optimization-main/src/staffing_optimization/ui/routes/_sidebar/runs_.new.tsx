import { createFileRoute, useNavigate, useSearch } from "@tanstack/react-router";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listConfigs, createRun } from "@/lib/api-client";
import { useState, useEffect } from "react";
import { toast } from "sonner";
import { ArrowLeft, PlayCircle, Loader2, Info } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export const Route = createFileRoute("/_sidebar/runs_/new")({
  component: NewRun,
  validateSearch: (search: Record<string, unknown>) => ({
    configId: (search.configId as string) || undefined,
  }),
});

function NewRun() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { configId: initialConfigId } = useSearch({ from: "/_sidebar/runs_/new" });

  const [configId, setConfigId] = useState(initialConfigId || "");
  const [runName, setRunName] = useState("");

  const { data: configs, isLoading: configsLoading } = useQuery({
    queryKey: ["configs"],
    queryFn: listConfigs,
  });

  // Set config from URL param
  useEffect(() => {
    if (initialConfigId) {
      setConfigId(initialConfigId);
    }
  }, [initialConfigId]);

  const selectedConfig = configs?.find(c => c.id === configId);

  const createMutation = useMutation({
    mutationFn: createRun,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      toast.success("Run submitted successfully!");
      navigate({ to: "/runs/$runId", params: { runId: data.id } });
    },
    onError: (error) => {
      toast.error(`Failed to submit run: ${error.message}`);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!configId) {
      toast.error("Please select a configuration");
      return;
    }

    createMutation.mutate({
      config_id: configId,
      run_name: runName || undefined,
    });
  };

  return (
    <div className="p-6 space-y-6 max-w-2xl">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={() => navigate({ to: "/runs" })}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="text-3xl font-bold">Run Optimization</h1>
          <p className="text-muted-foreground">
            Submit a new workforce optimization run
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Run Configuration</CardTitle>
            <CardDescription>
              Select a configuration and optionally name this run
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>Configuration *</Label>
              <Select value={configId} onValueChange={setConfigId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a configuration" />
                </SelectTrigger>
                <SelectContent>
                  {configs?.map(c => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {configsLoading && (
                <p className="text-sm text-muted-foreground">Loading configurations...</p>
              )}
              {!configsLoading && configs?.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  No configurations available.{" "}
                  <Button variant="link" className="p-0 h-auto" asChild>
                    <a href="/configs/new">Create one first</a>
                  </Button>
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="runName">Run Name (optional)</Label>
              <Input
                id="runName"
                value={runName}
                onChange={(e) => setRunName(e.target.value)}
                placeholder="e.g., Week of Jan 28"
              />
              <p className="text-xs text-muted-foreground">
                A friendly name to identify this optimization run
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Selected Config Details */}
        {selectedConfig && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Info className="h-4 w-4" />
                Configuration Details
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-muted-foreground">Source</p>
                  <p className="font-medium">
                    {selectedConfig.source_catalog}.{selectedConfig.source_schema}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground">Time Limit</p>
                  <p className="font-medium">{selectedConfig.time_limit_seconds}s</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Workers Table</p>
                  <Badge variant="outline">{selectedConfig.workers_table}</Badge>
                </div>
                <div>
                  <p className="text-muted-foreground">Shifts Table</p>
                  <Badge variant="outline">{selectedConfig.shifts_table}</Badge>
                </div>
                <div>
                  <p className="text-muted-foreground">Availability Table</p>
                  <Badge variant="outline">{selectedConfig.availability_table}</Badge>
                </div>
                <div>
                  <p className="text-muted-foreground">Max Shifts/Worker</p>
                  <p className="font-medium">
                    {selectedConfig.max_shifts_per_worker || "No limit"}
                  </p>
                </div>
              </div>
              {selectedConfig.databricks_job_id && (
                <div className="pt-2 border-t">
                  <p className="text-xs text-muted-foreground">
                    Databricks Job ID: {selectedConfig.databricks_job_id}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* GPU Info */}
        <Card className="border-blue-200 bg-blue-50/50 dark:border-blue-900 dark:bg-blue-950/20">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <span className="text-2xl">🚀</span>
              GPU-Accelerated Optimization
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              This run will execute on Databricks Serverless GPU compute using NVIDIA cuOpt 
              for high-performance optimization. Typical solve times are under 1 minute 
              for problems with hundreds of workers and shifts.
            </p>
          </CardContent>
        </Card>

        {/* Submit */}
        <div className="flex justify-end gap-4">
          <Button type="button" variant="outline" onClick={() => navigate({ to: "/runs" })}>
            Cancel
          </Button>
          <Button 
            type="submit" 
            disabled={createMutation.isPending || !configId}
          >
            {createMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Submitting...
              </>
            ) : (
              <>
                <PlayCircle className="h-4 w-4 mr-2" />
                Run Optimization
              </>
            )}
          </Button>
        </div>
      </form>
    </div>
  );
}
