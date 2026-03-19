import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Search, RotateCcw, User, Calendar } from "lucide-react";
import type { FilterState, GraphStats } from "@/lib/graph-utils";
import { defaultFilterState } from "@/lib/graph-utils";

export interface FiltersPanelProps {
  filters: FilterState;
  onFiltersChange: (filters: FilterState) => void;
  stats: GraphStats;
  className?: string;
}

export function FiltersPanel({
  filters,
  onFiltersChange,
  stats,
  className,
}: FiltersPanelProps) {
  const handleSearchChange = (value: string) => {
    onFiltersChange({ ...filters, search: value });
  };

  const handleCostMinChange = (value: string) => {
    const num = parseFloat(value) || 0;
    onFiltersChange({
      ...filters,
      costRange: [num, filters.costRange[1]],
    });
  };

  const handleCostMaxChange = (value: string) => {
    const num = parseFloat(value);
    const maxVal = isNaN(num) ? Infinity : num;
    onFiltersChange({
      ...filters,
      costRange: [filters.costRange[0], maxVal],
    });
  };

  const toggleWorkers = () => {
    onFiltersChange({ ...filters, showWorkers: !filters.showWorkers });
  };

  const toggleShifts = () => {
    onFiltersChange({ ...filters, showShifts: !filters.showShifts });
  };

  const handleReset = () => {
    onFiltersChange(defaultFilterState);
  };

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">Filters</CardTitle>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleReset}
            className="h-7 px-2 text-xs"
          >
            <RotateCcw className="h-3 w-3 mr-1" />
            Reset
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Search */}
        <div className="space-y-2">
          <Label className="text-xs">Search</Label>
          <div className="relative">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Worker or shift name..."
              value={filters.search}
              onChange={(e) => handleSearchChange(e.target.value)}
              className="pl-8 h-9"
            />
          </div>
        </div>

        <Separator />

        {/* Node type toggles */}
        <div className="space-y-2">
          <Label className="text-xs">Show</Label>
          <div className="flex gap-2">
            <Button
              variant={filters.showWorkers ? "default" : "outline"}
              size="sm"
              onClick={toggleWorkers}
              className="flex-1 h-8"
            >
              <User className="h-3 w-3 mr-1" />
              Workers
            </Button>
            <Button
              variant={filters.showShifts ? "default" : "outline"}
              size="sm"
              onClick={toggleShifts}
              className="flex-1 h-8"
            >
              <Calendar className="h-3 w-3 mr-1" />
              Shifts
            </Button>
          </div>
        </div>

        <Separator />

        {/* Cost range */}
        <div className="space-y-2">
          <Label className="text-xs">Cost Range</Label>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <Label className="text-xs text-muted-foreground">Min</Label>
              <Input
                type="number"
                placeholder="0"
                value={filters.costRange[0] === 0 ? "" : filters.costRange[0]}
                onChange={(e) => handleCostMinChange(e.target.value)}
                className="h-8"
                min={0}
                step={0.01}
              />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Max</Label>
              <Input
                type="number"
                placeholder="∞"
                value={
                  filters.costRange[1] === Infinity ? "" : filters.costRange[1]
                }
                onChange={(e) => handleCostMaxChange(e.target.value)}
                className="h-8"
                min={0}
                step={0.01}
              />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Data range: ${stats.minCost.toFixed(2)} - ${stats.maxCost.toFixed(2)}
          </p>
        </div>

        <Separator />

        {/* Stats summary */}
        <div className="space-y-1">
          <Label className="text-xs">Graph Stats</Label>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <span className="text-muted-foreground">Workers:</span>
            <span className="font-medium">{stats.workerCount}</span>
            <span className="text-muted-foreground">Shifts:</span>
            <span className="font-medium">{stats.shiftCount}</span>
            <span className="text-muted-foreground">Assignments:</span>
            <span className="font-medium">{stats.assignmentCount}</span>
            <span className="text-muted-foreground">Optimized Cost:</span>
            <span className="font-medium">${stats.totalCost.toFixed(2)}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
