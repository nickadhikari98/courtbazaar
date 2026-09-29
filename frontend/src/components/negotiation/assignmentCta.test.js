/* D2 (mobile): the "Open Discussion & Documents" button overflowed its
   column on phones (~18px past a 375px viewport) because the Button base is
   whitespace-nowrap + a fixed h-8. jsdom can't measure layout, so this pins
   the class contract the fix relies on: <Button> builds its classes as
   cn(buttonVariants({ variant, size, className })), and tailwind-merge must
   let ASSIGNMENT_CTA_CLASS override the base nowrap/h-8 while keeping the
   32px single-line height and everything else the button had. */
import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";
import { ASSIGNMENT_CTA_CLASS } from "@/components/negotiation/assignmentCta";

const classesOf = (className) =>
  cn(buttonVariants({ variant: "outline", size: "sm", className })).split(/\s+/);

describe("Assignment module CTA (D2 mobile overflow)", () => {
  const before = classesOf("font-bold");
  const after = classesOf(ASSIGNMENT_CTA_CLASS);

  test("the old button could never wrap (the cause of the overflow)", () => {
    expect(before).toEqual(expect.arrayContaining(["whitespace-nowrap", "h-8"]));
  });

  test("the label can wrap on a narrow column", () => {
    expect(after).toContain("whitespace-normal");
    expect(after).not.toContain("whitespace-nowrap");
    expect(after).toContain("h-auto");
    expect(after).not.toContain("h-8");
  });

  test("a single-line button keeps its 32px height", () => {
    expect(after).toEqual(expect.arrayContaining(["min-h-8", "py-1"]));
  });

  test("nothing else about the button changes", () => {
    const changed = new Set(["whitespace-nowrap", "h-8", "whitespace-normal", "h-auto", "min-h-8", "py-1", "text-left"]);
    expect(after.filter((c) => !changed.has(c)).sort()).toEqual(before.filter((c) => !changed.has(c)).sort());
    expect(after).toEqual(expect.arrayContaining(["font-bold", "text-xs", "px-3", "border", "border-input"]));
  });
});
