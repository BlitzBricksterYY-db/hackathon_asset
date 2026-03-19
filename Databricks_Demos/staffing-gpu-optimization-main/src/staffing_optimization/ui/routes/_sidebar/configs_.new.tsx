import { createFileRoute, useNavigate, useSearch } from "@tanstack/react-router";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LazySelect, SearchableSelect } from "@/components/ui/searchable-select";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listCatalogs, listSchemas, listTables, getTableColumns, createConfig } from "@/lib/api-client";
import { useState, useEffect, useMemo } from "react";
import { toast } from "sonner";
import { ArrowLeft, Save, Loader2 } from "lucide-react";
import { Separator } from "@/components/ui/separator";

// Default values
const DEFAULT_CATALOG = "demos";
const DEFAULT_SCHEMA = "staffing_optimization";

// Time limit (seconds) by dataset size — based on observed solve times
const DATASET_TIME_LIMITS: Record<string, number> = {
  small: 1,
  medium: 5,
  large: 20,
  enterprise: 60,
};

export const Route = createFileRoute("/_sidebar/configs_/new")({
  component: NewConfig,
  validateSearch: (search: Record<string, unknown>) => ({
    catalog: (search.catalog as string) || undefined,
    schema: (search.schema as string) || undefined,
    workers: (search.workers as string) || undefined,
    shifts: (search.shifts as string) || undefined,
    availability: (search.availability as string) || undefined,
    label: (search.label as string) || undefined,
  }),
});

function NewConfig() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const searchParams = useSearch({ from: "/_sidebar/configs_/new" });

  // Form state — pre-fill from search params (e.g. arriving from "Create Config" on Data page)
  const [name, setName] = useState(
    searchParams.label ? `${searchParams.label.charAt(0).toUpperCase() + searchParams.label.slice(1)} Dataset Config` : ""
  );
  const [description, setDescription] = useState("");
  const [sourceCatalog, setSourceCatalog] = useState(searchParams.catalog || DEFAULT_CATALOG);
  const [sourceSchema, setSourceSchema] = useState(searchParams.schema || DEFAULT_SCHEMA);
  const [workersTable, setWorkersTable] = useState(searchParams.workers || "");
  const [shiftsTable, setShiftsTable] = useState(searchParams.shifts || "");
  const [availabilityTable, setAvailabilityTable] = useState(searchParams.availability || "");
  
  // Column mappings
  const [workerNameCol, setWorkerNameCol] = useState("worker_name");
  const [workerPayCol, setWorkerPayCol] = useState("pay_rate");
  const [shiftNameCol, setShiftNameCol] = useState("shift_name");
  const [shiftRequiredCol, setShiftRequiredCol] = useState("required_workers");
  const [availabilityWorkerCol, setAvailabilityWorkerCol] = useState("worker_name");
  const [availabilityShiftCol, setAvailabilityShiftCol] = useState("shift_name");
  
  // Optimization settings — pre-fill time limit from dataset size when arriving from Data page
  const [maxShiftsPerWorker, setMaxShiftsPerWorker] = useState<string>("");
  const [timeLimitSeconds, setTimeLimitSeconds] = useState(() => {
    const limit = searchParams.label ? DATASET_TIME_LIMITS[searchParams.label] : undefined;
    return limit != null ? String(limit) : "1";
  });
  
  // Target settings
  const [targetCatalog, setTargetCatalog] = useState("");
  const [targetSchema, setTargetSchema] = useState("");
  const [resultsTable, setResultsTable] = useState("");

  // Track if user has requested to browse catalogs/schemas (lazy loading)
  const [catalogsEnabled, setCatalogsEnabled] = useState(false);
  const [schemasEnabled, setSchemasEnabled] = useState(false);

  // Queries - catalogs only load on demand
  const { data: catalogs, isLoading: catalogsLoading } = useQuery({
    queryKey: ["catalogs"],
    queryFn: listCatalogs,
    enabled: catalogsEnabled,
  });

  // Schemas only load on demand
  const { data: schemas, isLoading: schemasLoading } = useQuery({
    queryKey: ["schemas", sourceCatalog],
    queryFn: () => listSchemas(sourceCatalog),
    enabled: schemasEnabled && !!sourceCatalog,
  });

  // Tables load automatically when catalog/schema are set
  const { data: tables, isLoading: tablesLoading } = useQuery({
    queryKey: ["tables", sourceCatalog, sourceSchema],
    queryFn: () => listTables(sourceCatalog, sourceSchema),
    enabled: !!sourceCatalog && !!sourceSchema,
  });

  const { data: workersColumns } = useQuery({
    queryKey: ["columns", sourceCatalog, sourceSchema, workersTable],
    queryFn: () => getTableColumns(sourceCatalog, sourceSchema, workersTable),
    enabled: !!sourceCatalog && !!sourceSchema && !!workersTable,
  });

  const { data: shiftsColumns } = useQuery({
    queryKey: ["columns", sourceCatalog, sourceSchema, shiftsTable],
    queryFn: () => getTableColumns(sourceCatalog, sourceSchema, shiftsTable),
    enabled: !!sourceCatalog && !!sourceSchema && !!shiftsTable,
  });

  const { data: availabilityColumns } = useQuery({
    queryKey: ["columns", sourceCatalog, sourceSchema, availabilityTable],
    queryFn: () => getTableColumns(sourceCatalog, sourceSchema, availabilityTable),
    enabled: !!sourceCatalog && !!sourceSchema && !!availabilityTable,
  });

  // Transform data for SearchableSelect
  const catalogOptions = useMemo(() => 
    catalogs?.map(c => ({ value: c.name, label: c.name, description: c.comment || undefined })) || [],
    [catalogs]
  );

  const schemaOptions = useMemo(() => 
    schemas?.map(s => ({ value: s.name, label: s.name, description: s.comment || undefined })) || [],
    [schemas]
  );

  const tableOptions = useMemo(() => 
    tables?.map(t => ({ value: t.name, label: t.name })) || [],
    [tables]
  );

  // Reset dependent fields when parent changes (but only if user changes them)
  const handleCatalogChange = (value: string) => {
    if (value !== sourceCatalog) {
      setSourceCatalog(value);
      // Only reset schema if it was previously loaded
      if (schemasEnabled) {
        setSourceSchema("");
      }
      setWorkersTable("");
      setShiftsTable("");
      setAvailabilityTable("");
      // Re-enable schema loading for the new catalog
      setSchemasEnabled(false);
    }
  };

  const handleSchemaChange = (value: string) => {
    if (value !== sourceSchema) {
      setSourceSchema(value);
      setWorkersTable("");
      setShiftsTable("");
      setAvailabilityTable("");
    }
  };

  // Mutation
  const createMutation = useMutation({
    mutationFn: createConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["configs"] });
      toast.success("Configuration created successfully");
      navigate({ to: "/configs" });
    },
    onError: (error) => {
      toast.error(`Failed to create configuration: ${error.message}`);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!name || !sourceCatalog || !sourceSchema || !workersTable || !shiftsTable || !availabilityTable) {
      toast.error("Please fill in all required fields");
      return;
    }

    createMutation.mutate({
      name,
      description: description || undefined,
      source_catalog: sourceCatalog,
      source_schema: sourceSchema,
      workers_table: workersTable,
      shifts_table: shiftsTable,
      availability_table: availabilityTable,
      worker_name_col: workerNameCol,
      worker_pay_col: workerPayCol,
      shift_name_col: shiftNameCol,
      shift_required_col: shiftRequiredCol,
      availability_worker_col: availabilityWorkerCol,
      availability_shift_col: availabilityShiftCol,
      max_shifts_per_worker: maxShiftsPerWorker ? parseInt(maxShiftsPerWorker) : undefined,
      time_limit_seconds: parseFloat(timeLimitSeconds),
      target_catalog: targetCatalog || undefined,
      target_schema: targetSchema || undefined,
      results_table: resultsTable || undefined,
    });
  };

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={() => navigate({ to: "/configs" })}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="text-3xl font-bold">New Configuration</h1>
          <p className="text-muted-foreground">
            Set up a new workforce optimization configuration
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Basic Info */}
        <Card>
          <CardHeader>
            <CardTitle>Basic Information</CardTitle>
            <CardDescription>Name and describe your configuration</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">Name *</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g., Weekly Staff Schedule"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Describe this optimization configuration..."
                rows={2}
              />
            </div>
          </CardContent>
        </Card>

        {/* Source Data */}
        <Card>
          <CardHeader>
            <CardTitle>Source Data</CardTitle>
            <CardDescription>Select the Unity Catalog tables containing your workforce data</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Catalog *</Label>
                <LazySelect
                  value={sourceCatalog}
                  onValueChange={handleCatalogChange}
                  options={catalogOptions}
                  isLoading={catalogsLoading}
                  onBrowse={() => setCatalogsEnabled(true)}
                  placeholder="Enter catalog name..."
                  searchPlaceholder="Search catalogs..."
                  emptyText="No catalogs found"
                />
              </div>
              <div className="space-y-2">
                <Label>Schema *</Label>
                <LazySelect
                  value={sourceSchema}
                  onValueChange={handleSchemaChange}
                  options={schemaOptions}
                  isLoading={schemasLoading}
                  onBrowse={() => setSchemasEnabled(true)}
                  placeholder="Enter schema name..."
                  searchPlaceholder="Search schemas..."
                  emptyText="No schemas found"
                  disabled={!sourceCatalog}
                />
              </div>
            </div>

            <Separator />

            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label>Workers Table *</Label>
                <SearchableSelect
                  options={tableOptions}
                  value={workersTable}
                  onValueChange={setWorkersTable}
                  placeholder="Select table..."
                  searchPlaceholder="Search tables..."
                  emptyText="No tables found"
                  disabled={!sourceSchema}
                  isLoading={tablesLoading}
                />
              </div>
              <div className="space-y-2">
                <Label>Shifts Table *</Label>
                <SearchableSelect
                  options={tableOptions}
                  value={shiftsTable}
                  onValueChange={setShiftsTable}
                  placeholder="Select table..."
                  searchPlaceholder="Search tables..."
                  emptyText="No tables found"
                  disabled={!sourceSchema}
                  isLoading={tablesLoading}
                />
              </div>
              <div className="space-y-2">
                <Label>Availability Table *</Label>
                <SearchableSelect
                  options={tableOptions}
                  value={availabilityTable}
                  onValueChange={setAvailabilityTable}
                  placeholder="Select table..."
                  searchPlaceholder="Search tables..."
                  emptyText="No tables found"
                  disabled={!sourceSchema}
                  isLoading={tablesLoading}
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Column Mappings */}
        <Card>
          <CardHeader>
            <CardTitle>Column Mappings</CardTitle>
            <CardDescription>Map your table columns to the optimization fields</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Workers columns */}
            <div>
              <h4 className="font-medium mb-3">Workers Table Columns</h4>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Worker Name Column</Label>
                  <Select value={workerNameCol} onValueChange={setWorkerNameCol}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {workersColumns?.columns.map(c => (
                        <SelectItem key={c.name} value={c.name}>{c.name}</SelectItem>
                      ))}
                      {!workersColumns && (
                        <SelectItem value="worker_name">worker_name (default)</SelectItem>
                      )}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Pay Rate Column</Label>
                  <Select value={workerPayCol} onValueChange={setWorkerPayCol}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {workersColumns?.columns.map(c => (
                        <SelectItem key={c.name} value={c.name}>{c.name}</SelectItem>
                      ))}
                      {!workersColumns && (
                        <SelectItem value="pay_rate">pay_rate (default)</SelectItem>
                      )}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>

            <Separator />

            {/* Shifts columns */}
            <div>
              <h4 className="font-medium mb-3">Shifts Table Columns</h4>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Shift Name Column</Label>
                  <Select value={shiftNameCol} onValueChange={setShiftNameCol}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {shiftsColumns?.columns.map(c => (
                        <SelectItem key={c.name} value={c.name}>{c.name}</SelectItem>
                      ))}
                      {!shiftsColumns && (
                        <SelectItem value="shift_name">shift_name (default)</SelectItem>
                      )}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Required Workers Column</Label>
                  <Select value={shiftRequiredCol} onValueChange={setShiftRequiredCol}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {shiftsColumns?.columns.map(c => (
                        <SelectItem key={c.name} value={c.name}>{c.name}</SelectItem>
                      ))}
                      {!shiftsColumns && (
                        <SelectItem value="required_workers">required_workers (default)</SelectItem>
                      )}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>

            <Separator />

            {/* Availability columns */}
            <div>
              <h4 className="font-medium mb-3">Availability Table Columns</h4>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Worker Column</Label>
                  <Select value={availabilityWorkerCol} onValueChange={setAvailabilityWorkerCol}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {availabilityColumns?.columns.map(c => (
                        <SelectItem key={c.name} value={c.name}>{c.name}</SelectItem>
                      ))}
                      {!availabilityColumns && (
                        <SelectItem value="worker_name">worker_name (default)</SelectItem>
                      )}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Shift Column</Label>
                  <Select value={availabilityShiftCol} onValueChange={setAvailabilityShiftCol}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {availabilityColumns?.columns.map(c => (
                        <SelectItem key={c.name} value={c.name}>{c.name}</SelectItem>
                      ))}
                      {!availabilityColumns && (
                        <SelectItem value="shift_name">shift_name (default)</SelectItem>
                      )}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Optimization Settings */}
        <Card>
          <CardHeader>
            <CardTitle>Optimization Settings</CardTitle>
            <CardDescription>Configure solver parameters</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="maxShifts">Max Shifts per Worker (optional)</Label>
                <Input
                  id="maxShifts"
                  type="number"
                  value={maxShiftsPerWorker}
                  onChange={(e) => setMaxShiftsPerWorker(e.target.value)}
                  placeholder="Leave empty for no limit"
                  min={1}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="timeLimit">Time Limit (seconds)</Label>
                <Input
                  id="timeLimit"
                  type="number"
                  value={timeLimitSeconds}
                  onChange={(e) => setTimeLimitSeconds(e.target.value)}
                  min={1}
                  max={3600}
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Target Table (Optional) */}
        <Card>
          <CardHeader>
            <CardTitle>Results Storage (Optional)</CardTitle>
            <CardDescription>Optionally save results to a Delta table</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label>Target Catalog</Label>
                <LazySelect
                  value={targetCatalog}
                  onValueChange={setTargetCatalog}
                  options={catalogOptions}
                  isLoading={catalogsLoading}
                  onBrowse={() => setCatalogsEnabled(true)}
                  placeholder="Enter catalog..."
                  searchPlaceholder="Search catalogs..."
                  emptyText="No catalogs found"
                />
              </div>
              <div className="space-y-2">
                <Label>Target Schema</Label>
                <LazySelect
                  value={targetSchema}
                  onValueChange={setTargetSchema}
                  options={schemaOptions}
                  isLoading={schemasLoading}
                  onBrowse={() => setSchemasEnabled(true)}
                  placeholder="Enter schema..."
                  searchPlaceholder="Search schemas..."
                  emptyText="No schemas found"
                  disabled={!targetCatalog && !sourceCatalog}
                />
              </div>
              <div className="space-y-2">
                <Label>Results Table Name</Label>
                <Input
                  value={resultsTable}
                  onChange={(e) => setResultsTable(e.target.value)}
                  placeholder="e.g., workforce_results"
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Submit */}
        <div className="flex justify-end gap-4">
          <Button type="button" variant="outline" onClick={() => navigate({ to: "/configs" })}>
            Cancel
          </Button>
          <Button type="submit" disabled={createMutation.isPending}>
            {createMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Creating...
              </>
            ) : (
              <>
                <Save className="h-4 w-4 mr-2" />
                Create Configuration
              </>
            )}
          </Button>
        </div>
      </form>
    </div>
  );
}
