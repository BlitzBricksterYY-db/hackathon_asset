import { createFileRoute, Link } from "@tanstack/react-router";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LazySelect } from "@/components/ui/searchable-select";
import { useQuery, useMutation } from "@tanstack/react-query";
import { listCatalogs, listSchemas, generateSampleData } from "@/lib/api-client";
import { useState, useMemo } from "react";
import { toast } from "sonner";
import { Database, Users, Calendar, Loader2, CheckCircle2, Plus } from "lucide-react";
import { Separator } from "@/components/ui/separator";

// Default values
const DEFAULT_CATALOG = "demos";
const DEFAULT_SCHEMA = "staffing_optimization";

export const Route = createFileRoute("/_sidebar/data")({
  component: DataManagement,
});

// Dataset size presets
const DATASET_SIZES = {
  small: {
    label: "Small",
    description: "Quick demo (50 workers, 42 shifts, ~1.3k vars)",
    num_workers: 50,
    num_shifts: 42,
  },
  medium: {
    label: "Medium",
    description: "Department scale (200 workers, 150 shifts, ~18k vars)",
    num_workers: 200,
    num_shifts: 150,
  },
  large: {
    label: "Large",
    description: "Facility scale (1,000 workers, 500 shifts, ~300k vars)",
    num_workers: 1000,
    num_shifts: 500,
  },
  enterprise: {
    label: "Enterprise",
    description: "Multi-site stress test (5,000 workers, 1,000 shifts, ~3M vars)",
    num_workers: 5000,
    num_shifts: 1000,
  },
};

type DatasetSize = keyof typeof DATASET_SIZES;

function DataManagement() {
  // Form state with defaults
  const [catalog, setCatalog] = useState(DEFAULT_CATALOG);
  const [schema, setSchema] = useState(DEFAULT_SCHEMA);
  const [datasetSize, setDatasetSize] = useState<DatasetSize>("small");
  const [numWorkers, setNumWorkers] = useState("50");
  const [numShifts, setNumShifts] = useState("42");
  const [minPay, setMinPay] = useState("8");
  const [maxPay, setMaxPay] = useState("15");
  const [avgAvailability, setAvgAvailability] = useState("0.6");
  
  // Update worker/shift counts when dataset size changes
  const handleDatasetSizeChange = (size: DatasetSize) => {
    setDatasetSize(size);
    const preset = DATASET_SIZES[size];
    setNumWorkers(preset.num_workers.toString());
    setNumShifts(preset.num_shifts.toString());
  };

  // Track if user has requested to browse catalogs/schemas (lazy loading)
  const [catalogsEnabled, setCatalogsEnabled] = useState(false);
  const [schemasEnabled, setSchemasEnabled] = useState(false);

  const { data: catalogs, isLoading: catalogsLoading } = useQuery({
    queryKey: ["catalogs"],
    queryFn: listCatalogs,
    enabled: catalogsEnabled,
  });

  const { data: schemas, isLoading: schemasLoading } = useQuery({
    queryKey: ["schemas", catalog],
    queryFn: () => listSchemas(catalog),
    enabled: schemasEnabled && !!catalog,
  });

  const catalogOptions = useMemo(() => 
    catalogs?.map(c => ({ value: c.name, label: c.name, description: c.comment || undefined })) || [],
    [catalogs]
  );

  const schemaOptions = useMemo(() => 
    schemas?.map(s => ({ value: s.name, label: s.name, description: s.comment || undefined })) || [],
    [schemas]
  );

  const handleCatalogChange = (value: string) => {
    if (value !== catalog) {
      setCatalog(value);
      if (schemasEnabled) {
        setSchema("");
      }
      setSchemasEnabled(false);
    }
  };

  const generateMutation = useMutation({
    mutationFn: generateSampleData,
    onSuccess: (data) => {
      toast.success(
        `Sample data generated successfully! Created ${data.num_workers} workers, ${data.num_shifts} shifts, and ${data.num_availability_records} availability records.`
      );
    },
    onError: (error) => {
      toast.error(`Failed to generate sample data: ${error.message}`);
    },
  });

  const handleGenerate = (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!catalog) {
      toast.error("Please enter a catalog name");
      return;
    }
    if (!schema) {
      toast.error("Please enter a schema name");
      return;
    }

    generateMutation.mutate({
      catalog,
      schema: schema,
      num_workers: parseInt(numWorkers),
      num_shifts: parseInt(numShifts),
      min_pay: parseFloat(minPay),
      max_pay: parseFloat(maxPay),
      avg_availability_pct: parseFloat(avgAvailability),
      dataset_label: datasetSize,
    });
  };

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      <div>
        <h1 className="text-3xl font-bold">Data Management</h1>
        <p className="text-muted-foreground">
          Generate sample data or manage your workforce data tables
        </p>
      </div>

      {/* Generate Sample Data */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Database className="h-5 w-5" />
            Generate Sample Data
          </CardTitle>
          <CardDescription>
            Create sample workforce data tables to test the optimization
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleGenerate} className="space-y-6">
            {/* Target Location */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Target Catalog *</Label>
                <LazySelect
                  value={catalog}
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
                <Label>Target Schema *</Label>
                <LazySelect
                  value={schema}
                  onValueChange={setSchema}
                  options={schemaOptions}
                  isLoading={schemasLoading}
                  onBrowse={() => setSchemasEnabled(true)}
                  placeholder="Enter schema name..."
                  searchPlaceholder="Search schemas..."
                  emptyText="No schemas found"
                  disabled={!catalog}
                />
                <p className="text-xs text-muted-foreground">
                  Schema will be created if it doesn't exist
                </p>
              </div>
            </div>

            <Separator />

            {/* Dataset Size Selector */}
            <div className="space-y-3">
              <Label>Dataset Size</Label>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {(Object.entries(DATASET_SIZES) as [DatasetSize, typeof DATASET_SIZES[DatasetSize]][]).map(([key, preset]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => handleDatasetSizeChange(key)}
                    className={`p-4 border-2 rounded-lg text-left transition-colors ${
                      datasetSize === key
                        ? "border-primary bg-primary/5"
                        : "border-border hover:border-primary/50"
                    }`}
                  >
                    <div className="font-semibold mb-1">{preset.label}</div>
                    <div className="text-xs text-muted-foreground">{preset.description}</div>
                  </button>
                ))}
              </div>
            </div>

            <Separator />

            {/* Data Parameters */}
            <div>
              <h4 className="font-medium mb-4">Data Parameters</h4>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="space-y-2">
                  <Label>Number of Workers</Label>
                  <Input
                    type="number"
                    value={numWorkers}
                    onChange={(e) => setNumWorkers(e.target.value)}
                    min={1}
                    max={10000}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Number of Shifts</Label>
                  <Input
                    type="number"
                    value={numShifts}
                    onChange={(e) => setNumShifts(e.target.value)}
                    min={1}
                    max={5000}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Min Pay Rate ($)</Label>
                  <Input
                    type="number"
                    value={minPay}
                    onChange={(e) => setMinPay(e.target.value)}
                    min={1}
                    step={0.5}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Max Pay Rate ($)</Label>
                  <Input
                    type="number"
                    value={maxPay}
                    onChange={(e) => setMaxPay(e.target.value)}
                    min={1}
                    step={0.5}
                  />
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Average Availability (0-1)</Label>
              <Input
                type="number"
                value={avgAvailability}
                onChange={(e) => setAvgAvailability(e.target.value)}
                min={0.1}
                max={1}
                step={0.1}
                className="w-32"
              />
              <p className="text-xs text-muted-foreground">
                Average percentage of shifts each worker is available for
              </p>
            </div>

            <Button type="submit" disabled={generateMutation.isPending} className="w-full">
              {generateMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <Database className="h-4 w-4 mr-2" />
                  Generate Sample Data
                </>
              )}
            </Button>
          </form>

          {/* Success Result */}
          {generateMutation.isSuccess && generateMutation.data && (() => {
            const d = generateMutation.data;
            const workersPart = d.workers_table.split(".").pop() ?? "";
            const shiftsPart = d.shifts_table.split(".").pop() ?? "";
            const availPart  = d.availability_table.split(".").pop() ?? "";

            return (
              <div className="mt-6 p-4 border rounded-lg bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-900">
                <div className="flex items-center gap-2 mb-4">
                  <CheckCircle2 className="h-5 w-5 text-green-500" />
                  <h4 className="font-semibold text-green-700 dark:text-green-400">
                    {d.dataset_label
                      ? `${d.dataset_label.charAt(0).toUpperCase() + d.dataset_label.slice(1)} Dataset Generated!`
                      : "Sample Data Generated!"}
                  </h4>
                </div>
                <div className="space-y-2 text-sm">
                  <p><strong>Workers Table:</strong> <code className="bg-muted px-1.5 py-0.5 rounded text-xs">{d.workers_table}</code></p>
                  <p><strong>Shifts Table:</strong> <code className="bg-muted px-1.5 py-0.5 rounded text-xs">{d.shifts_table}</code></p>
                  <p><strong>Availability Table:</strong> <code className="bg-muted px-1.5 py-0.5 rounded text-xs">{d.availability_table}</code></p>
                  <p className="text-muted-foreground mt-1">
                    {d.num_workers} workers / {d.num_shifts} shifts / {d.num_availability_records} availability records
                  </p>
                </div>
                <div className="mt-4 flex gap-2">
                  <Button size="sm" asChild>
                    <Link
                      to="/configs/new"
                      search={{
                        catalog,
                        schema,
                        workers: workersPart,
                        shifts: shiftsPart,
                        availability: availPart,
                        label: d.dataset_label ?? undefined,
                      }}
                    >
                      <Plus className="h-4 w-4 mr-2" />
                      Create Configuration with These Tables
                    </Link>
                  </Button>
                </div>
              </div>
            );
          })()}
        </CardContent>
      </Card>

      {/* Info Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Users className="h-5 w-5" />
              Workers Table
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            <p className="mb-2">Contains worker information:</p>
            <ul className="list-disc list-inside space-y-1">
              <li><code>worker_name</code> - Worker identifier</li>
              <li><code>pay_rate</code> - Hourly/shift pay rate</li>
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Calendar className="h-5 w-5" />
              Shifts Table
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            <p className="mb-2">Contains shift requirements:</p>
            <ul className="list-disc list-inside space-y-1">
              <li><code>shift_name</code> - Shift identifier</li>
              <li><code>required_workers</code> - Workers needed</li>
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Database className="h-5 w-5" />
              Availability Table
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            <p className="mb-2">Maps worker availability:</p>
            <ul className="list-disc list-inside space-y-1">
              <li><code>worker_name</code> - Worker identifier</li>
              <li><code>shift_name</code> - Available shift</li>
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
