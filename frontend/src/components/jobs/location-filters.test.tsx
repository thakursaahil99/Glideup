import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { countryName, facetOptions, LocationFilters, remoteLabel } from "@/components/jobs/location-filters";
import { EMPTY_FILTERS, type JobFilters } from "@/lib/api/jobs";

const facets = {
  countries: { IN: 120, US: 300, GB: 40 },
  states: { Karnataka: 70, Maharashtra: 30 },
  cities: { Bengaluru: 65, Mysuru: 5 },
};

function renderFilters(filters: JobFilters = EMPTY_FILTERS) {
  const onChange = vi.fn();
  render(<LocationFilters filters={filters} facets={facets} onChange={onChange} />);
  return onChange;
}

describe("LocationFilters", () => {
  it("lists countries by count with readable names", () => {
    renderFilters();
    const options = Array.from(
      (screen.getByLabelText(/Country/) as HTMLSelectElement).options,
      (o) => o.textContent,
    );
    expect(options).toEqual(["Any country", "United States (300)", "India (120)", "United Kingdom (40)"]);
    // No state/city dropdowns until a country is chosen.
    expect(screen.queryByLabelText(/State/)).not.toBeInTheDocument();
  });

  it("cascades country -> state -> city and resets children", () => {
    const onChange = renderFilters({
      ...EMPTY_FILTERS,
      countries: ["IN"],
      states: ["Karnataka"],
      cities: ["Bengaluru"],
    });
    expect(screen.getByLabelText("State / UT")).toHaveValue("Karnataka");
    expect(screen.getByLabelText(/City/)).toHaveValue("Bengaluru");

    fireEvent.change(screen.getByLabelText("State / UT"), { target: { value: "Maharashtra" } });
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ countries: ["IN"], states: ["Maharashtra"], cities: [] }),
    );
    fireEvent.change(screen.getByLabelText(/Country/), { target: { value: "US" } });
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ countries: ["US"], states: [], cities: [] }),
    );
  });

  it("India / International quick toggle", () => {
    const onChange = renderFilters();
    fireEvent.click(screen.getByRole("radio", { name: "India" }));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ countries: ["IN"], region: null }));
    fireEvent.click(screen.getByRole("radio", { name: "International" }));
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ countries: [], region: "international" }),
    );
  });

  it("international hides India from the country list and disables Remote - India", () => {
    renderFilters({ ...EMPTY_FILTERS, region: "international" });
    expect(screen.getByRole("radio", { name: "International" })).toHaveAttribute("aria-checked", "true");
    const options = Array.from(
      (screen.getByLabelText(/Country/) as HTMLSelectElement).options,
      (o) => o.value,
    );
    expect(options).not.toContain("IN");
    expect(screen.getByLabelText("Remote - India")).toBeDisabled();
  });

  it("chooses a remote scope", () => {
    const onChange = renderFilters();
    fireEvent.click(screen.getByLabelText("Remote - Worldwide"));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ remote: "worldwide" }));
  });
});

describe("helpers", () => {
  it("keeps a selected value visible even without results", () => {
    expect(facetOptions({ Pune: 3 }, "Kochi")).toEqual([
      ["Kochi", 0],
      ["Pune", 3],
    ]);
  });

  it("labels remote jobs by scope", () => {
    expect(remoteLabel({ work_mode: "remote", remote_scope: "country", countries: ["IN"] })).toBe(
      "Remote · India",
    );
    expect(remoteLabel({ work_mode: "remote", remote_scope: "worldwide", countries: [] })).toBe(
      "Remote · Worldwide",
    );
    expect(remoteLabel({ work_mode: "hybrid", remote_scope: null, countries: ["IN"] })).toBeNull();
    expect(countryName("GB")).toBe("United Kingdom");
  });
});
