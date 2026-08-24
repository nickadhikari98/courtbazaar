import * as React from "react";
import { DayPicker } from "react-day-picker";
import { ChevronLeft, ChevronRight, ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";

function Calendar({ className, classNames, showOutsideDays = true, ...props }) {
  return (
    <DayPicker
      showOutsideDays={showOutsideDays}
      className={cn("p-3", className)}
      classNames={{
        months: "flex flex-col sm:flex-row gap-2",
        month: "flex flex-col gap-4",
        month_caption: "flex justify-center pt-1 relative items-center w-full",
        caption_label: "text-sm font-semibold font-display",
        nav: "flex items-center justify-between absolute inset-x-0 top-0",
        button_previous: cn(
          buttonVariants({ variant: "outline" }),
          "h-7 w-7 bg-transparent p-0 text-muted-foreground hover:text-foreground"
        ),
        button_next: cn(
          buttonVariants({ variant: "outline" }),
          "h-7 w-7 bg-transparent p-0 text-muted-foreground hover:text-foreground"
        ),
        dropdowns: "flex items-center justify-center gap-1.5",
        dropdown_root: "relative inline-flex items-center rounded-md border border-input bg-white px-2 py-1 hover:bg-slate-50 transition-colors",
        dropdown: "absolute inset-0 opacity-0 cursor-pointer",
        month_grid: "w-full border-collapse mt-2",
        weekdays: "flex",
        weekday: "text-muted-foreground rounded-md w-8 font-normal text-[0.8rem] flex-1 text-center",
        weeks: "flex flex-col gap-1 mt-1",
        week: "flex w-full",
        day: "relative p-0 text-center text-sm flex-1 focus-within:relative focus-within:z-20",
        day_button: cn(
          buttonVariants({ variant: "ghost" }),
          "h-8 w-8 p-0 font-normal aria-selected:opacity-100 mx-auto"
        ),
        range_start: "rounded-l-md",
        range_end: "rounded-r-md",
        selected: "[&>button]:bg-accent [&>button]:text-white [&>button]:hover:bg-accent [&>button]:hover:text-white",
        today: "[&>button]:bg-slate-100 [&>button]:font-bold",
        outside: "text-muted-foreground opacity-50",
        disabled: "text-muted-foreground opacity-30",
        hidden: "invisible",
        ...classNames,
      }}
      components={{
        Chevron: ({ orientation, ...chevronProps }) => {
          if (orientation === "left") return <ChevronLeft className="h-4 w-4" {...chevronProps} />;
          if (orientation === "down") return <ChevronDown className="h-4 w-4 ml-1 opacity-60" {...chevronProps} />;
          return <ChevronRight className="h-4 w-4" {...chevronProps} />;
        },
      }}
      {...props}
    />
  );
}
Calendar.displayName = "Calendar";

export { Calendar };
