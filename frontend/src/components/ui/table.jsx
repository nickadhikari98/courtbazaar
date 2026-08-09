import * as React from "react";
import { ArrowUp, ArrowDown, ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

/**
 * Table primitives — none existed before (every admin list page hand-rolled
 * its own <table>/<thead>/<tbody> markup, see DESIGN_SYSTEM_AUDIT.md §2.H).
 * These are thin, semantic wrappers with the styling that was already being
 * repeated by hand, not a new visual design — adopting them page by page
 * should be a zero-visual-change refactor.
 */

const Table = React.forwardRef(({ className, ...props }, ref) => (
  <div className="overflow-x-auto cb-scroll">
    <table ref={ref} className={cn("w-full text-sm", className)} {...props} />
  </div>
));
Table.displayName = "Table";

const TableHeader = React.forwardRef(({ className, ...props }, ref) => (
  <thead ref={ref} className={cn("bg-secondary text-left text-xs cb-overline", className)} {...props} />
));
TableHeader.displayName = "TableHeader";

const TableBody = React.forwardRef(({ className, ...props }, ref) => (
  <tbody ref={ref} className={cn("divide-y divide-border", className)} {...props} />
));
TableBody.displayName = "TableBody";

const TableRow = React.forwardRef(({ className, ...props }, ref) => (
  <tr ref={ref} className={cn("hover:bg-secondary/40", className)} {...props} />
));
TableRow.displayName = "TableRow";

const TableHead = React.forwardRef(({ className, ...props }, ref) => (
  <th ref={ref} className={cn("px-4 py-3 font-bold", className)} {...props} />
));
TableHead.displayName = "TableHead";

const TableCell = React.forwardRef(({ className, ...props }, ref) => (
  <td ref={ref} className={cn("px-4 py-3", className)} {...props} />
));
TableCell.displayName = "TableCell";

/** Full-width empty-state row — pass the column count so colSpan lines up. */
const TableEmpty = ({ colSpan, children = "No results" }) => (
  <tr>
    <td colSpan={colSpan} className="px-4 py-10 text-center text-muted-foreground">
      {children}
    </td>
  </tr>
);

/** Full-width loading row (skeleton-style) — pass the column count. */
const TableLoading = ({ colSpan, rows = 3 }) => (
  <>
    {Array.from({ length: rows }).map((_, i) => (
      <tr key={i}>
        <td colSpan={colSpan} className="px-4 py-3">
          <div className="h-4 bg-secondary rounded animate-pulse" />
        </td>
      </tr>
    ))}
  </>
);

/** Sortable column header — call `onSort(key)` and pass the current sort state back in. */
const TableSortHead = ({ sortKey, currentSort, onSort, className, children, ...props }) => {
  const active = currentSort?.key === sortKey;
  return (
    <th className={cn("px-4 py-3 font-bold", className)} {...props}>
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className="inline-flex items-center gap-1 hover:text-foreground"
      >
        {children}
        {active && (currentSort.direction === "asc" ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />)}
      </button>
    </th>
  );
};

/** Page navigation for a table — purely presentational, caller owns the page state. */
const TablePagination = ({ page, totalPages, onPageChange }) => {
  if (totalPages <= 1) return null;
  return (
    <div className="flex items-center justify-between px-4 py-3 border-t border-border text-sm">
      <span className="text-muted-foreground">Page {page} of {totalPages}</span>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
          <ChevronLeft className="w-4 h-4" /> Prev
        </Button>
        <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>
          Next <ChevronRight className="w-4 h-4" />
        </Button>
      </div>
    </div>
  );
};

export {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
  TableEmpty, TableLoading, TableSortHead, TablePagination,
};
